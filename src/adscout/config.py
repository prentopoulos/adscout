"""Segment and ideal-customer config, seed lists, their content hashes and the contact guard.

A segment is one YAML file `config/segments/<segment_id>.yaml`; its seed list is one CSV file
`config/seeds/<segment_id>.csv`. Both hold company-level data only: loading fails when any
value looks like an email address or a phone number (PROJECT.md §5).
"""

import csv
import hashlib
import io
import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"
SEED_COLUMNS = ("name", "domain", "source", "added_by", "added_on", "notes")

EMAIL = re.compile(r"[^\s@<>()\[\],;:\"']+@[^\s@<>()\[\],;:\"']+\.[a-z]{2,}", re.IGNORECASE)
# A run of digits with the separators phone numbers use, not part of a longer token; 10 to 15
# digits make it a phone number.
PHONE_CANDIDATE = re.compile(r"(?<![\w/])\+?\(?\d[\d\s().-]{6,}\d(?![\w/])")
# Web addresses are not contact data, and their long numeric IDs look like phone numbers.
URL = re.compile(r"https?://\S+")
LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
DOMAIN = re.compile(rf"^(?:{LABEL}\.)+[a-z][a-z0-9-]{{0,61}}[a-z0-9]$")


class ConfigError(ValueError):
    """A config, seed or stub file that fails validation; the message names the problem."""


def contact_kind(value: str) -> str | None:
    """'an email address' or 'a phone number' if the text contains one, else None."""
    if EMAIL.search(value):
        return "an email address"
    for match in PHONE_CANDIDATE.finditer(URL.sub(" ", value)):
        if 10 <= sum(character.isdigit() for character in match.group()) <= 15:
            return "a phone number"
    return None


def strings(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string in a parsed document, with a dotted path to it."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from strings(item, f"{path}[{index}]")


def reject_contact_data(document: Any, where: str) -> None:
    """Fail on personal contact data, naming its place but never printing the value."""
    for path, value in strings(document):
        kind = contact_kind(value)
        if kind:
            raise ConfigError(
                f"{where}: {path or 'value'} contains {kind}; only company-level data"
            )


def normalize_domain(value: str) -> str:
    """Lowercase host only: no scheme, path, port, trailing dot or leading `www.`."""
    text = value.strip()
    if not text.isascii():
        raise ValueError("non-ASCII domains are not supported")
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text.lower())
    text = re.split(r"[/?#]", text, maxsplit=1)[0]
    text = text.rsplit("@", 1)[-1]
    text = re.sub(r":\d+$", "", text).rstrip(".")
    text = text.removeprefix("www.")
    if not DOMAIN.match(text):
        raise ValueError(f"not a domain name: {value!r}")
    return text


def canonical_hash(data: Any) -> str:
    """SHA-256 of canonical JSON, so formatting and comments never change it."""
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# The enriched fields a score reason may cite (Phase 2 design, decision 7).
ENRICHMENT_FIELDS = frozenset(
    {
        "categories",
        "sells_in",
        "hq_country",
        "ownership",
        "parent",
        "employee_count",
        "revenue_usd",
        "social_accounts",
        "ad_signals",
        "recent_launches",
        "sponsorships",
    }
)
RATINGS = (1, 2, 3, 4, 5)
# Fields the segment may leave null until decided, each with a reason in null_reasons.
NULLABLE = ("size_range", "score_threshold", "near_miss_min", "criteria")


class SizeRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    metric: Literal["annual_revenue_usd", "employees"]
    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"size_range min {self.min} exceeds max {self.max}")
        return self


class Exclusions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    domains: list[str] = []
    categories: list[str] = []


