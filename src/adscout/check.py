"""Independent run check: validate a run from the database alone.

This module reads the run's rows with SQL and never imports the runner, its steps or their
models, so a bug in the runner cannot hide here. It records only the run's validation
outcome and detail.
"""

import hashlib
import itertools
import sqlite3
from dataclasses import dataclass
from typing import Literal

from adscout.db.connection import transaction

PIPELINE_ORDER = ["source", "enrich", "rules", "score", "research", "draft"]
STEPS_BY_KIND = {"pipeline": PIPELINE_ORDER, "approval": ["approve"], "crm_sync": ["crm_sync"]}
STUB_TABLES = ("enrichments", "scores", "briefs", "drafts")
IMMUTABLE = ("lead_id", "segment_id", "source", "prompt_version", "agent_version")


@dataclass(frozen=True)
class CheckResult:
    run_id: str
    outcome: Literal["pass", "fail"]
    problems: tuple[str, ...]

    @property
    def detail(self) -> str:
        return "; ".join(self.problems) if self.problems else "all checks passed"


def conservation(connection: sqlite3.Connection, run_id: str) -> list[str]:
    """Per step: kept + exited = entering, and the outcome rows say the same."""
    problems = []
    for step in connection.execute(
        "SELECT step, status, entering, kept, exited FROM step_runs WHERE run_id = ? ORDER BY seq",
        (run_id,),
    ).fetchall():
        if step["status"] != "succeeded":
            continue
        name, entering, kept, exited = step["step"], step["entering"], step["kept"], step["exited"]
        if None in (entering, kept, exited) or kept + exited != entering:
            problems.append(f"{name}: kept {kept} + exited {exited} != entering {entering}")
        counted = dict.fromkeys(("kept", "exited"), 0) | {
            row["outcome"]: row["n"]
            for row in connection.execute(
                "SELECT outcome, count(*) AS n FROM lead_step_outcomes "
                "WHERE run_id = ? AND step = ? GROUP BY outcome",
                (run_id, name),
            ).fetchall()
        }
        if (counted["kept"], counted["exited"]) != (kept, exited):
            problems.append(
                f"{name}: outcome rows say {counted['kept']} kept and {counted['exited']} "
                f"exited, the step says {kept} and {exited}"
            )
    return problems


def funnel_shape(connection: sqlite3.Connection, run_id: str, kind: str) -> list[str]:
    """Steps run in the declared order, entering never rises, and survivors carry on."""
    steps = connection.execute(
        "SELECT step, status, entering, kept FROM step_runs WHERE run_id = ? ORDER BY seq",
        (run_id,),
    ).fetchall()
    problems = []
    names = [step["step"] for step in steps]
    expected = STEPS_BY_KIND.get(kind, [])
    if names != expected[: len(names)]:
        problems.append(f"steps ran as {names}, expected the order {expected}")
    for before, after in itertools.pairwise(steps):
        if after["entering"] is None or before["entering"] is None:
            continue
        if after["entering"] > before["entering"]:
            problems.append(
                f"{after['step']}: entering {after['entering']} exceeds {before['step']}'s "
                f"{before['entering']}"
            )
        if before["status"] == "succeeded" and after["entering"] != before["kept"]:
            problems.append(
                f"{after['step']}: entering {after['entering']} differs from {before['step']}'s "
                f"kept {before['kept']}"
            )
    return problems


def labelling(connection: sqlite3.Connection, run_id: str) -> list[str]:
    """Rows a stub wrote say `stub`; stub briefs carry no claims; stub details say so."""
    problems = []
    stub_steps = {
        row[0]
        for row in connection.execute(
            "SELECT step FROM step_runs WHERE run_id = ? AND implementation = 'stub'", (run_id,)
        )
    }
    for table in STUB_TABLES:
        unlabelled = connection.execute(
            f"SELECT count(*) FROM {table} WHERE run_id = ? AND implementation != 'stub'",  # noqa: S608
            (run_id,),
        ).fetchone()[0]
        if unlabelled and stub_steps:
            problems.append(f"{table}: {unlabelled} rows from a stub run are not labelled stub")
    claims = connection.execute(
        "SELECT count(*) FROM briefs WHERE run_id = ? AND implementation = 'stub' "
        "AND claims_json != '[]'",
        (run_id,),
    ).fetchone()[0]
    if claims:
        problems.append(f"briefs: {claims} stub briefs carry claims")
    for row in connection.execute(
        "SELECT o.step, o.implementation, o.detail FROM lead_step_outcomes AS o WHERE o.run_id = ?",
        (run_id,),
    ).fetchall():
        if row["step"] in stub_steps and row["implementation"] != "stub":
            problems.append(f"{row['step']}: an outcome of a stub step is not labelled stub")
        elif row["implementation"] == "stub" and not row["detail"].startswith("stub:"):
            problems.append(f"{row['step']}: a stub outcome's detail does not say it is a stub")
    return sorted(set(problems))


