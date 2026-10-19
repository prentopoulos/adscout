"""The real `score` step: a rubric rated by a model, combined and routed by code.

The model rates every criterion of the segment 1 to 5 against its written anchors, each with
a short reason citing the lead's enriched fields (design decision 23). Code checks the
answer: every criterion exactly once, ratings 1 to 5, citations only of fields the lead has
and the criterion allows; a violation is invalid output, retried once and then sent to the
other tier. Code combines the ratings as the weighted mean of (rating - 1) x 25, so the
score runs 0 to 100, and routes: at or above the threshold to research; from the near-miss
floor up to the threshold out as `near_miss` for a person; below it out as
`below_threshold`; no valid answer after retry and fallback out as `score_failed`.
With repeats, every sample is recorded and the first decides the route.
"""

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from adscout.config import Criterion, SegmentConfig
from adscout.db.connection import utc_now
from adscout.llm.adapter import CallContext, Effort, ModelAdapter, ModelCallFailed, ModelRequest
from adscout.llm.invoke import SONNET, CallsFailed, InvalidOutput, Invoked, invoke
from adscout.llm.prompts import Prompt, data_block, request_for
from adscout.pipeline.contracts import Lead, Outcome
from adscout.spans import SpanStatus, step_span

MAX_TOKENS = 1_200
EFFORT: Effort = "low"


@dataclass(frozen=True)
class Rating:
    criterion: str
    rating: int
    reason: str
    cited_fields: list[str]


@dataclass(frozen=True)
class Sample:
    number: int
    ratings: list[Rating] | None
    score: float | None
    call_id: str | None
    call_role: str | None
    model: str | None
    failure: str | None = None


@dataclass(frozen=True)
class Scored:
    lead: Lead
    samples: list[Sample]
    outcome: Outcome

    @property
    def score(self) -> float | None:
        return self.samples[0].score if self.samples else None


def criteria_text(criteria: Sequence[Criterion]) -> str:
    """The rubric as fixed text: each criterion, its allowed fields and its five anchors."""
    blocks = []
    for item in criteria:
        anchors = "\n".join(f"  {rating}: {text}" for rating, text in sorted(item.anchors.items()))
        blocks.append(
            f"### {item.id}: {item.name}\nQuestion: {item.question}\n"
            f"Allowed fields: {', '.join(item.fields)}\nAnchors:\n{anchors}"
        )
    return "## Criteria\n\n" + "\n\n".join(blocks)


def combine(ratings: Sequence[Rating], criteria: Sequence[Criterion]) -> float:
    """The weighted mean of (rating - 1) x 25 over the criteria: 0 to 100."""
    weights = {item.id: item.weight for item in criteria}
    total = sum(weights[rating.criterion] * (rating.rating - 1) * 25 for rating in ratings)
    return round(total / sum(weights.values()), 4)


def parser(criteria: Sequence[Criterion], fields: dict[str, Any]) -> Any:
    """A parse function that turns the answer into ratings or raises InvalidOutput."""
    expected = {item.id: item for item in criteria}

    def parse(result: Any) -> list[Rating]:
        try:
            data = result.json()
        except ValueError as error:
            raise InvalidOutput(f"the answer is not JSON: {error}") from None
        items = data.get("ratings") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise InvalidOutput("the answer has no ratings list")
        ratings: list[Rating] = []
        for item in items:
            if not isinstance(item, dict):
                raise InvalidOutput("a rating is not an object")
            criterion = expected.get(str(item.get("criterion")))
            if criterion is None:
                raise InvalidOutput(f"unknown criterion {item.get('criterion')!r}")
            rating = item.get("rating")
            if isinstance(rating, bool) or rating not in (1, 2, 3, 4, 5):
                raise InvalidOutput(f"{criterion.id}: rating {rating!r} is not 1 to 5")
            cited = item.get("cited_fields") or []
            if not isinstance(cited, list) or not all(isinstance(c, str) for c in cited):
                raise InvalidOutput(f"{criterion.id}: cited_fields is not a list of field IDs")
            outside = sorted(set(cited) - set(criterion.fields))
            if outside:
                raise InvalidOutput(f"{criterion.id} cites fields it may not use: {outside}")
            absent = sorted(name for name in cited if name not in fields)
            if absent:
                raise InvalidOutput(
                    f"{criterion.id} cites fields the lead has no value for: {absent}"
                )
            reason = str(item.get("reason") or "").strip()
            if not reason:
                raise InvalidOutput(f"{criterion.id} gives no reason")
            ratings.append(Rating(criterion.id, int(rating), reason, list(cited)))
        names = [rating.criterion for rating in ratings]
        if sorted(names) != sorted(expected):
            raise InvalidOutput(
                f"criteria rated {sorted(names)}, expected each of {sorted(expected)}"
            )
        return sorted(ratings, key=lambda rating: names.index(rating.criterion))

    return parse


