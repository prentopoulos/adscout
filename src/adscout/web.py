"""Single-user loopback workspace. All operations stay in the local database."""

import argparse
import contextlib
import hmac
import json
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
    draft_notes,
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


def source_link(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return e(url)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username:
        return e(url)
    return f'<a href="{e(url)}" target="_blank" rel="noreferrer noopener">{e(url)}</a>'


def review(connection: sqlite3.Connection, draft_id: int, csrf: str) -> str:
    draft = get_draft(connection, draft_id)
    claims = claim_rows(connection, draft)
    citations = (
        "".join(
            f"<li><strong>{e(c['claim_key'])}</strong> {e(c['text'])}"
            f"<blockquote>{e(c['quote'])}</blockquote>{source_link(c['source_url'])}</li>"
            for c in claims
        )
        or "<li>No verified claims in this draft run.</li>"
    )
    actions = ""
    flags = connection.execute(
        "SELECT flag, detail FROM lead_step_outcomes WHERE lead_id=? AND run_id=? "
        "AND flag IS NOT NULL ORDER BY outcome_id",
        (draft["lead_id"], draft["run_id"]),
    ).fetchall()
    warnings = "".join(
        f'<p class="notice error"><strong>{e(row["flag"])}</strong>: {e(row["detail"])}</p>'
        for row in flags
    )
    if draft["status"] == "pending_approval":
        fields = {"draft": draft_id, "reviewed": review_digest(draft)}
        actions = form("approve", csrf, fields, "Approve draft")
        options = "".join(f"<option>{e(reason)}</option>" for reason in REASONS)
        actions += (
            '<form method="post" action="/action">'
            f'<input type="hidden" name="csrf" value="{e(csrf)}">'
            '<input type="hidden" name="action" value="reject">'
            f'<input type="hidden" name="draft" value="{draft_id}">'
            f'<input type="hidden" name="reviewed" value="{e(review_digest(draft))}">'
            f'<label>Rejection reason <select name="reason">{options}</select></label>'
            '<button class="secondary" type="submit">Reject draft</button></form>'
        )
    return (
        f'<section id="review"><div class="section-title"><h2>Review · {e(draft["name"])}</h2>'
        f'<span class="badge">{e(draft["status"])}</span></div>'
        f'<p class="muted">Source mode: {e(draft["data_mode"])} · Revision {draft["revision"]}</p>'
        f"{warnings}"
        '<div class="review-grid"><article><h3>Pitch draft</h3>'
        f'<h4>{e(draft["subject"])}</h4><pre class="message">{e(draft["body"])}</pre>'
        f'<div class="actions">{actions}</div></article>'
        f'<article><h3>Verified research</h3><ol class="citations">{citations}</ol>'
        f"<details><summary>Checks and critic notes</summary><pre>{e(draft_notes(draft))}</pre>"
        "</details></article></div></section>"
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
    demo_label = (
        "Synthetic demo · scripted model responses" if mode in ("fixture", "stub") else mode
    )
    pending = sum(r["status"] == "pending_approval" for r in rows)
    crm = sum(bool(r["in_crm"]) for r in rows)
    won = sum(r["amount_cents"] or 0 for r in rows if r["stage"] == "won")
    cost = json.loads(run["cost_summary_json"] or "{}") if run else {}
    total_cost = cost.get("total", {}).get("cost_usd", 0)
    table_rows = []
    for row in rows:
        name = (
            f'<a href="/?draft={row["draft_id"]}#review">{e(row["name"])}</a>'
            if row["draft_id"]
            else e(row["name"])
        )
        delivery = (
            form(
                "send",
                csrf,
                {"approval": row["approval_id"]},
                "Place in sandbox",
                style="secondary",
            )
            if row["status"] == "approved" and row["in_crm"]
            else ""
        )
        deal = ""
        if row["in_crm"]:
            deal = form(
                "deal",
                csrf,
                {"lead": row["lead_id"], "stage": "won", "cents": 250000},
                "Simulate $2,500 won",
                style="secondary",
            )
        score = "—" if row["score"] is None else f"{row['score']:g}"
        table_rows.append(
            f'<tr><td>{name}<small>{e(row["domain"])}</small></td><td class="number">{score}</td>'
            f'<td><span class="badge">{e(row["status"] or row["exit_reason"] or "sourced")}</span>'
            f"<small>{e(row['exit_reason'])}</small></td>"
            f"<td>{'Synced' if row['in_crm'] else '—'}</td>"
            f'<td class="row-actions">{delivery}{deal}</td></tr>'
        )
    steps = connection.execute(
        "SELECT step, entering, kept FROM step_runs WHERE run_id=? ORDER BY seq",
        (run["run_id"] if run else "",),
    ).fetchall()
    bars = (
        "".join(
            f'<div class="funnel-row"><span>{e(s["step"])}</span><meter min="0" '
            f'max="{max(1, len(rows))}" value="{s["kept"] or 0}"></meter>'
            f'<b>{s["kept"] or 0}</b><span class="muted">of {s["entering"] or 0}</span></div>'
            for s in steps
        )
        or "<p>No run yet. Start with <code>adscout demo</code>.</p>"
    )
    messages = connection.execute(
        "SELECT m.*, EXISTS(SELECT 1 FROM sandbox_suppressions s WHERE s.lead_id=m.lead_id) "
        "suppressed FROM sandbox_messages m JOIN leads l ON l.lead_id=m.lead_id "
        "WHERE l.segment_id=? ORDER BY m.created_at DESC",
        (segment,),
    ).fetchall()
    inbox = (
        "".join(
            f"<details><summary>{e(m['subject'])} · "
            f"{'Unsubscribed' if m['suppressed'] else 'Placed locally'}</summary>"
            f"<p>To {e(m['destination'])} · From {e(m['sender'])}</p>"
            f'<pre class="message">{e(m["body"])}</pre>'
            f'<a href="/unsubscribe?id={e(m["message_id"])}">'
            "Unsubscribe this synthetic lead</a></details>"
            for m in messages
        )
        or '<p class="muted">No messages yet. Approve a draft, then sync and place it here.</p>'
    )
    if draft_id is None:
        draft_id = next((r["draft_id"] for r in rows if r["status"] == "pending_approval"), None)
    review_html = review(connection, draft_id, csrf) if draft_id is not None else ""
    if draft_id is not None and get_draft(connection, draft_id)["segment_id"] != segment:
        raise ActionRefused("Draft belongs to a different segment")
    banner = (
        f'<p class="notice {"error" if error else ""}" role="status">{e(notice)}</p>'
        if notice
        else ""
    )
    sync = form("sync", csrf, {}, "Sync approved to local CRM", style="secondary")
    table_body = "".join(table_rows) or '<tr><td colspan="5">No prospects. Run the demo.</td></tr>'
    run_status = e(run["status"] if run else "none")
    cost_label = "Estimated fixture model cost" if mode != "live" else "Recorded model spend"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AdScout workspace</title>
<link rel="stylesheet" href="/workspace.css"></head><body>
<aside><a class="brand" href="/">AdScout<span>Prospecting workspace</span></a>
<nav aria-label="Workspace"><a href="#prospects">Prospects</a><a href="#review">Review drafts</a>
<a href="#funnel">Funnel</a><a href="#inbox">Sandbox inbox</a></nav>
<p>Local MVP<br>Single-user workspace</p></aside><main>
<header><div><h1>Your prospect pipeline</h1><p class="muted">{e(segment)}</p></div>
<span class="mode">{e(demo_label)}</span></header>{banner}
<div class="summary"><p><strong>{len(rows)}</strong> companies</p>
<p><strong>{pending}</strong> awaiting review</p><p><strong>{crm}</strong> in local CRM</p>
<p><strong>${won / 100:,.0f}</strong> simulated won revenue · USD</p></div>
<section id="prospects"><div class="section-title"><h2>Ranked prospects</h2>{sync}</div>
<div class="table-scroll"><table><thead><tr><th>Company</th><th>Fit score</th><th>Status</th>
<th>Local CRM</th><th>Sandbox actions</th></tr></thead><tbody>
{table_body}
</tbody></table></div></section>{review_html}
<section id="funnel"><h2>Run funnel</h2><p class="muted">Latest pipeline run · {run_status}</p>
{bars}<p>{cost_label}: ${float(total_cost):.6f} USD</p>
<p class="muted">Simulated revenue is a scenario you enter after CRM sync.
It is not a measured sales result.
Use the CLI trace and export commands for call-level usage and costs.</p></section>
<section id="inbox"><h2>Local sandbox inbox</h2>
<p class="muted">Synthetic messages stored on this PC. No email is sent.</p>{inbox}</section>
<footer>AdScout portfolio MVP · fixture outcomes are scripted ·
cloud integrations and live quality studies are deferred</footer>
</main></body></html>"""


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
                body = "<h1>Unsubscribe from the local sandbox</h1>" + form(
                    "unsubscribe",
                    self.csrf,
                    {"id": query.get("id", [""])[0]},
                    "Confirm unsubscribe",
                )
                self.reply(200, body)
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
