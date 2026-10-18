"""Evaluation case and result-record formats.

The result record follows the adscout-eval-review skill ("Record and compare honestly"):
every result names its inputs, versions, configuration, budgets and platform, and a field
without a value is null with a reason in `null_reasons`, never zero. Model and token fields
borrow OpenTelemetry GenAI attribute names.
"""

import json
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Step = Literal["scaffold", "rules", "enrich", "score", "research", "draft", "injection", "cost"]
Layer = Literal["deterministic", "judged", "operational"]
Label = Literal["normal", "edge", "deliberately_failing"]
Split = Literal["tuning", "held_out"]
Status = Literal["pass", "fail", "not_run", "error"]

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


class Case(BaseModel):
    """One fixed evaluation case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    case_set: str
    case_set_version: str
    step: Step
    layer: Layer
    label: Label
    synthetic: bool
    split: Split
    evaluator: str
    inputs: dict[str, Any]
    expected: dict[str, Any]
    tags: list[str] = []


class Validation(BaseModel):
    """Outcome of checking the output independently of the code that produced it."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["pass", "fail", "not_run"]
    detail: str


class ResultRecord(BaseModel):
    """One case's result in one repetition of one run."""

    model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)

    schema_version: Literal["1"] = "1"
    run_id: str
    case_id: str
    case_set: str
    case_set_version: str
    step: Step
    layer: Layer
    label: Label
    synthetic: bool
    split: Split
    repetition: int = Field(ge=0)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_revision: str
    code_dirty: bool
    lock_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator: str
    evaluator_version: str
    config: dict[str, Any]
    budgets: dict[str, Any]
    platform: str
    python_version: str
    status: Status
    validation: Validation
    metrics: dict[str, float | int | None]
    started_at: AwareDatetime
    duration_s: float = Field(ge=0)
    source: Literal["fixture", "live"]
    model: str | None = Field(alias="gen_ai.request.model")
    prompt_version: str | None
    agent_version: str | None
    input_tokens: int | None = Field(alias="gen_ai.usage.input_tokens", ge=0)
    output_tokens: int | None = Field(alias="gen_ai.usage.output_tokens", ge=0)
    cost_usd: float | None = Field(ge=0)
    segment: str | None
    seed_list_hash: str | None
    icp_config_hash: str | None
    labelled_set_version: str | None
    attribution_rule: str | None
    null_reasons: dict[str, str]

    @model_validator(mode="after")
    def every_null_has_a_reason(self) -> Self:
        missing = [
            info.alias or name
            for name, info in type(self).model_fields.items()
            if getattr(self, name) is None and (info.alias or name) not in self.null_reasons
        ]
        if missing:
            raise ValueError(f"null fields without a reason in null_reasons: {missing}")
        return self


def started_now() -> datetime:
    return datetime.now().astimezone()


SCHEMA_FILES: dict[str, type[BaseModel]] = {
    "case.schema.json": Case,
    "result.schema.json": ResultRecord,
}


def schema_text(model: type[BaseModel]) -> str:
    schema = {"$schema": JSON_SCHEMA_DIALECT, **model.model_json_schema(by_alias=True)}
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
