"""The dated price table and the cost of a model call from its usage.

Prices come from `config/prices/anthropic.yaml`, in US dollars per million tokens. A call is
priced with the price set in force on its date; a model missing from that set is refused
before any request is sent (Phase 2 design, decisions 16 and 20). Arithmetic is in `Decimal`
so a recorded cost equals the price-table arithmetic exactly.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from adscout.config import ConfigError, canonical_hash, error_text, load_yaml
from adscout.ids import ROOT

PRICE_TABLE = ROOT / "config" / "prices" / "anthropic.yaml"
MILLION = Decimal(1_000_000)
THOUSAND = Decimal(1_000)


class MissingPrice(LookupError):
    """No price for this model on this date; the call must not be sent."""


class TierPrices(BaseModel):
    """Per-MTok prices for prompts up to `max_prompt_tokens` (no limit when null)."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_prompt_tokens: int | None = Field(gt=0)
    input: float = Field(ge=0)
    cache_write_5m: float = Field(ge=0)
    cache_write_1h: float = Field(ge=0)
    cache_read: float = Field(ge=0)
    output: float = Field(ge=0)


class ModelPrices(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tiers: list[TierPrices] = Field(min_length=1)

    @model_validator(mode="after")
    def check(self) -> Self:
        limits = [tier.max_prompt_tokens for tier in self.tiers]
        bounded = [limit for limit in limits[:-1] if limit is not None]
        if (
            limits[-1] is not None
            or len(bounded) != len(limits) - 1
            or bounded != sorted(set(bounded))
        ):
            raise ValueError(
                "tiers need rising max_prompt_tokens, and only the last one may be null"
            )
        return self

    def tier(self, prompt_tokens: int) -> TierPrices:
        for tier in self.tiers:
            if tier.max_prompt_tokens is None or prompt_tokens <= tier.max_prompt_tokens:
                return tier
        raise AssertionError("the last tier has no limit")  # pragma: no cover


class PriceSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    effective_from: date
    retrieved_on: date
    source: str = Field(pattern=r"^https://")
    web_search_per_1000: float = Field(ge=0)
    models: dict[str, ModelPrices] = Field(min_length=1)


class PriceTable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1"]
    provider: Literal["anthropic"]
    currency: Literal["USD"]
    price_sets: list[PriceSet] = Field(min_length=1)

    @model_validator(mode="after")
    def check(self) -> Self:
        dates = [price_set.effective_from for price_set in self.price_sets]
        if dates != sorted(set(dates)):
            raise ValueError(f"price sets need distinct, rising effective_from dates: {dates}")
        return self

    def price_set(self, on: date) -> PriceSet:
        """The price set in force on a date."""
        in_force = [item for item in self.price_sets if item.effective_from <= on]
        if not in_force:
            raise MissingPrice(f"no price set is in force on {on.isoformat()}")
        return in_force[-1]

    def model_prices(self, model: str, on: date) -> tuple[PriceSet, ModelPrices]:
        price_set = self.price_set(on)
        prices = price_set.models.get(model)
        if prices is None:
            raise MissingPrice(
                f"no price for {model} in the price set in force on {on.isoformat()}"
            )
        return price_set, prices

    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


@dataclass(frozen=True)
class Usage:
    """Token and search counts from a response's usage fields."""

    input_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    web_search_requests: int = 0

    @property
    def prompt_tokens(self) -> int:
        """What a prompt-length tier counts: input, cache writes and cache reads."""
        return (
            self.input_tokens
            + self.cache_write_5m_tokens
            + self.cache_write_1h_tokens
            + self.cache_read_tokens
        )

    @property
    def cache_write_tokens(self) -> int:
        return self.cache_write_5m_tokens + self.cache_write_1h_tokens


@dataclass(frozen=True)
class Cost:
    tokens_usd: Decimal
    search_fee_usd: Decimal
    price_date: date

    @property
    def total_usd(self) -> Decimal:
        return self.tokens_usd + self.search_fee_usd


def per_token(price_per_mtok: float) -> Decimal:
    # str() keeps the YAML's decimal digits: 0.125 stays 0.125, not its binary neighbour.
    return Decimal(str(price_per_mtok)) / MILLION


def cost(table: PriceTable, model: str, usage: Usage, on: date) -> Cost:
    """The cost of one call from its usage, priced on the call's date."""
    price_set, prices = table.model_prices(model, on)
    tier = prices.tier(usage.prompt_tokens)
    tokens = (
        usage.input_tokens * per_token(tier.input)
        + usage.cache_write_5m_tokens * per_token(tier.cache_write_5m)
        + usage.cache_write_1h_tokens * per_token(tier.cache_write_1h)
        + usage.cache_read_tokens * per_token(tier.cache_read)
        + usage.output_tokens * per_token(tier.output)
    )
    searches = usage.web_search_requests * Decimal(str(price_set.web_search_per_1000)) / THOUSAND
    return Cost(tokens_usd=tokens, search_fee_usd=searches, price_date=price_set.effective_from)


def load_price_table(path: Path = PRICE_TABLE) -> PriceTable:
    try:
        return PriceTable.model_validate(load_yaml(path))
    except ValidationError as error:
        raise ConfigError(f"{path.name}: {error_text(error)}") from error
