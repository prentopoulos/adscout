"""Human review and the local MVP's sandbox operations. No model receives this data."""

import hashlib
import json
import sqlite3
from typing import Literal, cast

from adscout.config import canonical_hash
from adscout.crm.writer import account_exists
from adscout.db.connection import transaction, utc_now
from adscout.ids import uuid7
from adscout.pipeline.contracts import Outcome
from adscout.pipeline.recorder import Run

SENDER = "AdScout Demo Publisher (synthetic)"
DESTINATION = "sandbox@adscout.test"
REASONS = ("Needs revision", "Not relevant", "Not appropriate")


class ActionRefused(ValueError):
    """The local operator's requested action is stale or outside the sandbox."""


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def review_digest(draft: sqlite3.Row) -> str:
    return canonical_hash({"subject": draft["subject"], "body": draft["body"]})


def get_draft(connection: sqlite3.Connection, draft_id: int) -> sqlite3.Row:
    row = connection.execute(
        "SELECT d.*, l.segment_id, c.domain, c.name, r.source AS data_mode "
        "FROM drafts d JOIN leads l ON l.lead_id = d.lead_id "
        "JOIN companies c ON c.company_id = l.company_id "
        "JOIN runs r ON r.run_id = d.run_id WHERE d.draft_id = ?",
        (draft_id,),
    ).fetchone()
    if row is None:
        raise ActionRefused("Draft not found")
    return cast(sqlite3.Row, row)


def decide(
    connection: sqlite3.Connection,
    draft_id: int,
    reviewed: str,
    decision: Literal["approved", "rejected"],
    reason: str = "Needs revision",
) -> str:
    """Bind a human decision to the subject and body shown on the review screen."""
    draft = get_draft(connection, draft_id)
    if decision not in ("approved", "rejected") or reason not in REASONS:
        raise ActionRefused("Choose an approval or a listed rejection reason")
    if draft["status"] != "pending_approval" or review_digest(draft) != reviewed:
        raise ActionRefused("Draft changed or was already decided; reload before reviewing")
    run = Run(
        connection,
        "approval",
        draft["segment_id"],
        draft["data_mode"],
        {},
        {
            "seed_list_hash": "human review reads a stored draft",
            "stub_script_hash": "human decision, not a stub script",
        },
    )
    approval_id = str(uuid7())
    with run.recording(), run.step("approve", "real", 1) as recorder:

        def write() -> None:
            current = get_draft(connection, draft_id)
            if current["status"] != "pending_approval" or review_digest(current) != reviewed:
                raise ActionRefused("Draft changed during review; reload")
            connection.execute(
                "INSERT INTO approvals (approval_id, run_id, lead_id, draft_id, draft_sha256, "
                "decision, approver_kind, approver, reason, decided_at, approved_subject_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, 'person', 'local operator', ?, ?, ?)",
                (
                    approval_id,
                    run.run_id,
                    draft["lead_id"],
                    draft_id,
                    digest(draft["body"]),
                    decision,
                    reason if decision == "rejected" else None,
                    utc_now(),
                    digest(draft["subject"]),
                ),
            )
            connection.execute(
                "UPDATE drafts SET status = ? WHERE draft_id = ?", (decision, draft_id)
            )

        recorder.defer(write)
        recorder.outcomes.append(
            Outcome(
                lead_id=draft["lead_id"],
                outcome="kept" if decision == "approved" else "exited",
                reason=None if decision == "approved" else "rejected",
                detail=f"human review: {decision}",
            )
        )
    return approval_id