def lead_fields(connection: sqlite3.Connection, run_id: str) -> list[str]:
    """Every lead the run touched has all its immutable source fields."""
    problems = []
    for lead in connection.execute(
        "SELECT DISTINCT l.* FROM leads AS l JOIN lead_step_outcomes AS o "
        "ON o.lead_id = l.lead_id WHERE o.run_id = ?",
        (run_id,),
    ).fetchall():
        missing = [name for name in IMMUTABLE if not lead[name]]
        if missing or len(lead["lead_id"]) != 36 or not lead["created_run_id"]:
            problems.append(f"lead {lead['lead_id']}: missing {missing or 'created_run_id'}")
    return problems


def crm_writes(connection: sqlite3.Connection, run_id: str) -> list[str]:
    """Every CRM write belongs to an approved lead whose draft still matches the approval."""
    problems = []
    for write in connection.execute(
        "SELECT w.operation_id, w.lead_id, a.lead_id AS approved_lead, a.decision, "
        "a.draft_sha256, d.body FROM crm_writes AS w "
        "LEFT JOIN approvals AS a ON a.approval_id = w.approval_id "
        "LEFT JOIN drafts AS d ON d.draft_id = a.draft_id WHERE w.run_id = ?",
        (run_id,),
    ).fetchall():
        body = write["body"]
        valid = (
            write["decision"] == "approved"
            and write["approved_lead"] == write["lead_id"]
            and body is not None
            and hashlib.sha256(body.encode("utf-8")).hexdigest() == write["draft_sha256"]
        )
        if not valid:
            problems.append(f"CRM write {write['operation_id']} has no valid approval")
    return problems


# Parent span IDs are not foreign keys, as in OpenTelemetry, so the check follows them.
TRACED = {
    "spans": "SELECT span_id, trace_id, parent_span_id, lead_id FROM spans WHERE run_id = ?",
    "model_calls": (
        "SELECT span_id, trace_id, parent_span_id, lead_id FROM model_calls WHERE run_id = ?"
    ),
    "source_calls": (
        "SELECT span_id, trace_id, parent_span_id, lead_id FROM source_calls WHERE run_id = ?"
    ),
}


def trace_tree(connection: sqlite3.Connection, run_id: str) -> list[str]:
    """Every span and call is in its lead's trace, under a span recorded in that trace."""
    spans = dict(
        connection.execute("SELECT span_id, trace_id FROM spans WHERE run_id = ?", (run_id,))
    )
    problems = []
    for table, query in TRACED.items():
        for row in connection.execute(query, (run_id,)):
            if row["trace_id"] != row["lead_id"].replace("-", ""):
                problems.append(f"{table} span {row['span_id']}: not in its lead's trace")
            parent = row["parent_span_id"]
            if parent is not None and spans.get(parent) != row["trace_id"]:
                problems.append(
                    f"{table} span {row['span_id']}: parent {parent} is not a span in its trace"
                )
    return problems


def check_run(connection: sqlite3.Connection, run_id: str) -> CheckResult:
    """Validate one run and record the outcome on it."""
    run = connection.execute("SELECT kind, status FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        raise LookupError(f"no run {run_id}")
    problems: list[str] = []
    if run["status"] == "running":
        problems.append("the run is still running")
    if run["status"] == "succeeded":
        expected = STEPS_BY_KIND[run["kind"]]
        ran = [
            row[0]
            for row in connection.execute(
                "SELECT step FROM step_runs WHERE run_id = ? AND status = 'succeeded' ORDER BY seq",
                (run_id,),
            )
        ]
        if ran != expected:
            problems.append(f"a succeeded {run['kind']} run must complete {expected}; got {ran}")
    problems += conservation(connection, run_id)
    problems += funnel_shape(connection, run_id, run["kind"])
    problems += labelling(connection, run_id)
    problems += lead_fields(connection, run_id)
    problems += crm_writes(connection, run_id)
    problems += trace_tree(connection, run_id)
    result = CheckResult(run_id, "fail" if problems else "pass", tuple(problems))
    with transaction(connection):
        connection.execute(
            "UPDATE runs SET validation_outcome = ?, validation_detail = ? WHERE run_id = ?",
            (result.outcome, result.detail, run_id),
        )
    return result
