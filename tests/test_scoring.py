"""The rubric score: combination, routing, citations, retries, repeats and storage."""

import json
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from anthropic.types import Message

from adscout.config import load_segment
from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.ids import uuid7
from adscout.llm.adapter import FakeTransport, ModelAdapter, ModelRequest
from adscout.llm.budget import SpendLedger
from adscout.llm.fakes import fake_message
from adscout.llm.invoke import HAIKU, SONNET
from adscout.llm.prices import load_price_table
from adscout.llm.prompts import cached_prefix, load_prompt
from adscout.pipeline.contracts import Lead
from adscout.pipeline.recorder import Run
from adscout.scoring import Rating, Scorer, combine, criteria_text, route, store

SEGMENT = load_segment(
    Path(__file__).resolve().parent.parent / "config" / "segments" / "gaming-hardware-na.yaml"
)
FIELDS = {
    "categories": ["peripherals"],
    "sells_in": ["CA", "US"],
    "employee_count": {"count": 1500},
    "ad_signals": [{"tag": "meta_pixel", "kind": "ad_pixel", "host": "connect.facebook.net"}],
    "recent_launches": [{"name": "K1", "date": "2026-09", "source_url": "https://alpha.test/n"}],
}
CITES = {
    "audience": ["categories"],
    "ad_activity": ["ad_signals"],
    "budget_capacity": ["employee_count"],
    "recent_launches": ["recent_launches"],
}


def answer(*ratings: int, cites: dict[str, list[str]] | None = None) -> dict[str, Any]:
    order = ["audience", "ad_activity", "budget_capacity", "recent_launches"]
    cited = cites or CITES
    return {
        "ratings": [
            {
                "criterion": name,
                "rating": rating,
                "reason": f"{name} reason",
                "cited_fields": cited[name],
            }
            for name, rating in zip(order, ratings, strict=True)
        ]
    }


def test_combination_is_the_weighted_mean_of_points() -> None:
    criteria = SEGMENT.criteria or []
    ratings = [Rating(c.id, r, "x", []) for c, r in zip(criteria, (5, 3, 3, 1), strict=True)]
    assert combine(ratings, criteria) == 0.35 * 100 + 0.30 * 50 + 0.20 * 50 + 0.15 * 0 == 60.0
    assert combine([Rating(c.id, 1, "x", []) for c in criteria], criteria) == 0
    assert combine([Rating(c.id, 5, "x", []) for c in criteria], criteria) == 100


@pytest.mark.parametrize(
    ("score", "outcome", "reason"),
    [
        (100, "kept", None),
        (60, "kept", None),
        (59.99, "exited", "near_miss"),
        (57.5, "exited", "near_miss"),
        (55, "exited", "near_miss"),
        (54.99, "exited", "below_threshold"),
        (0, "exited", "below_threshold"),
    ],
)
def test_router(score: float, outcome: str, reason: str | None) -> None:
    routed = route("l" * 36, score, SEGMENT)
    assert (routed.outcome, routed.reason) == (outcome, reason)


def test_criteria_text_carries_every_anchor_and_allowed_field() -> None:
    text = criteria_text(SEGMENT.criteria or [])
    assert (
        "### audience: Audience fit" in text and "Allowed fields: ad_signals, sponsorships" in text
    )
    assert text.count("  5: ") == 4


class Models:
    def __init__(self, answers: list[Any]) -> None:
        self.answers = answers

    def __call__(self, request: ModelRequest) -> Message:
        reply = self.answers.pop(0)
        return fake_message(request.model, data=reply, input_tokens=1800, output_tokens=150)


def scorer(answers: list[Any], repeats: int = 1, sink: Any = None) -> tuple[Scorer, FakeTransport]:
    from adscout.llm.adapter import CallSink

    transport = FakeTransport(Models(answers))
    adapter = ModelAdapter(
        transport,
        load_price_table(),
        SpendLedger(None),
        sink if sink is not None else CallSink(),
        today=lambda: date(2026, 10, 19),
    )
    return Scorer(adapter, load_prompt("score"), SEGMENT, repeats=repeats), transport


LEAD = Lead(lead_id=str(uuid7()), company_id=1, domain="alpha.test", name="Alpha Gear")


def test_a_valid_answer_is_combined_and_routed_to_research() -> None:
    scoring, transport = scorer([answer(5, 4, 3, 2)])
    scored = scoring.score(LEAD, FIELDS, "r")
    assert scored.score == 0.35 * 100 + 0.30 * 75 + 0.20 * 50 + 0.15 * 25
    assert scored.outcome.outcome == "kept"
    assert transport.requests[0].model == SONNET and transport.requests[0].effort == "low"
    assert transport.requests[0].output_schema == load_prompt("score").schema


