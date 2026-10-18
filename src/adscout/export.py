"""Export one run as JSON Lines: the run, its steps and its lead outcomes.

Fields use an OpenTelemetry GenAI or Langfuse attribute name where one exists and an
`adscout.*` name otherwise, so Phase 5 can send the same fields as trace spans. The GenAI
conventions are still in Development status; `ATTRIBUTES` is the one place to update them.
Checked 2026-10-18: GenAI attributes in the OpenTelemetry semantic-conventions registry
(moved to the semantic-conventions-genai repository), and Langfuse's OpenTelemetry mapping.
"""

import json
import sqlite3
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from adscout.ids import ROOT

EVIDENCE = ROOT / "evidence" / "runs"
MINUTES_NULL = "stub timing is not a measurement; defined in the evaluation plan"

# Column → exported attribute. A run maps to a Langfuse session, a step to a span.
ATTRIBUTES = {
    "run_id": "langfuse.session.id",
    "agent_version": "langfuse.release",
    "model": "gen_ai.request.model",
    "input_tokens": "gen_ai.usage.input_tokens",
    "output_tokens": "gen_ai.usage.output_tokens",
    "cost_usd": "gen_ai.usage.cost",
}


class ExportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    session_id: str = Field(alias="langfuse.session.id")
    null_reasons: dict[str, str] = {}


class RunRecord(ExportRecord):
    record: Literal["run"]
    kind: str = Field(alias="adscout.run.kind")
    segment_id: str = Field(alias="adscout.segment.id")
    status: str = Field(alias="adscout.run.status")
    started_at: str = Field(alias="adscout.run.started_at")
    ended_at: str | None = Field(alias="adscout.run.ended_at")
    error_category: str | None = Field(alias="adscout.run.error_category")
    validation_outcome: str = Field(alias="adscout.validation.outcome")
    validation_detail: str | None = Field(alias="adscout.validation.detail")
    source: str = Field(alias="adscout.source")
    code_revision: str = Field(alias="adscout.code.revision")
    code_dirty: bool = Field(alias="adscout.code.dirty")
    lock_digest: str = Field(alias="adscout.lock.digest")
    package_version: str = Field(alias="adscout.package.version")
    agent_version: str = Field(alias="langfuse.release")
    prompt_version: str = Field(alias="adscout.prompt.version")
    python_version: str = Field(alias="adscout.python.version")
    platform: str = Field(alias="adscout.platform")
    schema_version: int = Field(alias="adscout.schema.version")
    icp_config_hash: str | None = Field(alias="adscout.icp_config_hash")
    seed_list_hash: str | None = Field(alias="adscout.seed_list_hash")
    stub_script_hash: str | None = Field(alias="adscout.stub_script_hash")
    budgets: dict[str, int] = Field(alias="adscout.budgets")
    minutes_per_account: float | None = Field(alias="adscout.minutes_per_account")


class StepRecord(ExportRecord):
    record: Literal["step"]
    step: str = Field(alias="adscout.step.name")
    seq: int = Field(alias="adscout.step.seq")
    implementation: str = Field(alias="adscout.step.implementation")
    status: str = Field(alias="adscout.step.status")
    started_at: str = Field(alias="adscout.step.started_at")
    ended_at: str | None = Field(alias="adscout.step.ended_at")
    duration_ms: int | None = Field(alias="adscout.step.duration_ms")
    entering: int | None = Field(alias="adscout.step.entering")
    kept: int | None = Field(alias="adscout.step.kept")
    exited: int | None = Field(alias="adscout.step.exited")
    model: str | None = Field(alias="gen_ai.request.model")
    input_tokens: int | None = Field(alias="gen_ai.usage.input_tokens")
    output_tokens: int | None = Field(alias="gen_ai.usage.output_tokens")
    cost_usd: float | None = Field(alias="gen_ai.usage.cost")


class OutcomeRecord(ExportRecord):
    record: Literal["lead_outcome"]
    lead_id: str = Field(alias="adscout.lead.id")
    domain: str = Field(alias="adscout.company.domain")
    step: str = Field(alias="adscout.step.name")
    seed_row: int | None = Field(alias="adscout.seed_row")
    outcome: str = Field(alias="adscout.outcome")
    reason: str | None = Field(alias="adscout.exit_reason")
    flag: str | None = Field(alias="adscout.flag")
    detail: str = Field(alias="adscout.detail")
    implementation: str = Field(alias="adscout.step.implementation")


class ExportLine(
    RootModel[Annotated[RunRecord | StepRecord | OutcomeRecord, Field(discriminator="record")]]
):
    """One line of a run export."""


class ExportRefused(RuntimeError):
    """The export would break an evidence rule; nothing was written."""


def build[Model: BaseModel](model: type[Model], data: dict[str, Any]) -> Model:
    """Validate the columns the export record defines; other columns stay out."""
    return model.model_validate(
        {key: value for key, value in data.items() if key in model.model_fields}
    )


def renamed_reasons(reasons: dict[str, str]) -> dict[str, str]:
    return {ATTRIBUTES.get(name, name): reason for name, reason in reasons.items()}


def export_lines(connection: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        raise LookupError(f"no run {run_id}")
    run_reasons = json.loads(run["null_reasons_json"]) | {
        "adscout.minutes_per_account": MINUTES_NULL
    }
    records: list[BaseModel] = [
        build(
            RunRecord,
            dict(run)
            | {
                "record": "run",
                "session_id": run_id,
                "code_dirty": bool(run["code_dirty"]),
                "budgets": json.loads(run["budgets_json"]),
                "minutes_per_account": None,
                "null_reasons": renamed_reasons(run_reasons),
            },
        )
    ]
    for step in connection.execute(
        "SELECT * FROM step_runs WHERE run_id = ? ORDER BY seq", (run_id,)
    ).fetchall():
        records.append(
            build(
                StepRecord,
                dict(step)
                | {
                    "record": "step",
                    "session_id": run_id,
                    "null_reasons": renamed_reasons(json.loads(step["null_reasons_json"])),
                },
            )
        )
    for outcome in connection.execute(
        "SELECT o.*, c.domain FROM lead_step_outcomes AS o "
        "JOIN leads AS l ON l.lead_id = o.lead_id "
        "JOIN companies AS c ON c.company_id = l.company_id "
        "WHERE o.run_id = ? ORDER BY o.outcome_id",
        (run_id,),
    ).fetchall():
        records.append(
            build(OutcomeRecord, dict(outcome) | {"record": "lead_outcome", "session_id": run_id})
        )
    return [record.model_dump(mode="json", by_alias=True) for record in records]


def write_export(connection: sqlite3.Connection, run_id: str, out: Path) -> Path:
    """Write a new export file; evidence exports need a clean tree and never overwrite."""
    run = connection.execute("SELECT code_dirty FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        raise LookupError(f"no run {run_id}")
    if out.resolve().is_relative_to(EVIDENCE.resolve()) and run["code_dirty"]:
        raise ExportRefused(
            f"run {run_id} ran on uncommitted code; evidence must come from a clean tree"
        )
    lines = export_lines(connection, run_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
    return out
