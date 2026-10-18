"""Deterministic evaluators, each checking one invariant from the adscout-eval-review skill.

An evaluator returns pass or fail with a detail and metrics; it never raises for a wrong
answer. Bump an evaluator's version whenever its logic changes.
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


def funnel_conservation(inputs: dict[str, Any]) -> Outcome:
    """Per step, kept plus dropped equals the step's input count."""
    entering, kept, dropped = inputs["entering"], inputs["kept"], inputs["dropped"]
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
    spend, qualified = inputs["spend_usd"], inputs["qualified_leads"]
    reported = inputs["reported_cost_per_qualified_lead"]
    correct = None if qualified == 0 else spend / qualified
    metrics: dict[str, float | int | None] = {"expected": correct, "reported": reported}
    if correct is None:
        if reported is None:
            return Outcome("pass", "zero qualified leads: reported as undefined", metrics)
        return Outcome("fail", f"zero qualified leads but reported {reported}", metrics)
    if reported is not None and math.isclose(reported, correct, rel_tol=1e-9):
        return Outcome("pass", f"reported {reported} = {spend} / {qualified}", metrics)
    return Outcome("fail", f"reported {reported}, expected {correct}", metrics)


EVALUATORS: dict[str, tuple[str, Callable[[dict[str, Any]], Outcome]]] = {
    "funnel_conservation": ("1", funnel_conservation),
    "cost_per_qualified_lead": ("1", cost_per_qualified_lead),
}
