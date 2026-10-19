"""`python -m evals score-compare`: the scoring tier evaluation (design decision 19).

Scores a segment's stored enrichments on Haiku and on Sonnet, each with the same repeats, as
two runs of kind `eval` sharing one spend cap; then checks both against the owner's labels
and applies the predeclared tier rule. The report goes to `evals/runs/` with both run IDs,
the labels' hash and every number; one cited as evidence is committed under
`evals/evidence/`. Model calls go through the same adapter as the pipeline: scripted,
replayed or live with --live and a cap.
"""

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from adscout.config import SegmentConfig
from adscout.llm.budget import SpendLedger
from adscout.llm.invoke import HAIKU, SONNET
from adscout.pipeline.models import ModelChoice
from adscout.pipeline.rescore import run_rescore
from evals.runner import RUNS
from evals.score_check import Company, Labels, report, tier_decision

ARMS = {"haiku": HAIKU, "sonnet": SONNET}


def companies(
    connection: sqlite3.Connection, run_id: str, labels: Labels
) -> tuple[list[Company], list[str]]:
    """Each scored lead of a run with its label; also the domains that have no label."""
    rows = connection.execute(
        "SELECT o.lead_id, c.domain, o.outcome, o.reason FROM lead_step_outcomes AS o "
        "JOIN leads AS l ON l.lead_id = o.lead_id "
        "JOIN companies AS c ON c.company_id = l.company_id "
        "WHERE o.run_id = ? AND o.step = 'score' ORDER BY c.domain",
        (run_id,),
    ).fetchall()
    found: list[Company] = []
    unlabelled: list[str] = []
    for row in rows:
        label = labels.by_domain.get(row["domain"])
        if label is None:
            unlabelled.append(row["domain"])
            continue
        samples = connection.execute(
            "SELECT score, reasons_json FROM scores WHERE run_id = ? AND lead_id = ? "
            "ORDER BY sample",
            (run_id, row["lead_id"]),
        ).fetchall()
        found.append(
            Company(
                domain=row["domain"],
                label=label,
                outcome="qualified" if row["outcome"] == "kept" else str(row["reason"]),
                scores=[sample["score"] for sample in samples],
                ratings=[
                    {
                        item["criterion"]: item["rating"]
                        for item in json.loads(sample["reasons_json"])
                    }
                    for sample in samples
                ],
            )
        )
    return found, unlabelled


def score_compare(
    connection: sqlite3.Connection,
    segment: SegmentConfig,
    labels: Labels,
    choices: dict[str, ModelChoice],
    *,
    repeats: int,
    cap_usd: Decimal | None,
) -> dict[str, Any]:
    """Both arms under one cap; `choices` gives each arm its scripted, replay or live mode."""
    if segment.score_threshold is None:
        raise ValueError(f"segment {segment.segment_id} has no score threshold")
    ledger = SpendLedger(cap_usd)
    result: dict[str, Any] = {
        "segment": segment.segment_id,
        "labels": {"path": labels.path, "sha256": labels.sha256, "labelled": len(labels.by_domain)},
        "repeats": repeats,
        "cap_usd": str(cap_usd) if cap_usd is not None else None,
        "runs": {},
    }
    for arm, model in ARMS.items():
        run_id = run_rescore(
            connection,
            segment,
            choices[arm],
            model=model,
            repeats=repeats,
            kind="eval",
            ledger=ledger,
        )
        scored, unlabelled = companies(connection, run_id, labels)
        result["runs"][arm] = run_id
        result[arm] = report(scored, segment.score_threshold)
        result[arm]["unlabelled"] = unlabelled
    result["spent_usd"] = str(ledger.spent_usd)
    result["decision"] = tier_decision(result["haiku"], result["sonnet"])
    return result


def write_report(result: dict[str, Any], runs: Path | None = None) -> Path:
    runs = runs or RUNS
    runs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = runs / f"score-compare-{result['segment']}-{stamp}.json"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return path