def route(lead_id: str, score: float, segment: SegmentConfig) -> Outcome:
    threshold, floor = segment.score_threshold, segment.near_miss_min
    if threshold is None or floor is None:
        raise ValueError("the segment has no score threshold or near-miss floor")
    shown = f"{score:g}"
    if score >= threshold:
        return Outcome(lead_id=lead_id, outcome="kept", detail=f"score {shown} >= {threshold:g}")
    if score >= floor:
        return Outcome(
            lead_id=lead_id,
            outcome="exited",
            reason="near_miss",
            detail=f"score {shown} is in the near-miss band from {floor:g}; for a person",
        )
    return Outcome(
        lead_id=lead_id,
        outcome="exited",
        reason="below_threshold",
        detail=f"score {shown} < {floor:g}",
    )


@dataclass
class Scorer:
    adapter: ModelAdapter
    prompt: Prompt
    segment: SegmentConfig
    model: str = SONNET  # provisional until the tier evaluation (decision 19)
    repeats: int = 1
    criteria: list[Criterion] = field(init=False)

    def __post_init__(self) -> None:
        if self.segment.criteria is None:
            raise ValueError(f"segment {self.segment.segment_id} has no score criteria")
        if self.repeats < 1:
            raise ValueError("score repeats must be at least 1")
        self.criteria = list(self.segment.criteria)

    def request(self, lead: Lead, fields: dict[str, Any]) -> ModelRequest:
        lead_data = {"company": lead.name, "domain": lead.domain, "fields": fields}
        return request_for(
            self.prompt,
            self.model,
            max_tokens=MAX_TOKENS,
            effort=EFFORT,
            fixed=(criteria_text(self.criteria),),
            user=data_block("lead_data", lead_data),
        )

    def score(self, lead: Lead, fields: dict[str, Any], run_id: str) -> Scored:
        span = step_span(run_id, lead.lead_id, "score")
        agent = span.child("scorer")
        context = CallContext(
            run_id=run_id,
            step="score",
            lead_id=lead.lead_id,
            role="scorer",
            agent_name="scorer",
            prompt_version=self.prompt.version,
            parent_span_id=agent.span_id,
        )
        request = self.request(lead, fields)
        parse = parser(self.criteria, fields)
        samples: list[Sample] = []
        for number in range(1, self.repeats + 1):
            try:
                invoked: Invoked[list[Rating]] = invoke(self.adapter, request, context, parse)
            except (CallsFailed, ModelCallFailed) as error:
                samples.append(Sample(number, None, None, None, None, None, str(error)))
                continue
            samples.append(
                Sample(
                    number,
                    invoked.value,
                    combine(invoked.value, self.criteria),
                    invoked.result.call_id,
                    invoked.call_role,
                    invoked.result.message.model,
                )
            )
        first = samples[0]
        if first.score is None:
            outcome = Outcome(
                lead_id=lead.lead_id,
                outcome="exited",
                reason="score_failed",
                detail=f"no valid score after retry and fallback: {first.failure}",
            )
        else:
            outcome = route(lead.lead_id, first.score, self.segment)
        status: SpanStatus = "failed" if first.score is None else "succeeded"
        self.adapter.sink.add(agent.close(status, f"{len(samples)} samples"))
        self.adapter.sink.add(span.close("succeeded", outcome.detail))
        return Scored(lead, samples, outcome)


def store(
    connection: sqlite3.Connection, run_id: str, scored: Scored, segment: SegmentConfig
) -> None:
    """One `scores` row per sample, with ratings, reasons and the combination."""
    weights = {item.id: item.weight for item in segment.criteria or []}
    for sample in scored.samples:
        ratings = sample.ratings or []
        reasons = [
            {
                "criterion": rating.criterion,
                "rating": rating.rating,
                "reason": rating.reason,
                "cited_fields": rating.cited_fields,
            }
            for rating in ratings
        ]
        combination = [
            {
                "criterion": rating.criterion,
                "rating": rating.rating,
                "weight": weights[rating.criterion],
                "points": (rating.rating - 1) * 25,
            }
            for rating in ratings
        ]
        nulls = {} if sample.score is not None else {"score": f"score_failed: {sample.failure}"}
        connection.execute(
            "INSERT INTO scores (lead_id, run_id, implementation, score, reasons_json, "
            "null_reasons_json, created_at, criteria_json, sample, model_call_id) "
            "VALUES (?, ?, 'real', ?, ?, ?, ?, ?, ?, ?)",
            (
                scored.lead.lead_id,
                run_id,
                sample.score,
                json.dumps(reasons, sort_keys=True),
                json.dumps(nulls, sort_keys=True),
                utc_now(),
                json.dumps(combination, sort_keys=True),
                sample.number,
                sample.call_id,
            ),
        )
