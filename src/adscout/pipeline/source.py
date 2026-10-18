"""The real `source` step: load seeds, dedupe by domain, apply exclusions and create leads.

Every seed row enters. A row whose domain repeats an earlier row, already has a lead in the
segment or is already in the CRM exits as `duplicate`; an excluded domain exits as
`excluded`. A company is stored once; a lead is created once per segment, with its source
fields fixed at creation (§5).
"""

import sqlite3

from adscout.config import SeedList, SegmentConfig
from adscout.crm.writer import account_exists
from adscout.db.connection import utc_now
from adscout.ids import uuid7
from adscout.pipeline.contracts import Lead, Outcome
from adscout.pipeline.recorder import PROMPT_VERSION, Run, StepRecorder


def lead_source(segment_id: str, seed_list_hash: str) -> str:
    return f"seed_list:{segment_id}@{seed_list_hash}"


def existing_lead(
    connection: sqlite3.Connection, segment_id: str, domain: str
) -> sqlite3.Row | None:
    row: sqlite3.Row | None = connection.execute(
        "SELECT l.lead_id, l.company_id, l.created_run_id, c.domain, c.name FROM leads AS l "
        "JOIN companies AS c ON c.company_id = l.company_id "
        "WHERE l.segment_id = ? AND c.domain = ?",
        (segment_id, domain),
    ).fetchone()
    return row


def company_id_for(connection: sqlite3.Connection, run_id: str, domain: str, name: str) -> int:
    row = connection.execute("SELECT company_id FROM companies WHERE domain = ?", (domain,))
    found = row.fetchone()
    if found:
        return int(found["company_id"])
    cursor = connection.execute(
        "INSERT INTO companies (domain, name, created_run_id, created_at) VALUES (?, ?, ?, ?)",
        (domain, name, run_id, utc_now()),
    )
    return int(cursor.lastrowid or 0)


def source(
    run: Run,
    recorder: StepRecorder,
    segment: SegmentConfig,
    seeds: SeedList,
    seed_list_hash: str,
) -> list[Lead]:
    """Record one outcome per seed row and return the leads that go on."""
    connection = run.connection
    excluded = segment.excluded_domains
    first_row: dict[str, int] = {}
    survivors: list[Lead] = []
    for number, row in enumerate(seeds.rows, start=2):
        if row.domain in first_row:
            earlier = existing_lead(connection, segment.segment_id, row.domain)
            if earlier is None:  # the earlier row always created or found the lead
                raise RuntimeError(f"no lead for repeated domain {row.domain}")
            recorder.outcomes.append(
                Outcome(
                    lead_id=earlier["lead_id"],
                    outcome="exited",
                    reason="duplicate",
                    detail=f"repeats seed row {first_row[row.domain]}",
                    seed_row=number,
                )
            )
            continue
        first_row[row.domain] = number
        found = existing_lead(connection, segment.segment_id, row.domain)
        if found:
            recorder.outcomes.append(
                Outcome(
                    lead_id=found["lead_id"],
                    outcome="exited",
                    reason="duplicate",
                    detail=f"already a lead in this segment since run {found['created_run_id']}",
                    seed_row=number,
                )
            )
            continue
        in_crm = account_exists(connection, row.domain)
        company_id = company_id_for(connection, run.run_id, row.domain, row.name)
        lead = Lead(lead_id=str(uuid7()), company_id=company_id, domain=row.domain, name=row.name)
        connection.execute(
            "INSERT INTO leads (lead_id, segment_id, company_id, source, prompt_version, "
            "agent_version, created_run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lead.lead_id,
                segment.segment_id,
                company_id,
                lead_source(segment.segment_id, seed_list_hash),
                PROMPT_VERSION,
                run.agent_version,
                run.run_id,
                utc_now(),
            ),
        )
        if row.domain in excluded:
            outcome = Outcome(
                lead_id=lead.lead_id,
                outcome="exited",
                reason="excluded",
                detail="domain is in the segment's exclusions",
                seed_row=number,
            )
        elif in_crm:
            outcome = Outcome(
                lead_id=lead.lead_id,
                outcome="exited",
                reason="duplicate",
                detail="already an account in the CRM",
                seed_row=number,
            )
        else:
            outcome = Outcome(
                lead_id=lead.lead_id, outcome="kept", detail="new lead", seed_row=number
            )
            survivors.append(lead)
        recorder.outcomes.append(outcome)
    return survivors
