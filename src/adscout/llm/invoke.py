"""Retry, fallback and escalation around the adapter, in our own code (design decision 15).

A role's call is tried once; output that breaks the role's contract is retried once with the
problem stated; a refusal, output still invalid after the retry, or an overload or server
error that survived the transport's retries calls the other tier once, recorded with call
role `fallback`. No server-side fallback is configured. Budget errors are never retried.
Escalation is a separate, logged second opinion on a stronger tier (extraction, decision 14).
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from adscout.llm.adapter import (
    CallContext,
    CallRole,
    ModelAdapter,
    ModelCallFailed,
    ModelRequest,
    ModelResult,
)

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
OTHER_TIER = {HAIKU: SONNET, SONNET: HAIKU}
RETRY_NOTE = (
    "That answer was not valid: {problem}. Answer again with the same instructions, fixing "
    "only that problem."
)


class InvalidOutput(ValueError):
    """A response that does not meet the role's output contract."""


class CallsFailed(RuntimeError):
    """Every allowed attempt failed; `attempts` names each one's call role and reason."""

    def __init__(self, attempts: list[tuple[CallRole, str]]) -> None:
        super().__init__("; ".join(f"{role}: {reason}" for role, reason in attempts))
        self.attempts = attempts


@dataclass(frozen=True)
class Invoked[T]:
    value: T
    result: ModelResult
    call_role: CallRole


def with_feedback(request: ModelRequest, answer: str, problem: str) -> ModelRequest:
    """The same request with the invalid answer and the problem appended as new turns."""
    messages: list[Any] = [
        *request.messages,
        {"role": "assistant", "content": answer or "(empty)"},
        {"role": "user", "content": RETRY_NOTE.format(problem=problem)},
    ]
    return replace(request, messages=messages)


def invoke[T](
    adapter: ModelAdapter,
    request: ModelRequest,
    context: CallContext,
    parse: Callable[[ModelResult], T],
) -> Invoked[T]:
    """Primary call, one retry on invalid output, then one fallback to the other tier."""
    attempts: list[tuple[CallRole, str]] = []
    try:
        result = adapter.call(request, context, "primary")
        try:
            return Invoked(parse(result), result, "primary")
        except InvalidOutput as problem:
            attempts.append(("primary", f"invalid output: {problem}"))
            retry = with_feedback(request, result.text, str(problem))
            result = adapter.call(retry, context, "retry")
            try:
                return Invoked(parse(result), result, "retry")
            except InvalidOutput as again:
                attempts.append(("retry", f"invalid output: {again}"))
    except ModelCallFailed as failure:
        if not failure.fallback_allowed:
            raise
        attempts.append(("primary" if not attempts else "retry", str(failure)))
    other = OTHER_TIER.get(request.model)
    if other is None:
        raise CallsFailed(attempts)
    try:
        result = adapter.call(replace(request, model=other), context, "fallback")
        return Invoked(parse(result), result, "fallback")
    except (InvalidOutput, ModelCallFailed) as failure:
        attempts.append(("fallback", str(failure)))
        raise CallsFailed(attempts) from None


def escalate[T](
    adapter: ModelAdapter,
    request: ModelRequest,
    context: CallContext,
    parse: Callable[[ModelResult], T],
    model: str = SONNET,
) -> Invoked[T]:
    """One call on a stronger tier after a validator rejected the cheaper tier's answer."""
    result = adapter.call(replace(request, model=model), context, "escalation")
    return Invoked(parse(result), result, "escalation")