class Criterion(BaseModel):
    """One score criterion: a 1-5 rating against written anchors, weighted by code."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    question: str = Field(min_length=1)
    weight: float = Field(gt=0, le=1)
    # The enriched fields this criterion's reasons may cite.
    fields: list[str] = Field(min_length=1)
    anchors: dict[int, str]

    @model_validator(mode="after")
    def check(self) -> Self:
        unknown = sorted(set(self.fields) - ENRICHMENT_FIELDS)
        if unknown:
            raise ValueError(f"criterion {self.id}: unknown enriched fields {unknown}")
        if tuple(sorted(self.anchors)) != RATINGS:
            raise ValueError(f"criterion {self.id}: anchors must be given for ratings 1 to 5")
        if not all(text.strip() for text in self.anchors.values()):
            raise ValueError(f"criterion {self.id}: every anchor needs text")
        return self


class SegmentConfig(BaseModel):
    """One segment and its ideal-customer rules. Undecided fields are null with a reason.

    The score routes a lead: at or above `score_threshold` to research; from `near_miss_min`
    up to the threshold to a person as a near miss; below `near_miss_min` out.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["2"]
    segment_id: str = Field(pattern=SLUG)
    name: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    regions: list[str] = Field(min_length=1)
    categories: list[str] = Field(min_length=1)
    size_range: SizeRange | None
    exclusions: Exclusions
    score_threshold: float | None = Field(ge=0, le=100)
    near_miss_min: float | None = Field(ge=0, le=100)
    criteria: list[Criterion] | None
    null_reasons: dict[str, str] = {}

    @model_validator(mode="after")
    def check(self) -> Self:
        for region in self.regions:
            if not re.fullmatch(r"[A-Z]{2}", region):
                raise ValueError(f"region {region!r} is not an ISO 3166-1 alpha-2 code")
        for category in [*self.categories, *self.exclusions.categories]:
            if not re.fullmatch(SLUG, category):
                raise ValueError(f"category {category!r} is not a lowercase slug")
        missing = [
            name
            for name in NULLABLE
            if getattr(self, name) is None and not self.null_reasons.get(name)
        ]
        if missing:
            raise ValueError(f"null fields without a reason in null_reasons: {missing}")
        stale = sorted(name for name in self.null_reasons if getattr(self, name, None) is not None)
        unknown = sorted(set(self.null_reasons) - set(NULLABLE))
        if stale or unknown:
            raise ValueError(f"null_reasons for fields that are set or unknown: {stale + unknown}")
        if self.near_miss_min is not None and (
            self.score_threshold is None or self.near_miss_min >= self.score_threshold
        ):
            raise ValueError("near_miss_min must be below a set score_threshold")
        if self.criteria is not None:
            ids = [criterion.id for criterion in self.criteria]
            if len(set(ids)) != len(ids) or not ids:
                raise ValueError(f"criteria need distinct IDs: {ids}")
            total = sum(criterion.weight for criterion in self.criteria)
            if abs(total - 1) > 1e-9:
                weights = {criterion.id: criterion.weight for criterion in self.criteria}
                raise ValueError(f"criterion weights sum to {total:g}, not 1: {weights}")
        return self

    @property
    def excluded_domains(self) -> set[str]:
        return {normalize_domain(domain) for domain in self.exclusions.domains}

    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class SeedRow(BaseModel):
    """One seed company: company-level fields and where the row came from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    domain: str
    source: str = Field(min_length=1)
    added_by: str = Field(min_length=1)
    added_on: date
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("domain"), str):
            return data | {"domain": normalize_domain(data["domain"])}
        return data


class SeedList(BaseModel):
    model_config = ConfigDict(frozen=True)

    segment_id: str
    rows: tuple[SeedRow, ...]

    def content_hash(self) -> str:
        return canonical_hash([row.model_dump(mode="json") for row in self.rows])

    def duplicate_domains(self) -> list[str]:
        seen: set[str] = set()
        repeated: list[str] = []
        for row in self.rows:
            if row.domain in seen and row.domain not in repeated:
                repeated.append(row.domain)
            seen.add(row.domain)
        return repeated


def error_text(error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        place = ".".join(str(part) for part in item["loc"]) or "document"
        parts.append(f"{place}: {item['msg']}")
    return "; ".join(parts)


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigError(f"{path.name}: not valid YAML: {error}") from error


def load_segment(path: Path) -> SegmentConfig:
    raw = load_yaml(path)
    reject_contact_data(raw, path.name)
    try:
        segment = SegmentConfig.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(f"{path.name}: {error_text(error)}") from error
    if segment.segment_id != path.stem:
        raise ConfigError(f"{path.name}: segment_id {segment.segment_id!r} differs from the file")
    return segment


def load_seeds(path: Path, segment_id: str | None = None) -> SeedList:
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = tuple(reader.fieldnames or ())
    unexpected = [column for column in header if column not in SEED_COLUMNS]
    if unexpected or len(header) != len(SEED_COLUMNS) or set(header) != set(SEED_COLUMNS):
        raise ConfigError(
            f"{path.name}: columns must be exactly {', '.join(SEED_COLUMNS)}; "
            f"unexpected: {', '.join(unexpected) or 'none'}"
        )
    rows: list[SeedRow] = []
    for number, record in enumerate(reader, start=2):
        if None in record:
            raise ConfigError(f"{path.name} row {number}: more values than columns")
        for column, value in record.items():
            kind = contact_kind(value or "")
            if kind:
                raise ConfigError(
                    f"{path.name} row {number} column {column}: contains {kind}; "
                    "only company-level data"
                )
        try:
            rows.append(SeedRow.model_validate(record))
        except (ValidationError, ValueError) as error:
            detail = error_text(error) if isinstance(error, ValidationError) else str(error)
            raise ConfigError(f"{path.name} row {number}: {detail}") from error
    return SeedList(segment_id=segment_id or path.stem, rows=tuple(rows))
