"""Deterministic evaluators, each checking one invariant from the adscout-eval-review skill.

An evaluator returns pass or fail with a detail and metrics; it never raises for a wrong
answer. It raises for malformed inputs (a missing field, a wrong type, a negative or
non-finite amount), which the runner records as an error, so a malformed case cannot pass as
a deliberately failing one. A null metric carries its reason. Bump an evaluator's version
whenever its logic changes.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Outcome:
    status: Literal["pass", "fail"]
    detail: str
    metrics: dict[str, float | int | None] = field(default_factory=dict)
    null_reasons: dict[str, str] = field(default_factory=dict)


def is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def amount(inputs: dict[str, Any], key: str) -> float | int:
    """A finite, non-negative number from the inputs."""
    if not is_number(inputs[key]):
        raise TypeError(f"input {key!r} must be a number, got {inputs[key]!r}")
    value: float | int = inputs[key]
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"input {key!r} must be finite and not negative, got {value!r}")
    return value


def count(inputs: dict[str, Any], key: str) -> int:
    """A non-negative whole count from the inputs."""
    value = amount(inputs, key)
    if not isinstance(value, int):
        raise TypeError(f"input {key!r} must be a whole count, got {value!r}")
    return value


def funnel_conservation(inputs: dict[str, Any]) -> Outcome:
    """Per step, kept plus dropped equals the step's input count."""
    entering, kept, dropped = (count(inputs, key) for key in ("entering", "kept", "dropped"))
    metrics: dict[str, float | int | None] = {
        "entering": entering,
        "kept": kept,
        "dropped": dropped,
    }
    if kept + dropped == entering:
        return Outcome("pass", f"kept {kept} + dropped {dropped} = entering {entering}", metrics)
    return Outcome("fail", f"kept {kept} + dropped {dropped} != entering {entering}", metrics)


def cost_per_qualified_lead(inputs: dict[str, Any]) -> Outcome:
    """Reported cost per qualified lead equals spend / qualified, and is null at zero."""
    spend, qualified = amount(inputs, "spend_usd"), count(inputs, "qualified_leads")
    reported = inputs["reported_cost_per_qualified_lead"]
    if reported is not None and not is_number(reported):
        raise TypeError(f"reported cost per qualified lead must be a number or null: {reported!r}")
    correct = None if qualified == 0 else spend / qualified
    metrics: dict[str, float | int | None] = {"expected": correct, "reported": reported}
    reasons = {"expected": "undefined at zero qualified leads"} if correct is None else {}
    if reported is None:
        reasons["reported"] = "reported as undefined"
    if correct is None:
        if reported is None:
            return Outcome("pass", "zero qualified leads: reported as undefined", metrics, reasons)
        return Outcome("fail", f"zero qualified leads but reported {reported}", metrics, reasons)
    if reported is not None and math.isclose(reported, correct, rel_tol=1e-9):
        return Outcome("pass", f"reported {reported} = {spend} / {qualified}", metrics, reasons)
    return Outcome("fail", f"reported {reported}, expected {correct}", metrics, reasons)


EVALUATORS: dict[str, tuple[str, Callable[[dict[str, Any]], Outcome]]] = {
    "funnel_conservation": ("2", funnel_conservation),
    "cost_per_qualified_lead": ("2", cost_per_qualified_lead),
}
