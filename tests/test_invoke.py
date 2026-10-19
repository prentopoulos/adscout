"""Retry, fallback and escalation in our own code (Phase 2 design, decision 15)."""

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from adscout.ids import uuid7
from adscout.llm.adapter import (
    CallContext,
    CallSink,
    FakeTransport,
    ModelAdapter,
    ModelCallFailed,
    ModelRequest,
    ModelResult,
    request_hash,
)
from adscout.llm.budget import BudgetExhausted, SpendLedger
from adscout.llm.fakes import fake_message, scripted
from adscout.llm.invoke import HAIKU, SONNET, CallsFailed, InvalidOutput, escalate, invoke
from adscout.llm.prices import load_price_table

PROMPT = "p-0123456789ab"


def parse_rating(result: ModelResult) -> int:
    try:
        rating = json.loads(result.text)["rating"]
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidOutput(f"not a rating object: {error}") from None
    if rating not in range(1, 6):
        raise InvalidOutput(f"rating {rating} is outside 1-5")
    return int(rating)


def setup(
    responses: list[Any], model: str = HAIKU
) -> tuple[ModelAdapter, FakeTransport, CallSink, ModelRequest, CallContext]:
    transport = FakeTransport(scripted(responses))
    sink = CallSink()
    adapter = ModelAdapter(
        transport, load_price_table(), SpendLedger(None), sink, today=lambda: date(2026, 10, 19)
    )
    request = ModelRequest(
        model=model,
        max_tokens=200,
        system=[{"type": "text", "text": "Rate the lead 1-5."}],
        messages=[{"role": "user", "content": "example.test"}],
        effort="low",
    )
    context = CallContext(
        run_id="r",
        step="score",
        lead_id=str(uuid7()),
        role="scorer",
        agent_name="scorer",
        prompt_version=PROMPT,
        parent_span_id="0123456789abcdef",
    )
    return adapter, transport, sink, request, context


def calls(sink: CallSink) -> list[tuple[str, str, str]]:
    return [(record.call_role, record.model, record.status) for record in sink.drain()]


def test_valid_answer_needs_one_call() -> None:
    adapter, _, sink, request, context = setup([fake_message(HAIKU, data={"rating": 4})])
    invoked = invoke(adapter, request, context, parse_rating)
    assert (invoked.value, invoked.call_role) == (4, "primary")
    assert calls(sink) == [("primary", HAIKU, "succeeded")]


def test_invalid_answer_is_retried_once_with_the_problem_stated() -> None:
    adapter, transport, sink, request, context = setup(
        [fake_message(HAIKU, data={"rating": 9}), fake_message(HAIKU, data={"rating": 3})]
    )
    invoked = invoke(adapter, request, context, parse_rating)
    assert (invoked.value, invoked.call_role) == (3, "retry")
    retry = transport.requests[1]
    assert retry.messages[-1]["content"].startswith("That answer was not valid: rating 9")
    assert retry.messages[-2] == {"role": "assistant", "content": '{"rating": 9}'}
    assert request_hash(retry, PROMPT) != request_hash(request, PROMPT)  # replayable
    assert calls(sink) == [("primary", HAIKU, "succeeded"), ("retry", HAIKU, "succeeded")]


def test_invalid_twice_falls_back_to_the_other_tier_once() -> None:
    adapter, transport, sink, request, context = setup(
        [
            fake_message(HAIKU, text="not json"),
            fake_message(HAIKU, data={"rating": 0}),
            fake_message(SONNET, data={"rating": 5}),
        ]
    )
    invoked = invoke(adapter, request, context, parse_rating)
    assert (invoked.value, invoked.call_role) == (5, "fallback")
    assert transport.requests[2].model == SONNET
    assert transport.requests[2].messages == request.messages  # a fresh request, no feedback
    assert transport.requests[2].effort == "low"
    assert calls(sink) == [
        ("primary", HAIKU, "succeeded"),
        ("retry", HAIKU, "succeeded"),
        ("fallback", SONNET, "succeeded"),
    ]


def test_invalid_everywhere_names_every_attempt() -> None:
    adapter, _, sink, request, context = setup(
        [fake_message(m, text="{}") for m in (HAIKU, HAIKU, SONNET)]
    )
    with pytest.raises(CallsFailed) as caught:
        invoke(adapter, request, context, parse_rating)
    assert [role for role, _ in caught.value.attempts] == ["primary", "retry", "fallback"]
    assert len(calls(sink)) == 3


def test_refusal_falls_back_without_a_retry() -> None:
    adapter, _, sink, request, context = setup(
        [
            fake_message(SONNET, text="", stop_reason="refusal"),
            fake_message(HAIKU, data={"rating": 2}),
        ],
        model=SONNET,
    )
    invoked = invoke(adapter, request, context, parse_rating)
    assert (invoked.value, invoked.call_role) == (2, "fallback")
    assert calls(sink) == [("primary", SONNET, "succeeded"), ("fallback", HAIKU, "succeeded")]


def test_overload_after_the_transport_retries_falls_back() -> None:
    overloaded = ModelCallFailed("overloaded", "HTTP 529", fallback_allowed=True)
    adapter, _, sink, request, context = setup(
        [overloaded, fake_message(SONNET, data={"rating": 3})]
    )
    assert invoke(adapter, request, context, parse_rating).call_role == "fallback"
    assert calls(sink) == [("primary", HAIKU, "failed"), ("fallback", SONNET, "succeeded")]


def test_failure_without_a_fallback_is_raised_at_once() -> None:
    denied = ModelCallFailed("authentication", "HTTP 401", fallback_allowed=False)
    adapter, transport, _, request, context = setup([denied])
    with pytest.raises(ModelCallFailed, match="authentication"):
        invoke(adapter, request, context, parse_rating)
    assert len(transport.requests) == 1


def test_budget_error_is_never_retried_or_fallen_back() -> None:
    adapter, transport, _, request, context = setup([BudgetExhausted("cap")])
    with pytest.raises(BudgetExhausted):
        invoke(adapter, request, context, parse_rating)
    assert len(transport.requests) == 1


def test_model_without_another_tier_cannot_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("adscout.llm.invoke.OTHER_TIER", {})
    adapter, _, _, request, context = setup(
        [ModelCallFailed("overloaded", "HTTP 529", fallback_allowed=True)]
    )
    with pytest.raises(CallsFailed, match="overloaded"):
        invoke(adapter, request, context, parse_rating)


def test_escalation_is_recorded_as_its_own_call_role() -> None:
    adapter, transport, sink, request, context = setup([fake_message(SONNET, data={"rating": 4})])
    invoked = escalate(adapter, request, context, parse_rating)
    assert (invoked.value, invoked.call_role, transport.requests[0].model) == (
        4,
        "escalation",
        SONNET,
    )
    assert calls(sink) == [("escalation", SONNET, "succeeded")]
    assert invoked.result.cost_usd > Decimal(0)
