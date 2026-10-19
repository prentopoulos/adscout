"""The owner-approved site list: which company domains live enrichment may read.

`config/site-checks/<segment_id>.yaml` records, for each seed domain, the one-off check of
its robots.txt and terms of use and the decision `fetch` or `skip` (design decision 11). A
live run reads a company's own site only when the list is approved by the owner and marks
the domain `fetch`; fixture and replay runs read no live site and need no list.
"""

from datetime import date
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from adscout.config import (
    SLUG,
    ConfigError,
    canonical_hash,
    error_text,
    load_yaml,
    normalize_domain,
    reject_contact_data,
)
from adscout.ids import ROOT

SITE_CHECKS = ROOT / "config" / "site-checks"


class SiteCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    domain: str
    decision: Literal["fetch", "skip"]
    robots_url: str = Field(pattern=r"^https?://")
    robots_checked_on: date
    robots_summary: str = Field(min_length=1)
    terms_url: str | None = Field(default=None, pattern=r"^https?://")
    terms_checked_on: date | None = None
    terms_summary: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: object) -> object:
        if isinstance(data, dict) and isinstance(data.get("domain"), str):
            return data | {"domain": normalize_domain(data["domain"])}
        return data

    @model_validator(mode="after")
    def check(self) -> Self:
        if (self.terms_url is None) != (self.terms_checked_on is None):
            raise ValueError(f"{self.domain}: a terms URL needs its check date and the reverse")
        return self


class Approval(BaseModel):
    """The owner's approval of the whole list; null until given, with the reason why."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    approved_by: str | None
    approved_on: date | None
    note: str = Field(min_length=1)

    @model_validator(mode="after")
    def check(self) -> Self:
        if (self.approved_by is None) != (self.approved_on is None):
            raise ValueError("an approval needs both who approved and when")
        return self

    @property
    def given(self) -> bool:
        return self.approved_by is not None


class SiteList(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1"]
    segment_id: str = Field(pattern=SLUG)
    checked_by: str = Field(min_length=1)
    approval: Approval
    sites: list[SiteCheck]

    @model_validator(mode="after")
    def check(self) -> Self:
        domains = [site.domain for site in self.sites]
        repeated = sorted({domain for domain in domains if domains.count(domain) > 1})
        if repeated:
            raise ValueError(f"domains listed twice: {repeated}")
        return self

    def site(self, domain: str) -> SiteCheck | None:
        wanted = normalize_domain(domain)
        return next((site for site in self.sites if site.domain == wanted), None)

    def live_refusal(self, domain: str) -> str | None:
        """Why a live run may not read this domain, or None if it may."""
        if not self.approval.given:
            return f"the site list for {self.segment_id} is not approved by the owner yet"
        found = self.site(domain)
        if found is None:
            return f"{domain} is not on the approved site list for {self.segment_id}"
        if found.decision == "skip":
            return f"the approved site list skips {domain}: {found.reason}"
        return None

    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


def site_list_path(segment_id: str, folder: Path = SITE_CHECKS) -> Path:
    return folder / f"{segment_id}.yaml"


def load_site_list(path: Path) -> SiteList:
    raw = load_yaml(path)
    reject_contact_data(raw, path.name)
    try:
        found = SiteList.model_validate(raw)
    except (ValidationError, ValueError) as error:
        detail = error_text(error) if isinstance(error, ValidationError) else str(error)
        raise ConfigError(f"{path.name}: {detail}") from error
    if found.segment_id != path.stem:
        raise ConfigError(f"{path.name}: segment_id {found.segment_id!r} differs from the file")
    return found


def company_site_refusal(mode: str, sites: SiteList | None, domain: str) -> str | None:
    """Why this run may not read a company's own site, or None if it may.

    Only live runs read real sites, so only they need the approved list; fixture and replay
    runs read files and recorded responses.
    """
    if mode != "live":
        return None
    if sites is None:
        return "live runs read company sites only with an approved site list; none is loaded"
    return sites.live_refusal(domain)
