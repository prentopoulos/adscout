"""The dated price table and call costs (Phase 2 design, decisions 16 and 20)."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from adscout.config import ConfigError
from adscout.llm.prices import (
    PRICE_TABLE,
    MissingPrice,
    PriceTable,
    Usage,
    cost,
    load_price_table,
)

DAY = date(2026, 10, 19)
HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"


def raw_table() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(PRICE_TABLE.read_text(encoding="utf-8"))
    return data


def write_table(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "prices.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_committed_table_loads_with_its_source_and_date() -> None:
    table = load_price_table()
    [price_set] = table.price_sets
    assert price_set.retrieved_on == date(2026, 10, 18)
    assert price_set.source == "https://platform.claude.com/docs/en/about-claude/pricing"
    assert set(price_set.models) == {HAIKU, SONNET}
    assert price_set.web_search_per_1000 == 10.0


def test_haiku_call_with_a_search_costs_the_table_arithmetic() -> None:
    usage = Usage(
        input_tokens=2000, cache_read_tokens=1000, output_tokens=500, web_search_requests=1
    )
    result = cost(load_price_table(), HAIKU, usage, DAY)
    expected = (2000 * Decimal("0.10") + 1000 * Decimal("0.01") + 500 * Decimal("0.50")) / 1_000_000
    assert result.tokens_usd == expected == Decimal("0.00046")
    assert result.search_fee_usd == Decimal("0.01")
    assert result.total_usd == Decimal("0.01046")
    assert result.price_date == date(2026, 10, 18)


def test_sonnet_cache_writes_and_reads_have_their_own_prices() -> None:
    usage = Usage(input_tokens=1000, cache_write_5m_tokens=4000, cache_read_tokens=10_000)
    result = cost(load_price_table(), SONNET, usage, DAY)
    assert (
        result.total_usd
        == (1000 * Decimal("2") + 4000 * Decimal("2.5") + 10_000 * Decimal("0.1")) / 1_000_000
    )


def test_haiku_prompt_over_100k_tokens_pays_the_long_prompt_tier_for_everything() -> None:
    table = load_price_table()
    at_limit = Usage(input_tokens=60_000, cache_read_tokens=40_000, output_tokens=1000)
    over = Usage(input_tokens=60_000, cache_read_tokens=40_001, output_tokens=1000)
    assert at_limit.prompt_tokens == 100_000
    assert (
        cost(table, HAIKU, at_limit, DAY).total_usd
        == (60_000 * Decimal("0.10") + 40_000 * Decimal("0.01") + 1000 * Decimal("0.50"))
        / 1_000_000
    )
    assert (
        cost(table, HAIKU, over, DAY).total_usd
        == (60_000 * Decimal("0.50") + 40_001 * Decimal("0.05") + 1000 * Decimal("2.50"))
        / 1_000_000
    )


def test_model_without_a_price_is_refused() -> None:
    with pytest.raises(MissingPrice, match="claude-opus-5-5"):
        cost(load_price_table(), "claude-opus-5-5", Usage(input_tokens=1), DAY)


def test_call_before_any_price_set_is_refused() -> None:
    with pytest.raises(MissingPrice, match="2026-10-17"):
        cost(load_price_table(), HAIKU, Usage(input_tokens=1), date(2026, 10, 17))


def test_call_is_priced_with_the_set_in_force_on_its_date(tmp_path: Path) -> None:
    data = raw_table()
    later = yaml.safe_load(yaml.safe_dump(data["price_sets"][0]))
    later["effective_from"] = later["retrieved_on"] = date(2026, 12, 1)
    later["models"][HAIKU]["tiers"][0]["input"] = 0.20
    data["price_sets"].append(later)
    table = load_price_table(write_table(tmp_path, data))
    usage = Usage(input_tokens=100_000)
    assert cost(table, HAIKU, usage, date(2026, 11, 30)).total_usd == Decimal("0.01")
    assert cost(table, HAIKU, usage, date(2026, 12, 1)).total_usd == Decimal("0.02")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["price_sets"][0]["models"][HAIKU]["tiers"].reverse(), "rising"),
        (lambda d: d["price_sets"].append(d["price_sets"][0]), "distinct, rising"),
        (lambda d: d["price_sets"][0].update(source="http://example.test"), "source"),
        (lambda d: d["price_sets"][0].update(note="x"), "note"),
        (lambda d: d["price_sets"][0]["models"][SONNET]["tiers"][0].update(input=-1), "input"),
    ],
)
def test_invalid_table_is_refused(tmp_path: Path, change: Any, message: str) -> None:
    data = raw_table()
    change(data)
    with pytest.raises(ConfigError, match=message):
        load_price_table(write_table(tmp_path, data))


def test_hash_ignores_formatting(tmp_path: Path) -> None:
    table = load_price_table()
    reformatted = load_price_table(write_table(tmp_path, raw_table()))
    assert isinstance(reformatted, PriceTable)
    assert reformatted.content_hash() == table.content_hash()
