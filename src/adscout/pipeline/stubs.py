"""Phase 1 stub steps, scripted per seed domain by `config/stubs/<segment_id>.yaml`.

A stub never states a fact about a company: its outputs are labelled stubs, briefs carry no
claims and drafts carry no pitch. For a real company the script records why it scripts that
outcome, with sources; the database rows only point at the script.
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from adscout.config import (
    SLUG,
    ConfigError,
    canonical_hash,
    error_text,
    load_yaml,
    normalize_domain,
    reject_contact_data,
)
from adscout.pipeline.contracts import (
    Brief,
    Draft,
    Enrichment,
    ExitReason,
    Flag,
    Lead,
    Outcome,
    PipelineStep,
    Score,
    StepOutput,
)

STUB_VERSION = "stub-1"
# RFC 2606 and RFC 6761 names: a seed on one of these is synthetic, not a real company.
RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost")
RESERVED_DOMAINS = ("example.com", "example.net", "example.org")
STUB_EXIT_REASONS: dict[PipelineStep, tuple[ExitReason, ...]] = {
    "enrich": ("missing_key_fields",),
    "rules": ("out_of_profile",),
    "score": ("below_threshold",),
    "research": (),
    "draft": ("draft_failed",),
}


def is_reserved_domain(domain: str) -> bool:
    return domain.endswith(RESERVED_SUFFIXES) or any(
        domain == name or domain.endswith("." + name) for name in RESERVED_DOMAINS
    )


class StubFailure(RuntimeError):
    """A failure the stub script asked for, to show that failed runs are kept."""


class SourceNote(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str = Field(pattern=r"^https://")
    retrieved: date
    note: str = Field(min_length=1)


class ScriptedExit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["enrich", "rules", "score", "draft"]
    reason: ExitReason

    @model_validator(mode="after")
    def reason_fits_step(self) -> Self:
        if self.reason not in STUB_EXIT_REASONS[self.step]:
            raise ValueError(f"a stub cannot exit at {self.step} with {self.reason}")
        return self


class LeadScript(BaseModel):
    """One seed's scripted path; a lead without an exit needs an approval decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected: str = Field(min_length=1)
    exit: ScriptedExit | None = None
    research_flag: Literal["research_partial"] | None = None
    approval: Literal["approved", "rejected"] | None = None
    rejection_reason: str | None = None
    rationale: str | None = None
    sources: list[SourceNote] = []

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.exit is None and self.approval is None:
            raise ValueError("a lead that reaches a draft needs an approval decision")
        if self.approval == "rejected" and not self.rejection_reason:
            raise ValueError("a rejection needs a rejection_reason")
        return self


class StubScript(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"]
    segment_id: str = Field(pattern=SLUG)
    label: str = Field(min_length=1)
    fail_at_step: PipelineStep | None = None
    leads: dict[str, LeadScript]

    @model_validator(mode="after")
    def real_seeds_cite_sources(self) -> Self:
        for domain, script in self.leads.items():
            if normalize_domain(domain) != domain:
                raise ValueError(f"script domain {domain!r} is not normalized")
            if not is_reserved_domain(domain) and not (script.rationale and script.sources):
                raise ValueError(
                    f"{domain}: a real company's scripted outcome needs a rationale and at "
                    "least one source with its retrieval date"
                )
        return self

    def for_lead(self, lead: Lead) -> LeadScript:
        try:
            return self.leads[lead.domain]
        except KeyError:
            raise ConfigError(f"stub script has no entry for {lead.domain}") from None

    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


def load_stub_script(path: Path) -> StubScript:
    raw = load_yaml(path)
    reject_contact_data(raw, path.name)
    try:
        script = StubScript.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(f"{path.name}: {error_text(error)}") from error
    if script.segment_id != path.stem:
        raise ConfigError(f"{path.name}: segment_id {script.segment_id!r} differs from the file")
    return script


def kept(lead: Lead, script: StubScript, flag: Flag | None = None) -> Outcome:
    return Outcome(lead_id=lead.lead_id, outcome="kept", flag=flag, detail=f"{script.label}")


def scripted_exit(lead: Lead, script: StubScript, step: PipelineStep) -> Outcome | None:
    planned = script.for_lead(lead).exit
    if planned is None or planned.step != step:
        return None
    return Outcome(
        lead_id=lead.lead_id, outcome="exited", reason=planned.reason, detail=script.label
    )


def enrich(leads: list[Lead], script: StubScript) -> StepOutput:
    outcomes = [scripted_exit(lead, script, "enrich") or kept(lead, script) for lead in leads]
    # No fields: a stub states nothing about a company.
    enrichments = [Enrichment(lead_id=lead.lead_id) for lead in leads]
    return StepOutput(outcomes=outcomes, enrichments=enrichments)


def rules(leads: list[Lead], script: StubScript) -> StepOutput:
    return StepOutput(
        outcomes=[scripted_exit(lead, script, "rules") or kept(lead, script) for lead in leads]
    )


def score(leads: list[Lead], script: StubScript) -> StepOutput:
    scores = [
        Score(
            lead_id=lead.lead_id,
            score=None,
            reasons=[script.label],
            null_reasons={"score": "stub step: the scoring rubric and scale arrive in Phase 2"},
        )
        for lead in leads
    ]
    outcomes = [scripted_exit(lead, script, "score") or kept(lead, script) for lead in leads]
    return StepOutput(outcomes=outcomes, scores=scores)


def research(leads: list[Lead], script: StubScript) -> StepOutput:
    briefs, outcomes = [], []
    for lead in leads:
        flag = script.for_lead(lead).research_flag
        briefs.append(
            Brief(
                lead_id=lead.lead_id,
                status="partial" if flag else "complete",
                summary="Stub brief: no research was performed; the research agent arrives "
                "in Phase 3.",
            )
        )
        outcomes.append(kept(lead, script, flag))
    return StepOutput(outcomes=outcomes, briefs=briefs)


def draft(leads: list[Lead], script: StubScript) -> StepOutput:
    drafts, outcomes = [], []
    for lead in leads:
        exit_outcome = scripted_exit(lead, script, "draft")
        drafts.append(
            Draft(
                lead_id=lead.lead_id,
                subject=f"Stub draft for {lead.name}",
                body=(
                    f"Stub draft for lead {lead.lead_id}. No pitch is written until Phase 4; "
                    "this text exists so an approval can be bound to a draft."
                ),
                status="failed_checks" if exit_outcome else "pending_approval",
            )
        )
        outcomes.append(exit_outcome or kept(lead, script))
    return StepOutput(outcomes=outcomes, drafts=drafts)


StubStep = Callable[[list[Lead], StubScript], StepOutput]
STUBS: dict[PipelineStep, StubStep] = {
    "enrich": enrich,
    "rules": rules,
    "score": score,
    "research": research,
    "draft": draft,
}


def run_stub(step: PipelineStep, leads: list[Lead], script: StubScript) -> StepOutput:
    if script.fail_at_step == step:
        raise StubFailure(f"the stub script asks the {step} step to fail")
    output = STUBS[step](leads, script)
    output.check_against(leads)
    return output
