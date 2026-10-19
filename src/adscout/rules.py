"""Deterministic profile rules over validated fields (Phase 2 design, decision 22).

A lead passes only if it sells in every region of the segment, has at least one allowed
category, matches no excluded category and is within the segment's size range. Region and
category are rules, not score criteria; headquarters is never a rule. A lead missing a key
field exits as `missing_key_fields`; a lead failing a rule exits as `out_of_profile`, and
the detail names every rule it failed.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from adscout.config import SegmentConfig
from adscout.enrichment.fields import KEY_FIELDS
from adscout.pipeline.contracts import Outcome

RuleId = Literal["region", "category", "excluded_category", "size"]


@dataclass(frozen=True)
class RuleResult:
    missing: list[str]
    failed: list[RuleId]
    reasons: list[str]

    @property
    def passed(self) -> bool:
        return not self.missing and not self.failed

    def outcome(self, lead_id: str) -> Outcome:
        if self.missing:
            return Outcome(
                lead_id=lead_id,
                outcome="exited",
                reason="missing_key_fields",
                detail=f"missing key fields: {', '.join(self.missing)}",
            )
        if self.failed:
            return Outcome(
                lead_id=lead_id,
                outcome="exited",
                reason="out_of_profile",
                detail="; ".join(self.reasons),
            )
        return Outcome(lead_id=lead_id, outcome="kept", detail="passes every profile rule")


def apply_rules(segment: SegmentConfig, fields: dict[str, Any]) -> RuleResult:
    """`fields` are a lead's chosen valid values, as the enrich step summarizes them."""
    missing: list[str] = [name for name in KEY_FIELDS if not fields.get(name)]
    if missing:
        return RuleResult(missing, [], [])
    failed: list[RuleId] = []
    reasons: list[str] = []
    sells_in = set(fields["sells_in"])
    absent = [region for region in segment.regions if region not in sells_in]
    if absent:
        failed.append("region")
        reasons.append(
            f"region: does not sell in {', '.join(absent)} "
            f"(sells in {', '.join(sorted(sells_in))}; needs {', '.join(segment.regions)})"
        )
    categories = set(fields["categories"])
    if not categories & set(segment.categories):
        failed.append("category")
        reasons.append(f"category: none of {sorted(categories)} is an allowed category")
    excluded = sorted(categories & set(segment.exclusions.categories))
    if excluded:
        failed.append("excluded_category")
        reasons.append(f"excluded_category: {', '.join(excluded)} is excluded")
    size = segment.size_range
    if size is not None:
        measure = _size(fields, size.metric)
        if measure is None:
            return RuleResult([size.metric], [], [])
        if (size.min is not None and measure < size.min) or (
            size.max is not None and measure > size.max
        ):
            failed.append("size")
            bounds = f"at least {size.min:g}" if size.min is not None else ""
            if size.max is not None:
                bounds += f"{' and ' if bounds else ''}at most {size.max:g}"
            reasons.append(f"size: {size.metric} {measure:g}, needs {bounds}")
    return RuleResult([], failed, reasons)


def _size(fields: dict[str, Any], metric: str) -> float | None:
    if metric == "employees":
        value = fields.get("employee_count")
        count = value.get("count") if isinstance(value, dict) else None
        return float(count) if isinstance(count, int) else None
    revenue = fields.get("revenue_usd")
    amount = revenue.get("amount") if isinstance(revenue, dict) else None
    return float(amount) if isinstance(amount, int | float) else None


def rules_step(
    segment: SegmentConfig, leads: Sequence[tuple[str, dict[str, Any]]]
) -> list[Outcome]:
    """The `rules` step: one outcome per lead from its enriched fields; no model call."""
    return [apply_rules(segment, fields).outcome(lead_id) for lead_id, fields in leads]