def send_sandbox(connection: sqlite3.Connection, approval_id: str) -> str:
    """The only send path: idempotent delivery into SQLite, never an external service.

    Local rendering fills fixed synthetic sender data and an unsubscribe path which the
    workspace serves. Approval, body, subject, CRM and suppression are checked atomically.
    """
    with transaction(connection):
        row = connection.execute(
            "SELECT a.*, d.body, d.subject, d.status, c.domain FROM approvals a "
            "JOIN drafts d ON d.draft_id = a.draft_id JOIN leads l ON l.lead_id = a.lead_id "
            "JOIN companies c ON c.company_id = l.company_id WHERE a.approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None or row["decision"] != "approved" or row["approver_kind"] != "person":
            raise ActionRefused("Delivery needs a human approval")
        if (
            row["status"] != "approved"
            or digest(row["body"]) != row["draft_sha256"]
            or digest(row["subject"]) != row["approved_subject_sha256"]
        ):
            raise ActionRefused("Approved draft changed; delivery refused")
        if not row["domain"].endswith((".test", ".example")):
            raise ActionRefused("Sandbox delivery accepts synthetic company domains only")
        if not account_exists(connection, row["domain"]):
            raise ActionRefused("Sync this approved lead to the local CRM first")
        if connection.execute(
            "SELECT 1 FROM sandbox_suppressions WHERE lead_id = ?", (row["lead_id"],)
        ).fetchone():
            raise ActionRefused("This lead unsubscribed from the local sandbox")
        existing = connection.execute(
            "SELECT message_id FROM sandbox_messages WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        if existing:
            return str(existing[0])
        message_id = str(uuid7())
        replacements = {
            "{{sender_name}}": SENDER,
            "{{sender_title}}": "Demo advertising team",
            "{{publisher_postal_address}}": "Synthetic address: Demo House, Example City",
            "{{unsubscribe_url}}": f"/unsubscribe?id={message_id}",
        }
        body = row["body"]
        for placeholder, value in replacements.items():
            if body.count(placeholder) != 1:
                raise ActionRefused(
                    "Draft needs each sender and unsubscribe placeholder exactly once"
                )
            body = body.replace(placeholder, value)
        if "{{" in body or "}}" in body:
            raise ActionRefused("Unresolved message placeholder")
        connection.execute(
            "INSERT INTO sandbox_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                message_id,
                approval_id,
                row["lead_id"],
                DESTINATION,
                SENDER,
                row["subject"],
                body,
                utc_now(),
            ),
        )
    return message_id


def unsubscribe(connection: sqlite3.Connection, message_id: str) -> None:
    with transaction(connection):
        row = connection.execute(
            "SELECT lead_id FROM sandbox_messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        if row is None:
            raise ActionRefused("Sandbox message not found")
        connection.execute(
            "INSERT OR IGNORE INTO sandbox_suppressions VALUES (?, ?)", (row[0], utc_now())
        )


def set_deal(connection: sqlite3.Connection, lead_id: str, stage: str, amount_cents: int) -> None:
    if stage not in ("pipeline", "won", "lost") or not 0 <= amount_cents <= 100000000:
        raise ActionRefused("Choose a valid simulated stage and amount")
    with transaction(connection):
        row = connection.execute(
            "SELECT c.domain FROM leads l JOIN companies c ON c.company_id = l.company_id "
            "WHERE l.lead_id = ?",
            (lead_id,),
        ).fetchone()
        if row is None or not account_exists(connection, row[0]):
            raise ActionRefused("A simulated deal needs a lead in the local CRM sandbox")
        connection.execute(
            "INSERT INTO simulated_deals (lead_id, stage, amount_cents, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(lead_id) DO UPDATE SET stage=excluded.stage, "
            "amount_cents=excluded.amount_cents, updated_at=excluded.updated_at",
            (lead_id, stage, amount_cents, utc_now()),
        )


def leads(connection: sqlite3.Connection, segment: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT l.lead_id, c.name, c.domain, "
        "(SELECT s.score FROM scores s WHERE s.lead_id=l.lead_id "
        "AND s.run_id=(SELECT s2.run_id FROM scores s2 WHERE s2.lead_id=l.lead_id "
        "ORDER BY s2.score_id DESC LIMIT 1) ORDER BY s.sample, s.score_id LIMIT 1) score, "
        "(SELECT o.reason FROM lead_step_outcomes o WHERE o.lead_id=l.lead_id "
        "AND o.outcome='exited' ORDER BY o.outcome_id DESC LIMIT 1) exit_reason, "
        "d.draft_id, d.status, a.approval_id, "
        "EXISTS(SELECT 1 FROM fake_crm_accounts f WHERE f.domain=c.domain) in_crm, "
        "sd.stage, sd.amount_cents FROM leads l JOIN companies c ON c.company_id=l.company_id "
        "LEFT JOIN drafts d ON d.draft_id=(SELECT max(d2.draft_id) FROM drafts d2 "
        "WHERE d2.lead_id=l.lead_id) LEFT JOIN approvals a ON a.draft_id=d.draft_id "
        "LEFT JOIN simulated_deals sd ON sd.lead_id=l.lead_id WHERE l.segment_id=? "
        "ORDER BY score IS NULL, score DESC, c.domain",
        (segment,),
    ).fetchall()


def claim_rows(connection: sqlite3.Connection, draft: sqlite3.Row) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM claims WHERE verified=1 AND brief_id = "
        "(SELECT brief_id FROM briefs WHERE lead_id=? AND run_id=? ORDER BY brief_id DESC LIMIT 1)",
        (draft["lead_id"], draft["run_id"]),
    ).fetchall()


def draft_notes(draft: sqlite3.Row) -> str:
    notes = {
        "checks": json.loads(draft["checks_json"]),
        "critic": json.loads(draft["critic_notes_json"]),
    }
    return json.dumps(notes, ensure_ascii=False, indent=2)