def test_citing_a_field_the_lead_lacks_is_retried() -> None:
    bad = answer(5, 4, 3, 2, cites={**CITES, "ad_activity": ["sponsorships"]})
    scoring, transport = scorer([bad, answer(4, 4, 3, 2)])
    scored = scoring.score(LEAD, FIELDS, "r")
    assert scored.samples[0].call_role == "retry" and scored.score is not None
    feedback = transport.requests[1].messages[-1]["content"]
    assert "ad_activity cites fields the lead has no value for: ['sponsorships']" in feedback


@pytest.mark.parametrize(
    "bad",
    [
        {"ratings": answer(5, 4, 3, 2)["ratings"][:3]},  # a criterion missing
        {"ratings": answer(5, 4, 3, 2)["ratings"] + answer(5, 4, 3, 2)["ratings"][:1]},  # twice
        answer(5, 4, 3, 6),  # out of range
        answer(5, 4, 3, 2, cites={**CITES, "audience": ["employee_count"]}),  # not allowed
        {"ratings": [{**r, "reason": " "} for r in answer(5, 4, 3, 2)["ratings"]]},  # no reason
        {"scores": []},
    ],
)
def test_invalid_answers_end_as_score_failed_after_retry_and_fallback(bad: Any) -> None:
    scoring, transport = scorer([bad, bad, bad])
    scored = scoring.score(LEAD, FIELDS, "r")
    assert [r.model for r in transport.requests] == [SONNET, SONNET, HAIKU]
    assert (scored.outcome.reason, scored.score) == ("score_failed", None)
    assert scored.outcome.detail.startswith("no valid score after retry and fallback")


def test_repeats_record_every_sample_and_the_first_decides() -> None:
    scoring, transport = scorer(
        [answer(3, 3, 3, 3), answer(5, 5, 5, 5), answer(1, 1, 1, 1)], repeats=3
    )
    scored = scoring.score(LEAD, FIELDS, "r")
    assert [sample.score for sample in scored.samples] == [50, 100, 0]
    assert scored.outcome.reason == "below_threshold"
    assert len({cached_prefix(request) for request in transport.requests}) == 1


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


def test_scores_and_calls_are_stored_with_the_step(db: sqlite3.Connection) -> None:
    run = Run(db, "pipeline", "gaming-hardware-na", "fixture", {}, {})
    run.start()
    db.execute(
        "INSERT INTO companies (company_id, domain, name, created_run_id, created_at) "
        "VALUES (1, 'alpha.test', 'Alpha Gear', ?, ?)",
        (run.run_id, utc_now()),
    )
    db.execute(
        "INSERT INTO leads VALUES (?, 'gaming-hardware-na', 1, 'test', 'none', 'v', ?, ?)",
        (LEAD.lead_id, run.run_id, utc_now()),
    )
    scoring, _ = scorer([answer(5, 3, 3, 1), answer(4, 3, 3, 1)], repeats=2, sink=run.calls)
    with run.step("score", "real", 1) as recorder:
        scored = scoring.score(LEAD, FIELDS, run.run_id)
        recorder.defer(lambda: store(db, run.run_id, scored, SEGMENT))
        recorder.outcomes.append(scored.outcome)
    rows = db.execute("SELECT * FROM scores ORDER BY sample").fetchall()
    assert [(row["sample"], row["score"]) for row in rows] == [(1, 60.0), (2, 51.25)]
    assert json.loads(rows[0]["reasons_json"])[0]["criterion"] == "audience"
    assert {item["points"] for item in json.loads(rows[0]["criteria_json"])} == {100, 50, 0}
    assert rows[0]["model_call_id"] is not None
    step = db.execute("SELECT * FROM step_runs WHERE step = 'score'").fetchone()
    calls = db.execute("SELECT count(*), sum(cost_usd) FROM model_calls").fetchone()
    assert calls[0] == 2 and step["cost_usd"] == pytest.approx(calls[1])
    outcome = db.execute("SELECT outcome, detail FROM lead_step_outcomes").fetchone()
    assert tuple(outcome) == ("kept", "score 60 >= 60")
    spans = db.execute("SELECT operation, agent_name FROM spans ORDER BY operation DESC").fetchall()
    assert [tuple(row) for row in spans] == [("step", None), ("invoke_agent", "scorer")]
