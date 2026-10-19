"""Profile rules (Phase 2 design, decision 22); the full case set is evals/cases/rules.jsonl."""

from pathlib import Path

from adscout.config import SegmentConfig, load_segment
from adscout.rules import apply_rules, rules_step

SEGMENT = Path(__file__).resolve().parent.parent / "config" / "segments" / "gaming-hardware-na.yaml"


def segment(**changes: object) -> SegmentConfig:
    base = load_segment(SEGMENT)
    return SegmentConfig.model_validate(base.model_dump() | changes, strict=False)


def test_us_only_exits_out_of_profile_naming_the_region_rule() -> None:
    fields = {"sells_in": ["US"], "categories": ["peripherals"], "employee_count": {"count": 900}}
    result = apply_rules(segment(), fields)
    outcome = result.outcome("0192f0c1-0000-7000-8000-000000000001")
    assert (outcome.outcome, outcome.reason) == ("exited", "out_of_profile")
    assert outcome.detail == "region: does not sell in CA (sells in US; needs US, CA)"


def test_a_passing_lead_is_kept() -> None:
    fields = {
        "sells_in": ["CA", "US"],
        "categories": ["peripherals"],
        "employee_count": {"count": 50},
    }
    outcome = apply_rules(segment(), fields).outcome("0192f0c1-0000-7000-8000-000000000001")
    assert (outcome.outcome, outcome.detail) == ("kept", "passes every profile rule")


def test_missing_key_field_exits_before_the_rules() -> None:
    fields = {"sells_in": ["US"], "categories": ["peripherals"]}
    outcome = apply_rules(segment(), fields).outcome("0192f0c1-0000-7000-8000-000000000001")
    assert (outcome.reason, outcome.detail) == (
        "missing_key_fields",
        "missing key fields: employee_count",
    )


def test_a_revenue_size_rule_reads_revenue() -> None:
    by_revenue = segment(size_range={"metric": "annual_revenue_usd", "min": 1e8, "max": None})
    base = {"sells_in": ["US", "CA"], "categories": ["peripherals"], "employee_count": {"count": 9}}
    assert apply_rules(by_revenue, base | {"revenue_usd": {"amount": 2e8}}).passed
    small = apply_rules(by_revenue, base | {"revenue_usd": {"amount": 5e7}})
    assert small.failed == ["size"] and "annual_revenue_usd 5e+07" in small.reasons[0]
    assert apply_rules(by_revenue, base).missing == ["annual_revenue_usd"]


def test_rules_step_gives_one_outcome_per_lead() -> None:
    good = {
        "sells_in": ["US", "CA"],
        "categories": ["peripherals"],
        "employee_count": {"count": 60},
    }
    outcomes = rules_step(segment(), [("a" * 36, good), ("b" * 36, good | {"sells_in": ["US"]})])
    assert [(o.lead_id[0], o.outcome) for o in outcomes] == [("a", "kept"), ("b", "exited")]
