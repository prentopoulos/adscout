"""Typed contracts between the runner and its steps.

A step takes the leads that entered it and returns one outcome per lead plus whatever it
produced. Later phases replace a stub step with a real one behind the same contract.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

PipelineStep = Literal["source", "enrich", "rules", "score", "research", "draft"]
Step = Literal["source", "enrich", "rules", "score", "research", "draft", "approve", "crm_sync"]
STUB_STEPS: tuple[PipelineStep, ...] = ("enrich", "rules", "score", "research", "draft")
PIPELINE_STEPS: tuple[PipelineStep, ...] = ("source", *STUB_STEPS)
ExitReason = Literal[
    "duplicate",
    "excluded",
    "out_of_profile",
    "missing_key_fields",
    "below_threshold",
    "draft_failed",
    "rejected",
]
Flag = Literal["research_partial", "crm_conflict"]
Implementation = Literal["stub", "real"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Lead(Contract):
    lead_id: str = Field(min_length=36, max_length=36)
    company_id: int
    domain: str
    name: str


class Outcome(Contract):
    """What happened to one lead at one step."""

    lead_id: str
    outcome: Literal["kept", "exited"]
    reason: ExitReason | None = None
    flag: Flag | None = None
    detail: str = Field(min_length=1)
    seed_row: int | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.outcome == "exited") != (self.reason is not None):
            raise ValueError("an exit needs a reason, and only an exit has one")
        if self.outcome == "exited" and self.flag is not None:
            raise ValueError("only a kept lead carries a flag")
        return self


class Enrichment(Contract):
    lead_id: str
    fields: dict[str, str] = {}
    missing_fields: list[str] = []


class Score(Contract):
    lead_id: str
    score: float | None
    reasons: list[str] = Field(min_length=1)
    null_reasons: dict[str, str] = {}

    @model_validator(mode="after")
    def explained(self) -> Self:
        if self.score is None and "score" not in self.null_reasons:
            raise ValueError("a null score needs a reason")
        return self


class Claim(Contract):
    """One factual claim in a brief, with the page it came from (§5)."""

    text: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https?://")


class Brief(Contract):
    lead_id: str
    status: Literal["complete", "partial"]
    summary: str = Field(min_length=1)
    claims: list[Claim] = []


class Draft(Contract):
    lead_id: str
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    status: Literal["pending_approval", "failed_checks"]


class StepOutput(Contract):
    """Everything one step produced: an outcome per entering lead, and its stored outputs."""

    outcomes: list[Outcome]
    enrichments: list[Enrichment] = []
    scores: list[Score] = []
    briefs: list[Brief] = []
    drafts: list[Draft] = []

    def check_against(self, entering: list[Lead]) -> None:
        """Every entering lead gets exactly one outcome, and no other lead does."""
        expected = sorted(lead.lead_id for lead in entering)
        got = sorted(outcome.lead_id for outcome in self.outcomes)
        if expected != got:
            raise ValueError("a step must return exactly one outcome per entering lead")
