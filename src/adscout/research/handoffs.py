"""Strict typed handoffs between the research lead, the workers and the verifier (decision 26).

Every handoff is a frozen model that refuses unknown fields. Worker output is untrusted: it
is validated here, its claims are checked against the pages fetched in the run, and only
verified claims, under IDs that code assigns, reach the merge and the writer.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Topic = Literal["audience_channels", "ad_activity", "launches"]
TOPICS: tuple[Topic, ...] = ("audience_channels", "ad_activity", "launches")
BriefStatus = Literal["complete", "partial", "failed"]
Design = Literal["multi", "single"]


class Handoff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkerTask(Handoff):
    lead_id: str
    worker: str
    topics: list[Topic] = Field(min_length=1)
    company: str
    domain: str
    questions: list[str] = Field(min_length=1, max_length=9)
    seed_urls: list[str] = []


class Claim(Handoff):
    """A claim as a worker submits it: one fact, the page that states it, and a quote."""

    topic: Topic
    text: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=2000)
    quote: str = Field(max_length=300)


class WorkerFindings(Handoff):
    worker: str
    claims: list[Claim] = []
    gaps: list[str] = []
    stopped_because: str


class VerifiedClaim(Handoff):
    """A claim after the verifier, with the ID the merge and the writer cite."""

    claim_id: str
    worker: str
    claim: Claim
    fetch_call_id: str | None
    url_fetched_in_run: bool
    quote_found: bool
    numbers_ok: bool
    names_individual: bool = False
    verifier_version: str

    @property
    def verified(self) -> bool:
        return (
            self.url_fetched_in_run
            and self.quote_found
            and self.numbers_ok
            and not self.names_individual
        )


class SummaryPoint(Handoff):
    text: str = Field(min_length=1, max_length=400)
    claim_ids: list[str] = Field(min_length=1)


class Brief(Handoff):
    status: BriefStatus
    design: Design
    summary_points: list[SummaryPoint] = []
    claim_ids: list[str] = []
    gaps: list[str] = []
    caps_hit: list[str] = []

    @model_validator(mode="after")
    def check(self) -> Self:
        cited = {claim_id for point in self.summary_points for claim_id in point.claim_ids}
        unknown = sorted(cited - set(self.claim_ids))
        if unknown:
            raise ValueError(f"summary points cite claims the brief does not hold: {unknown}")
        return self
