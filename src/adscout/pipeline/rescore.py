"""`adscout rescore`: score a segment's stored enrichments again, as a run of kind `rescore`.

Used when the tier evaluation picks another scoring model (design decision 19) or a prompt
changes. It reads each lead's latest real enrichment, applies the profile rules again (they
are code, so the same leads pass), and makes scoring calls only: no page, Wikidata or EDGAR
read and no extraction.
"""

import json
import sqlite3
from functools import partial
from typing import Any

from adscout.config import SegmentConfig
from adscout.llm.adapter import CallSink
from adscout.llm.prompts import load_prompt, prompt_set_version
from adscout.pipeline.contracts import Lead
from adscout.pipeline.models import ModelChoice, build_adapter, price_snapshot
from adscout.pipeline.recorder import Run
from adscout.pipeline.run import require_migrated, segment_snapshot
from adscout.rules import apply_rules
from adscout.scoring import Scorer
from adscout.scoring import store as store_scores

NOT_READ = "a rescore reads stored enrichments only"


def stored_enrichments(
    connection: sqlite3.Connection, segment_id: str
) -> list[tuple[Lead, dict[str, Any]]]:
    """Each lead's latest real enrichment in the segment, as chosen field values."""
    rows = connection.execute(
        "SELECT l.lead_id, l.company_id, c.domain, c.name, e.fields_json "
        "FROM enrichments AS e JOIN leads AS l ON l.lead_id = e.lead_id "
        "JOIN companies AS c ON c.company_id = l.company_id "
        "WHERE l.segment_id = ? AND e.implementation = 'real' AND e.enrichment_id = ("
        "  SELECT max(latest.enrichment_id) FROM enrichments AS latest "
        "  WHERE latest.lead_id = l.lead_id AND latest.implementation = 'real') "
        "ORDER BY c.domain",
        (segment_id,),
    ).fetchall()
    found = []
    for row in rows:
        lead = Lead(
            lead_id=row["lead_id"],
            company_id=row["company_id"],
            domain=row["domain"],
            name=row["name"],
        )
        found.append((lead, json.loads(row["fields_json"]).get("fields", {})))
    return found


def run_rescore(
    connection: sqlite3.Connection,
    segment: SegmentConfig,
    choice: ModelChoice,
    *,
    model: str,
    repeats: int = 1,
) -> str:
    require_migrated(connection)
    choice.check()
    leads = stored_enrichments(connection, segment.segment_id)
    if not leads:
        raise LookupError(f"segment {segment.segment_id} has no stored real enrichments to rescore")
    run = Run(
        connection,
        "rescore",
        segment.segment_id,
        choice.source,
        {"icp_config_hash": segment_snapshot(segment), "price_table_hash": price_snapshot()},
        null_reasons={
            "seed_list_hash": NOT_READ,
            "stub_script_hash": "a rescore runs no stub",
            "site_list_hash": NOT_READ,
            "media_kit_hash": "a rescore writes no draft",
        },
        calls=CallSink(),
        budgets={"max_spend_usd": float(choice.cap_usd)} if choice.cap_usd else {},
        prompt_version=prompt_set_version(),
        options={
            "model": model,
            "score_repeats": repeats,
            "mode": choice.mode,
            "replay_of": choice.replay_run_id,
        },
    )
    adapter, cache = build_adapter(choice, run)
    try:
        scorer = Scorer(adapter, load_prompt("score"), segment, model=model, repeats=repeats)
        with run.recording():
            passing = [
                (lead, fields) for lead, fields in leads if apply_rules(segment, fields).passed
            ]
            with run.step("score", "real", len(passing)) as recorder:
                for lead, fields in passing:
                    scored = scorer.score(lead, fields, run.run_id)
                    recorder.defer(partial(store_scores, connection, run.run_id, scored, segment))
                    recorder.outcomes.append(scored.outcome)
    finally:
        if cache is not None:
            cache.close()
    return run.run_id
