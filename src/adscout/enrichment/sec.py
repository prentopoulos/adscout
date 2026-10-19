"""SEC EDGAR XBRL facts for US filers: annual revenue, and employees when a filer tags them.

A filer is identified by its CIK from Wikidata (P5531). Revenue is the latest full fiscal
year from a 10-K, read from the companyconcept API for the first revenue tag the filer
uses. The response fields (`units`, `end`, `start`, `val`, `fy`, `fp`, `form`) follow
EDGAR's XBRL frames; the API page does not list them, so they are checked again against the
first live run. Requests go through the polite fetcher with its contact User-Agent, at one
request per second, well inside SEC's fair-access limit; robots.txt (crawler rules) does
not govern this API.
"""

from datetime import date
from typing import Any

from adscout.db.connection import utc_now
from adscout.enrichment.fields import Candidate
from adscout.sources.fetcher import Fetcher, FetchFailed, Page, SourceContext

CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/{taxonomy}/{tag}.json"
SITE = "sec.gov"
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
ANNUAL_FORMS = ("10-K", "10-K/A")
MIN_YEAR_DAYS = 330


class Sec:
    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher

    def concept(self, cik: int, taxonomy: str, tag: str, context: SourceContext) -> Page | None:
        url = CONCEPT.format(cik=cik, taxonomy=taxonomy, tag=tag)
        try:
            return self.fetcher.fetch(url, context, site=SITE, kind="sec_edgar", check_robots=False)
        except FetchFailed as failure:
            if "HTTP 404" in str(failure):
                return None  # the filer does not use this tag
            raise

    def enrich(self, cik: int, context: SourceContext) -> list[Candidate]:
        found: list[Candidate] = []
        for tag in REVENUE_TAGS:
            page = self.concept(cik, "us-gaap", tag, context)
            fact = latest_annual(page.json(), "USD") if page else None
            if page and fact:
                found.append(
                    _candidate(
                        page,
                        "revenue_usd",
                        {"amount": fact["val"], "currency": "USD", "fiscal_year": fact.get("fy")},
                        fact["end"],
                    )
                )
                found.append(_candidate(page, "ownership", "public", None))
                break
        page = self.concept(cik, "dei", "EntityNumberOfEmployees", context)
        fact = latest_annual(page.json(), "pure", duration=False) if page else None
        if page and fact and isinstance(fact.get("val"), int):
            found.append(_candidate(page, "employee_count", fact["val"], fact["end"]))
        return found


def latest_annual(data: Any, unit: str, *, duration: bool = True) -> dict[str, Any] | None:
    """The latest fact from an annual report: a full-year period, or an instant if asked."""
    facts = data.get("units", {}).get(unit, []) if isinstance(data, dict) else []
    usable = []
    for fact in facts:
        if not isinstance(fact, dict) or fact.get("form") not in ANNUAL_FORMS:
            continue
        if not isinstance(fact.get("end"), str) or not isinstance(fact.get("val"), int | float):
            continue
        if duration:
            if fact.get("fp") != "FY" or not isinstance(fact.get("start"), str):
                continue
            span = date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])
            if span.days < MIN_YEAR_DAYS:
                continue
        usable.append(fact)
    return max(usable, key=lambda fact: (fact["end"], fact.get("filed", ""))) if usable else None


def _candidate(page: Page, field: Any, value: Any, as_of: str | None) -> Candidate:
    return Candidate(
        field=field,
        value=value,
        source_url=page.final_url,
        source_kind="sec_edgar",
        method="parsed",
        retrieved_at=utc_now(),
        as_of=as_of,
        source_call_id=page.call_id,
    )
