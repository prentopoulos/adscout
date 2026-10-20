"""Single-user loopback workspace. All operations stay in the local database."""

import argparse
import contextlib
import hmac
import secrets
import sqlite3
from functools import partial
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from adscout.config import load_segment
from adscout.db.connection import connect
from adscout.db.migrate import upgrade
from adscout.pipeline.recorder import RunFailed, RunInProgress
from adscout.pipeline.run import run_crm_sync
from adscout.workspace import (
    REASONS,
    ActionRefused,
    claim_rows,
    decide,
    get_draft,
    leads,
    review_digest,
    send_sandbox,
    set_deal,
    unsubscribe,
)

CSS = Path(__file__).with_name("workspace.css")


def e(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def form(action: str, csrf: str, fields: dict[str, Any], label: str, *, style: str = "") -> str:
    hidden = "".join(
        f'<input type="hidden" name="{e(k)}" value="{e(v)}">'
        for k, v in {"csrf": csrf, "action": action, **fields}.items()
    )
    return (
        f'<form method="post" action="/action">{hidden}'
        f'<button class="{style}" type="submit">{e(label)}</button></form>'
    )


# Labels and tones for every draft status, exit reason and review flag the workspace shows.
STATUS = {
    "pending_approval": ("Needs review", "blue", "Draft ready for your decision"),
    "approved": ("Approved", "green", "Approved by you"),
    "rejected": ("Rejected", "grey", "Rejected by you"),
    "failed_checks": ("Failed checks", "red", "Draft failed the rule checker"),
    "draft_failed": ("Draft failed", "red", "No draft passed the checks"),
    "research_failed": ("Research failed", "red", "No claim could be verified"),
    "near_miss": ("Near miss", "amber", "Scored 55 to 59; not researched"),
    "missing_key_fields": ("Missing data", "amber", "Key company facts are missing"),
    "below_threshold": ("Below threshold", "grey", "Scored under 55"),
    "out_of_profile": ("Out of profile", "grey", "Outside size, region or category"),
    "excluded": ("Excluded", "grey", "On the segment's exclusion list"),
    "duplicate": ("Duplicate", "grey", "Already in this list"),
    "sourced": ("Sourced", "grey", "Waiting for the next step"),
}
FLAGS = {
    "critic_unresolved": "Critic concern unresolved",
    "research_partial": "Research partly failed",
}


def pill(key: str) -> str:
    label, tone, _ = STATUS.get(key, (key.replace("_", " ").capitalize(), "grey", ""))
    return f'<span class="pill {tone}">{e(label)}</span>'


def bar(fraction: float, *, muted: bool = False) -> str:
    step = max(0, min(100, round(fraction * 20) * 5))
    return f'<span class="bar{" muted" if muted else ""}"><i class="w{step}"></i></span>'


def source_link(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return e(url)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username:
        return e(url)
    shown = f"{parts.hostname}{parts.path.rstrip('/')}"
    return f'<a href="{e(url)}" target="_blank" rel="noreferrer noopener">{e(shown)}</a>'


def page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{e(title)}</title><link rel="stylesheet" href="/workspace.css"></head>'
        f"<body>{body}</body></html>"
    )


def review(connection: sqlite3.Connection, draft_id: int, csrf: str) -> str:
    draft = get_draft(connection, draft_id)
    claims = claim_rows(connection, draft)
    sources = (
        "".join(
            f'<li><span class="key">{e(c["claim_key"])}</span>'
            f'<span class="claim">{e(c["text"])}</span>'
            + ("" if c["quote"] == c["text"] else f"<blockquote>{e(c['quote'])}</blockquote>")
            + f"{source_link(c['source_url'])}</li>"
            for c in claims
        )
        or '<li><span class="claim">No verified claims.</span></li>'
    )
    flags = connection.execute(
        "SELECT flag, detail FROM lead_step_outcomes WHERE lead_id=? AND run_id=? "
        "AND flag IS NOT NULL ORDER BY outcome_id",
        (draft["lead_id"], draft["run_id"]),
    ).fetchall()
    warnings = "".join(
        f'<p class="warning"><strong>{e(FLAGS.get(row["flag"], row["flag"]))}</strong>: '
        f"{e(row['detail'])}</p>"
        for row in flags
    )
    if draft["status"] == "pending_approval":
        reviewed = review_digest(draft)
        options = "".join(f"<option>{e(reason)}</option>" for reason in REASONS)
        actions = (
            '<div class="actions">'
            + form("approve", csrf, {"draft": draft_id, "reviewed": reviewed}, "Approve draft")
            + '<form class="reject" method="post" action="/action">'
            f'<input type="hidden" name="csrf" value="{e(csrf)}">'
            '<input type="hidden" name="action" value="reject">'
            f'<input type="hidden" name="draft" value="{draft_id}">'
            f'<input type="hidden" name="reviewed" value="{e(reviewed)}">'
            f'<label>Rejection reason <select name="reason">{options}</select></label>'
            '<button class="secondary" type="submit">Reject draft</button></form></div>'
        )
    else:
        label = STATUS.get(draft["status"], (draft["status"], "", ""))[0]
        actions = f'<p class="decided">Decision recorded: {e(label)}.</p>'
    return (
        f'<section id="review" class="panel"><div class="review-head"><div>'
        f"<h2>{e(draft['name'])}</h2><p>{e(draft['domain'])} · Revision {draft['revision']}"
        f"</p></div>{pill(draft['status'])}</div>"
        + (f'<div class="warnings">{warnings}</div>' if warnings else "")
        + '<div class="review-grid"><article><p class="label">Pitch draft</p>'
        f'<h3 class="subject">{e(draft["subject"])}</h3>'
        f'<pre class="message">{e(draft["body"])}</pre>{actions}</article>'
        f'<article><p class="label">Verified research</p><ol class="sources">{sources}</ol>'
        "</article></div></section>"
    )


def render(
    connection: sqlite3.Connection,
    segment: str,
    csrf: str,
    draft_id: int | None = None,
    notice: str = "",
    error: bool = False,
) -> str:
    rows = leads(connection, segment)
    run = connection.execute(
        "SELECT * FROM runs WHERE segment_id=? AND kind='pipeline' "
        "ORDER BY started_at DESC, rowid DESC LIMIT 1",
        (segment,),
    ).fetchone()
    mode = run["source"] if run else "no run"
    demo_label = "Synthetic data" if mode in ("fixture", "stub") else mode.capitalize()
    pending = sum(r["status"] == "pending_approval" for r in rows)
    crm = sum(bool(r["in_crm"]) for r in rows)
    won = sum(r["amount_cents"] or 0 for r in rows if r["stage"] == "won")
    if draft_id is None:
        draft_id = next((r["draft_id"] for r in rows if r["status"] == "pending_approval"), None)
    if draft_id is not None and get_draft(connection, draft_id)["segment_id"] != segment:
        raise ActionRefused("Draft belongs to a different segment")
    table_rows = []
    for row in rows:
        name = (
            f'<a href="/?draft={row["draft_id"]}#review">{e(row["name"])}</a>'
            if row["draft_id"]
            else f"<span>{e(row['name'])}</span>"
        )
        actions = ""
        if row["status"] == "approved" and row["in_crm"]:
            actions += form(
                "send",
                csrf,
                {"approval": row["approval_id"]},
                "Place in sandbox",
                style="secondary small",
            )
        if row["in_crm"] and row["stage"] != "won":
            actions += form(
                "deal",
                csrf,
                {"lead": row["lead_id"], "stage": "won", "cents": 250000},
                "Simulate $2,500 won",
                style="secondary small",
            )
        if row["score"] is None:
            fit = '<span class="none">—</span>'
        else:
            fit = f"<b>{row['score']:g}</b>" + bar(row["score"] / 100, muted=row["score"] < 60)
        key = row["status"] or row["exit_reason"] or "sourced"
        if row["stage"] == "won":
            crm_cell = (
                f'<span class="crm synced">Won ${(row["amount_cents"] or 0) / 100:,.0f}</span>'
            )
        elif row["in_crm"]:
            crm_cell = '<span class="crm synced">Synced</span>'
        else:
            crm_cell = '<span class="crm">—</span>'
        selected = ' class="is-selected"' if row["draft_id"] == draft_id else ""
        table_rows.append(
            f'<tr{selected}><td><div class="fit">{fit}</div></td>'
            f'<td><div class="company">{name}<small>{e(row["domain"])}</small></div></td>'
            f"<td>{pill(key)}</td>"
            f'<td>{crm_cell}</td><td><div class="row-actions">{actions}</div></td></tr>'
        )
    messages = connection.execute(
        "SELECT m.*, EXISTS(SELECT 1 FROM sandbox_suppressions s WHERE s.lead_id=m.lead_id) "
        "suppressed FROM sandbox_messages m JOIN leads l ON l.lead_id=m.lead_id "
        "WHERE l.segment_id=? ORDER BY m.created_at DESC",
        (segment,),
    ).fetchall()
    inbox = (
        "".join(
            f"<details><summary><span>{e(m['subject'])}</span>"
            + (
                '<span class="pill">Unsubscribed</span>'
                if m["suppressed"]
                else '<span class="pill green">Placed locally</span>'
            )
            + f'</summary><div class="inbox-body"><p class="inbox-meta">To {e(m["destination"])}'
            f" · From {e(m['sender'])} · {e(str(m['created_at'])[:16].replace('T', ' '))}</p>"
            f'<pre class="message">{e(m["body"])}</pre>'
            f'<a href="/unsubscribe?id={e(m["message_id"])}">Unsubscribe</a></div></details>'
            for m in messages
        )
        or '<p class="empty">No messages.</p>'
    )
    review_html = review(connection, draft_id, csrf) if draft_id is not None else ""
    banner = (
        f'<p class="notice {"error" if error else ""}" role="status">{e(notice)}</p>'
        if notice
        else ""
    )
    sync = form("sync", csrf, {}, "Sync approved to CRM", style="secondary")
    table_body = "".join(table_rows) or '<tr><td class="empty" colspan="5">No prospects.</td></tr>'
    title = segment.replace("-", " ").capitalize()
    attention = " attention" if pending else ""
    return page(
        "AdScout",
        f"""<aside class="sidebar">
<a class="brand" href="/"><span class="brand-mark">A</span>AdScout</a>
<nav class="nav" aria-label="Workspace">
<a href="#prospects">Prospects<span class="count">{len(rows)}</span></a>
<a href="#review">Review<span class="count{attention}">{pending}</span></a>
<a href="#inbox">Inbox<span class="count">{len(messages)}</span></a></nav>
</aside><main>
<header class="topbar"><h1>{e(title)}</h1><span class="mode">{e(demo_label)}</span></header>
{banner}
<dl class="stats"><div class="stat"><dt>Companies</dt><dd>{len(rows)}</dd></div>
<div class="stat"><dt>Awaiting review</dt><dd>{pending}</dd></div>
<div class="stat"><dt>In CRM</dt><dd>{crm}</dd></div>
<div class="stat"><dt>simulated won revenue</dt><dd>${won / 100:,.0f}<small>USD</small></dd></div>
</dl>
<section id="prospects"><div class="section-head"><h2>Prospects</h2>{sync}</div>
<div class="panel panel-scroll"><table><thead><tr><th>Fit</th><th>Company</th>
<th>Status</th><th>CRM</th><th></th>
</tr></thead><tbody>{table_body}</tbody></table></div></section>
{review_html}
<section id="inbox"><div class="section-head"><h2>Sandbox inbox</h2></div>
<div class="panel inbox">{inbox}</div></section>
</main>""",
    )


def apply_action(
    connection: sqlite3.Connection, segment: str, config: Path, values: dict[str, str]
) -> str:
    action = values.get("action")
    if action in ("approve", "reject"):
        draft_id = int(values["draft"])
        if get_draft(connection, draft_id)["segment_id"] != segment:
            raise ActionRefused("Draft belongs to a different segment")
        decide(
            connection,
            draft_id,
            values["reviewed"],
            "approved" if action == "approve" else "rejected",
            values.get("reason", REASONS[0]),
        )
        return "Decision recorded. Approved drafts can now be synced to the local CRM."
    if action == "sync":
        run_crm_sync(connection, load_segment(config / "segments" / f"{segment}.yaml"))
        return "Approved records synced to the local CRM sandbox."
    if action == "send":
        send_sandbox(connection, values["approval"])
        return "Approved message placed in the local sandbox inbox."
    if action == "deal":
        set_deal(connection, values["lead"], values["stage"], int(values["cents"]))
        return "Simulated deal saved. Simulated revenue updated."
    if action == "unsubscribe":
        unsubscribe(connection, values["id"])
        return "This synthetic lead is unsubscribed. Later sandbox delivery is blocked."
    raise ActionRefused("Unknown workspace action")


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args: Any, db: Path, config: Path, segment: str, csrf: str, **kwargs: Any):
        self.db, self.config, self.segment, self.csrf = db, config, segment, csrf
        super().__init__(*args, **kwargs)

    def reply(self, code: int, body: str, kind: str = "text/html; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def allowed(self, *, writing: bool = False) -> bool:
        host = f"127.0.0.1:{cast(ThreadingHTTPServer, self.server).server_port}"
        return self.headers.get("Host") == host and (
            not writing or self.headers.get("Origin") in (None, f"http://{host}")
        )

    def do_GET(self) -> None:
        if not self.allowed():
            self.reply(403, "Local host required")
            return
        url = urlsplit(self.path)
        if url.path == "/workspace.css":
            self.reply(200, CSS.read_text(encoding="utf-8"), "text/css; charset=utf-8")
            return
        if url.path not in ("/", "/unsubscribe"):
            self.reply(404, "Not found")
            return
        connection = connect(self.db)
        try:
            query = parse_qs(url.query)
            if url.path == "/unsubscribe":
                body = (
                    '<main class="single panel"><h1>Unsubscribe from the local sandbox</h1>'
                    "<p>This synthetic lead will receive no further sandbox messages.</p>"
                    + form(
                        "unsubscribe",
                        self.csrf,
                        {"id": query.get("id", [""])[0]},
                        "Confirm unsubscribe",
                    )
                    + "</main>"
                )
                self.reply(200, page("Unsubscribe · AdScout", body))
            else:
                chosen = int(query["draft"][0]) if "draft" in query else None
                self.reply(200, render(connection, self.segment, self.csrf, chosen))
        except (ActionRefused, ValueError, KeyError):
            self.reply(400, "Invalid draft or request. Return to the workspace and reload.")
        finally:
            connection.close()

    def do_POST(self) -> None:
        if not self.allowed(writing=True) or self.path != "/action":
            self.reply(403, "Local form required")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384:
                raise ActionRefused("Request too large or empty")
            if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                raise ActionRefused("Use the workspace form")
            values = {k: v[0] for k, v in parse_qs(self.rfile.read(size).decode("utf-8")).items()}
            if not hmac.compare_digest(values.get("csrf", "").encode(), self.csrf.encode()):
                raise ActionRefused("Form expired; reload the workspace")
        except (ValueError, UnicodeError) as error:
            self.reply(400, e(error))
            return
        connection = connect(self.db)
        try:
            notice = apply_action(connection, self.segment, self.config, values)
            self.reply(200, render(connection, self.segment, self.csrf, notice=notice))
        except (ValueError, KeyError, sqlite3.Error, RunFailed, RunInProgress) as error:
            self.reply(
                400, render(connection, self.segment, self.csrf, notice=str(error), error=True)
            )
        finally:
            connection.close()

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Request forms and unsubscribe references never enter terminal logs.


def serve(db: Path, config: Path, segment: str, port: int = 8765) -> None:
    upgrade(db)
    handler = partial(
        Handler, db=db, config=config, segment=segment, csrf=secrets.token_urlsafe(32)
    )
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(
            f"AdScout workspace: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)", flush=True
        )
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()


def command(args: argparse.Namespace) -> int:
    serve(Path(args.db or "data/adscout.db"), args.config_dir, args.segment, args.port)
    return 0
