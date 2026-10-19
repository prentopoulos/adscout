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
from pathlib import Path
from typing import Any, Literal

from adscout.config import SegmentConfig, load_segment
from adscout.rules import apply_rules

ROOT = Path(__file__).resolve().parent.parent


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


def funnel_conservation(inputs: dict[str, Any], expected: dict[str, Any]) -> Outcome:
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


def cost_per_qualified_lead(inputs: dict[str, Any], expected: dict[str, Any]) -> Outcome:
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


def profile_rules(inputs: dict[str, Any], expected: dict[str, Any]) -> Outcome:
    """The real profile rules on a lead's fields give the case's expected outcome."""
    path = ROOT / "config" / "segments" / f"{inputs['segment']}.yaml"
    segment = load_segment(path)
    if inputs.get("segment_changes"):
        segment = SegmentConfig.model_validate(
            segment.model_dump() | inputs["segment_changes"], strict=False
        )
    result = apply_rules(segment, inputs["fields"])
    got = {
        "outcome": "kept" if result.passed else "exited",
        "reason": None if result.passed else result.outcome("x" * 36).reason,
        "failed_rules": sorted(result.failed),
        "missing": result.missing,
    }
    want = {
        "outcome": expected["outcome"],
        "reason": expected.get("reason"),
        "failed_rules": sorted(expected.get("failed_rules", [])),
        "missing": expected.get("missing", []),
    }
    metrics: dict[str, float | int | None] = {"failed_rules": len(result.failed)}
    detail = "; ".join(result.reasons) or (
        f"missing {result.missing}" if result.missing else "passes every rule"
    )
    if got == want:
        return Outcome("pass", f"as expected: {detail}", metrics)
    return Outcome("fail", f"expected {want}, got {got}: {detail}", metrics)


EVALUATORS: dict[str, tuple[str, Callable[[dict[str, Any], dict[str, Any]], Outcome]]] = {
    "funnel_conservation": ("2", funnel_conservation),
    "cost_per_qualified_lead": ("2", cost_per_qualified_lead),
    "profile_rules": ("1", profile_rules),
}
