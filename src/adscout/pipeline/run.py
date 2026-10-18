"""The three kinds of run: the pipeline up to drafts, the stub approver, and the CRM sync.

A pipeline run stops with drafts waiting for approval; it never waits for a person.
Approval is its own run, bound to each draft's SHA-256, and CRM sync is its own run over
drafts whose approval still matches their text (Phase 1 design, decisions 14 and 16).
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from adscout.config import SeedList, SegmentConfig, load_seeds, load_segment
from adscout.crm.writer import write_account
from adscout.db.connection import utc_now
from adscout.db.migrate import pending
from adscout.ids import uuid7
from adscout.pipeline.contracts import STUB_STEPS, Lead, Outcome, StepOutput
from adscout.pipeline.recorder import Run, RunSource, Snapshot
from adscout.pipeline.source import source
from adscout.pipeline.stubs import StubScript, is_reserved_domain, load_stub_script, run_stub

STUB_APPROVER = "stub approver"


class DatabaseNotReady(RuntimeError):
    """The database is missing migrations; `adscout db upgrade` fixes it."""


@dataclass(frozen=True)
class SegmentFiles:
    """A segment's config, seed list and stub script, loaded and validated."""

    segment: SegmentConfig
    seeds: SeedList
    script: StubScript

    @classmethod
    def load(cls, config_dir: Path, segment_id: str, seeds: Path | None = None) -> "SegmentFiles":
        segment = load_segment(config_dir / "segments" / f"{segment_id}.yaml")
        seed_list = load_seeds(seeds or config_dir / "seeds" / f"{segment_id}.csv", segment_id)
        script = load_stub_script(config_dir / "stubs" / f"{segment_id}.yaml")
        return cls(segment, seed_list, script)

    def snapshots(self) -> dict[str, Snapshot]:
        return {
            "icp_config_hash": segment_snapshot(self.segment),
            "seed_list_hash": Snapshot(
                "seed_list",
                self.seeds.content_hash(),
                [row.model_dump(mode="json") for row in self.seeds.rows],
            ),
            "stub_script_hash": Snapshot(
                "stub_script", self.script.content_hash(), self.script.model_dump(mode="json")
            ),
        }


def segment_snapshot(segment: SegmentConfig) -> Snapshot:
    return Snapshot("segment", segment.content_hash(), segment.model_dump(mode="json"))


def require_migrated(connection: sqlite3.Connection) -> None:
    if pending(connection):
        raise DatabaseNotReady("the database needs migrations; run `adscout db upgrade` first")


def source_label(domains: list[str]) -> RunSource:
    """`fixture` when every company is synthetic; otherwise `stub`, since nothing is live yet."""
    return "fixture" if domains and all(map(is_reserved_domain, domains)) else "stub"


def store_outputs(connection: sqlite3.Connection, run_id: str, output: StepOutput) -> None:
    now = utc_now()
    for enrichment in output.enrichments:
        connection.execute(
            "INSERT INTO enrichments (lead_id, run_id, implementation, fields_json, "
            "missing_fields_json, created_at) VALUES (?, ?, 'stub', ?, ?, ?)",
            (
                enrichment.lead_id,
                run_id,
                json.dumps(enrichment.fields),
                json.dumps(enrichment.missing_fields),
                now,
            ),
        )
    for score in output.scores:
        connection.execute(
            "INSERT INTO scores (lead_id, run_id, implementation, score, reasons_json, "
            "null_reasons_json, created_at) VALUES (?, ?, 'stub', ?, ?, ?, ?)",
            (
                score.lead_id,
                run_id,
                score.score,
                json.dumps(score.reasons),
                json.dumps(score.null_reasons),
                now,
            ),
        )
    for brief in output.briefs:
        connection.execute(
            "INSERT INTO briefs (lead_id, run_id, implementation, status, summary, claims_json, "
            "created_at) VALUES (?, ?, 'stub', ?, ?, ?, ?)",
            (
                brief.lead_id,
                run_id,
                brief.status,
                brief.summary,
                json.dumps([claim.model_dump() for claim in brief.claims]),
                now,
            ),
        )
    for draft in output.drafts:
        connection.execute(
            "INSERT INTO drafts (lead_id, run_id, implementation, revision, subject, body, "
            "body_sha256, status, created_at) VALUES (?, ?, 'stub', 1, ?, ?, ?, ?, ?)",
            (
                draft.lead_id,
                run_id,
                draft.subject,
                draft.body,
                sha256_text(draft.body),
                draft.status,
                now,
            ),
        )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_pipeline(connection: sqlite3.Connection, files: SegmentFiles) -> str:
    """Source the seeds, run every stub step, and stop with drafts pending approval."""
    require_migrated(connection)
    run = Run(
        connection,
        "pipeline",
        files.segment.segment_id,
        source_label([row.domain for row in files.seeds.rows]),
        files.snapshots(),
        null_reasons={},
    )
    with run.recording():
        with run.step("source", "real", len(files.seeds.rows)) as recorder:
            seed_list_hash = files.seeds.content_hash()
            leads = source(run, recorder, files.segment, files.seeds, seed_list_hash)
        for step in STUB_STEPS:
            with run.step(step, "stub", len(leads)) as recorder:
                output = run_stub(step, leads, files.script)
                store_outputs(connection, run.run_id, output)
                recorder.outcomes.extend(output.outcomes)
            going_on = {o.lead_id for o in output.outcomes if o.outcome == "kept"}
            leads = [lead for lead in leads if lead.lead_id in going_on]
    return run.run_id


