"""The end-of-run cost table: calls, tokens, searches, cost and time by step, role and model.

Actual spend only: a replayed call costs 0 here, its original cost stays on its row. A lead
counts once the run carried it past `source`. A qualified lead passed the rules and scored
at or above the threshold in this run (design decision 4), so its real `score` outcome is
`kept`; near misses sent to a person and stub runs never qualify.
"""

import json
import sqlite3
from decimal import Decimal
from typing import Any

NO_LEADS = "no leads"
NO_QUALIFIED = "no qualified leads"
# Kinds whose runs end with the table; approvals and CRM syncs call no model.
COSTED_KINDS = ("pipeline", "rescore", "eval")

GROUPS = (
    "SELECT m.step, m.agent_name AS role, m.model, count(*) AS calls, "
    "sum(coalesce(m.input_tokens, 0) + coalesce(m.cache_read_tokens, 0) "
    "+ coalesce(m.cache_write_tokens, 0)) AS input_tokens, "
    "sum(coalesce(m.cache_read_tokens, 0)) AS cache_read_tokens, "
    "sum(coalesce(m.output_tokens, 0)) AS output_tokens, "
    "sum(m.web_search_requests) AS searches, "
    "group_concat(m.cost_usd, ' ') AS costs, "
    "sum(coalesce(m.latency_ms, 0)) AS latency_ms "
    "FROM model_calls AS m JOIN step_runs AS s ON s.run_id = m.run_id AND s.step = m.step "
    "WHERE m.run_id = ? GROUP BY s.seq, m.step, m.agent_name, m.model "
    "ORDER BY s.seq, m.agent_name, m.model"
)
LEADS = (
    "SELECT count(DISTINCT lead_id) FROM lead_step_outcomes "
    "WHERE run_id = ? AND NOT (step = 'source' AND outcome = 'exited')"
)
QUALIFIED = (
    "SELECT count(DISTINCT lead_id) FROM lead_step_outcomes "
    "WHERE run_id = ? AND step = 'score' AND outcome = 'kept' AND implementation = 'real'"
)
COUNTS = ("calls", "input_tokens", "cache_read_tokens", "output_tokens", "searches")


def cost_summary(connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    """The run's spend from its `model_calls` rows, with cost per lead and qualified lead."""
    rows: list[dict[str, Any]] = []
    for group in connection.execute(GROUPS, (run_id,)):
        # Summed as decimals: a float sum of many small prices drifts in the last digits.
        cost = sum((Decimal(str(float(c))) for c in group["costs"].split()), Decimal(0))
        rows.append(
            {key: group[key] for key in ("step", "role", "model", *COUNTS)}
            | {"cost_usd": str(cost), "seconds": round(group["latency_ms"] / 1000, 3)}
        )
    total_cost = sum((Decimal(row["cost_usd"]) for row in rows), Decimal(0))
    total = {key: sum(row[key] for row in rows) for key in COUNTS} | {
        "cost_usd": str(total_cost),
        "seconds": round(sum(row["seconds"] for row in rows), 3),
    }
    leads = connection.execute(LEADS, (run_id,)).fetchone()[0]
    qualified = connection.execute(QUALIFIED, (run_id,)).fetchone()[0]
    reasons = {}
    if not leads:
        reasons["cost_per_lead_usd"] = NO_LEADS
    if not qualified:
        reasons["cost_per_qualified_lead_usd"] = NO_QUALIFIED
    return {
        "rows": rows,
        "total": total,
        "leads": leads,
        "qualified_leads": qualified,
        "cost_per_lead_usd": str(round(total_cost / leads, 6)) if leads else None,
        "cost_per_qualified_lead_usd": (
            str(round(total_cost / qualified, 6)) if qualified else None
        ),
        "null_reasons": reasons,
    }


def store_cost_summary(connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    summary = cost_summary(connection, run_id)
    connection.execute(
        "UPDATE runs SET cost_summary_json = ? WHERE run_id = ?",
        (json.dumps(summary, sort_keys=True), run_id),
    )
    return summary


def cost_table(summary: dict[str, Any]) -> str:
    """The stored summary as a terminal table."""
    header = (
        f"{'step':<9} {'role':<16} {'model':<18} {'calls':>5} {'input':>9} {'cached':>9} "
        f"{'output':>8} {'searches':>8} {'cost USD':>10} {'seconds':>8}"
    )
    lines = ["cost by step, role and model (actual spend)", header]
    if not summary["rows"]:
        lines.append("no model calls")
    for row in [*summary["rows"], {"step": "total", "role": "", "model": ""} | summary["total"]]:
        lines.append(
            f"{row['step']:<9} {row['role']:<16} {row['model']:<18} {row['calls']:>5} "
            f"{row['input_tokens']:>9} {row['cache_read_tokens']:>9} {row['output_tokens']:>8} "
            f"{row['searches']:>8} {Decimal(row['cost_usd']):>10.6f} {row['seconds']:>8.3f}"
        )
    for key, label, count in (
        ("cost_per_lead_usd", "cost per lead", f"{summary['leads']} leads"),
        (
            "cost_per_qualified_lead_usd",
            "cost per qualified lead",
            f"{summary['qualified_leads']} qualified",
        ),
    ):
        value = summary[key]
        shown = (
            f"${value} ({count})" if value is not None else f"null ({summary['null_reasons'][key]})"
        )
        lines.append(f"{label}: {shown}")
    return "\n".join(lines)