def leads_by_id(connection: sqlite3.Connection, segment_id: str) -> dict[str, Lead]:
    rows = connection.execute(
        "SELECT l.lead_id, l.company_id, c.domain, c.name FROM leads AS l "
        "JOIN companies AS c ON c.company_id = l.company_id WHERE l.segment_id = ?",
        (segment_id,),
    ).fetchall()
    return {row["lead_id"]: Lead(**dict(row)) for row in rows}


def run_stub_approval(connection: sqlite3.Connection, files: SegmentFiles) -> str:
    """Decide every pending draft as the stub script says, bound to the draft's hash."""
    require_migrated(connection)
    segment_id = files.segment.segment_id
    leads = leads_by_id(connection, segment_id)
    pending_drafts = connection.execute(
        "SELECT d.draft_id, d.lead_id, d.body FROM drafts AS d JOIN leads AS l "
        "ON l.lead_id = d.lead_id WHERE l.segment_id = ? AND d.status = 'pending_approval' "
        "ORDER BY d.draft_id",
        (segment_id,),
    ).fetchall()
    snapshots = files.snapshots()
    del snapshots["seed_list_hash"]
    run = Run(
        connection,
        "approval",
        segment_id,
        source_label([lead.domain for lead in leads.values()]),
        snapshots,
        null_reasons={"seed_list_hash": "an approval run reads stored drafts, not the seed list"},
    )
    with run.recording(), run.step("approve", "stub", len(pending_drafts)) as recorder:
        for draft in pending_drafts:
            lead = leads[draft["lead_id"]]
            plan = files.script.for_lead(lead)
            decision = plan.approval or "rejected"
            reason = None if decision == "approved" else plan.rejection_reason or plan.expected
            connection.execute(
                "INSERT INTO approvals (approval_id, run_id, lead_id, draft_id, draft_sha256, "
                "decision, approver_kind, approver, reason, decided_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'stub', ?, ?, ?)",
                (
                    str(uuid7()),
                    run.run_id,
                    lead.lead_id,
                    draft["draft_id"],
                    sha256_text(draft["body"]),
                    decision,
                    STUB_APPROVER,
                    reason,
                    utc_now(),
                ),
            )
            connection.execute(
                "UPDATE drafts SET status = ? WHERE draft_id = ?", (decision, draft["draft_id"])
            )
            recorder.outcomes.append(
                Outcome(lead_id=lead.lead_id, outcome="kept", detail=files.script.label)
                if decision == "approved"
                else Outcome(
                    lead_id=lead.lead_id,
                    outcome="exited",
                    reason="rejected",
                    detail=f"{files.script.label}; rejected: {reason}",
                )
            )
    return run.run_id


def approved_for_sync(connection: sqlite3.Connection, segment_id: str) -> list[sqlite3.Row]:
    """Approved drafts whose current text still has the hash the approval was bound to."""
    rows = connection.execute(
        "SELECT a.approval_id, a.draft_sha256, a.approver_kind, d.body, d.subject, "
        "l.lead_id, l.source, l.agent_version, l.prompt_version, c.domain, c.name "
        "FROM approvals AS a JOIN drafts AS d ON d.draft_id = a.draft_id "
        "JOIN leads AS l ON l.lead_id = a.lead_id "
        "JOIN companies AS c ON c.company_id = l.company_id "
        "WHERE l.segment_id = ? AND a.decision = 'approved' ORDER BY a.decided_at",
        (segment_id,),
    ).fetchall()
    return [row for row in rows if sha256_text(row["body"]) == row["draft_sha256"]]


def latest(connection: sqlite3.Connection, table: str, column: str, lead_id: str) -> str | None:
    row = connection.execute(
        f"SELECT {column} FROM {table} WHERE lead_id = ? ORDER BY rowid DESC LIMIT 1",  # noqa: S608
        (lead_id,),
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def run_crm_sync(connection: sqlite3.Connection, segment: SegmentConfig) -> str:
    """Write every validly approved lead to the CRM through the one CRM writer."""
    require_migrated(connection)
    rows = approved_for_sync(connection, segment.segment_id)
    run = Run(
        connection,
        "crm_sync",
        segment.segment_id,
        source_label([row["domain"] for row in rows]),
        {"icp_config_hash": segment_snapshot(segment)},
        null_reasons={
            "seed_list_hash": "a CRM sync reads stored approvals, not the seed list",
            "stub_script_hash": "a CRM sync follows stored approvals, not the stub script",
        },
    )
    with run.recording(), run.step("crm_sync", "real", len(rows)) as recorder:
        for row in rows:
            fields: dict[str, str | None] = {
                "name": row["name"],
                "adscout_lead_id": row["lead_id"],
                "adscout_segment": segment.segment_id,
                "adscout_source": row["source"],
                "adscout_agent_version": row["agent_version"],
                "adscout_prompt_version": row["prompt_version"],
                "adscout_score": latest(connection, "scores", "score", row["lead_id"]),
                "adscout_brief_summary": latest(connection, "briefs", "summary", row["lead_id"]),
                "adscout_draft_subject": row["subject"],
                "adscout_approval_id": row["approval_id"],
                "adscout_approver_kind": row["approver_kind"],
            }
            result = write_account(
                connection,
                run_id=run.run_id,
                lead_id=row["lead_id"],
                approval_id=row["approval_id"],
                domain=row["domain"],
                fields=fields,
            )
            detail = f"{result.operation} on the local fake CRM"
            if result.skipped:
                detail += f"; kept the person's value of {', '.join(result.skipped)}"
            recorder.outcomes.append(
                Outcome(
                    lead_id=row["lead_id"],
                    outcome="kept",
                    flag="crm_conflict" if result.skipped else None,
                    detail=detail,
                )
            )
    return run.run_id
