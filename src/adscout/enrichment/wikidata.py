"""Wikidata: HQ country, ownership, parent, dated employee count, revenue, social accounts.

A company is found by searching its name and keeping the first item whose official website
(P856) is on the company's domain, so a namesake never matches. Values come from the item's
statements: the preferred rank first, else the latest point in time (P585); deprecated
statements are ignored. A parent organization (P749) is read for its label only. Requests
go through the polite fetcher to the Wikidata API, which follows the Wikimedia API and
User-Agent policies rather than robots.txt (crawler rules); its pages are not crawled.
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from adscout.db.connection import utc_now
from adscout.enrichment.fields import Candidate
from adscout.sources.fetcher import Fetcher, FetchFailed, Page, SourceContext
from adscout.sources.urls import on_site

API = "https://www.wikidata.org/w/api.php"
ENTITY_DATA = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
ITEM_PAGE = "https://www.wikidata.org/wiki/{qid}"
SITE = "wikidata.org"
USD = "http://www.wikidata.org/entity/Q4917"
HUMAN = "Q5"
SOCIAL = {  # property: (platform, URL template)
    "P2002": ("x", "https://x.com/{id}"),
    "P2013": ("facebook", "https://www.facebook.com/{id}"),
    "P2003": ("instagram", "https://www.instagram.com/{id}/"),
    "P2397": ("youtube", "https://www.youtube.com/channel/{id}"),
    "P7085": ("tiktok", "https://www.tiktok.com/@{id}"),
    "P5797": ("twitch", "https://www.twitch.tv/{id}"),
}


@dataclass(frozen=True)
class Entity:
    qid: str
    data: dict[str, Any]
    page: Page

    @property
    def claims(self) -> dict[str, list[dict[str, Any]]]:
        found: dict[str, list[dict[str, Any]]] = self.data.get("claims", {})
        return found

    @property
    def label(self) -> str | None:
        label = self.data.get("labels", {}).get("en", {}).get("value")
        return str(label) if label else None


@dataclass(frozen=True)
class WikidataResult:
    entity: Entity
    candidates: list[Candidate]
    cik: int | None


class Wikidata:
    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher
        self._countries: dict[str, str | None] = {}

    def get(self, url: str, context: SourceContext) -> Page:
        return self.fetcher.fetch(url, context, site=SITE, kind="wikidata", check_robots=False)

    def entity(self, qid: str, context: SourceContext) -> Entity:
        page = self.get(ENTITY_DATA.format(qid=qid), context)
        data = page.json()
        entities = data.get("entities", {}) if isinstance(data, dict) else {}
        found = entities.get(qid) or next(iter(entities.values()), None)
        if not isinstance(found, dict):
            raise FetchFailed(f"Wikidata returned no entity {qid}")
        return Entity(qid, found, page)

    def find(self, name: str, domain: str, context: SourceContext) -> Entity | None:
        query = urlencode(
            {
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "type": "item",
                "limit": 5,
                "format": "json",
            }
        )
        results = self.get(f"{API}?{query}", context).json()
        hits = results.get("search", []) if isinstance(results, dict) else []
        for hit in hits:
            qid = hit.get("id") if isinstance(hit, dict) else None
            if not isinstance(qid, str):
                continue
            entity = self.entity(qid, context)
            websites = [str(value) for value in values(entity.claims, "P856")]
            if any(on_site(site, domain) for site in websites):
                return entity
        return None

    def enrich(self, name: str, domain: str, context: SourceContext) -> WikidataResult | None:
        entity = self.find(name, domain, context)
        if entity is None:
            return None
        source = ITEM_PAGE.format(qid=entity.qid)
        now = utc_now()

        def candidate(field: Any, value: Any, as_of: str | None = None) -> Candidate:
            return Candidate(
                field=field,
                value=value,
                source_url=source,
                source_kind="wikidata",
                method="parsed",
                retrieved_at=now,
                as_of=as_of,
                source_call_id=entity.page.call_id,
            )

        found: list[Candidate] = []
        country = best(entity.claims, "P17")
        if country is not None:
            code = self.alpha_2(entity_id(country), context)
            if code:
                found.append(candidate("hq_country", code))
        parent = best(entity.claims, "P749")
        if values(entity.claims, "P414"):
            found.append(candidate("ownership", "public"))
        elif parent is not None:
            found.append(candidate("ownership", "subsidiary"))
        if parent is not None:
            parent_entity = self.entity(entity_id(parent), context)
            instance = [entity_id(item) for item in statements(parent_entity.claims, "P31")]
            if parent_entity.label and HUMAN not in instance:
                found.append(candidate("parent", parent_entity.label))
        employees = best(entity.claims, "P1128")
        if employees is not None:
            found.append(candidate("employee_count", quantity(employees), point_in_time(employees)))
        revenue = best(entity.claims, "P2139", unit=USD)
        if revenue is not None:
            as_of = point_in_time(revenue)
            year = int(as_of[:4]) if as_of else None
            found.append(
                candidate(
                    "revenue_usd",
                    {"amount": quantity(revenue), "currency": "USD", "fiscal_year": year},
                    as_of,
                )
            )
        accounts = [
            {"platform": platform, "id": str(value), "url": template.format(id=value)}
            for prop, (platform, template) in SOCIAL.items()
            for value in values(entity.claims, prop)[:1]
        ]
        if accounts:
            found.append(candidate("social_accounts", accounts))
        cik = values(entity.claims, "P5531")
        return WikidataResult(entity, found, int(cik[0]) if cik else None)

    def alpha_2(self, qid: str, context: SourceContext) -> str | None:
        if qid not in self._countries:
            codes = values(self.entity(qid, context).claims, "P297")
            self._countries[qid] = str(codes[0]) if codes else None
        return self._countries[qid]


# --- statements -------------------------------------------------------------------------


def statements(claims: dict[str, Any], prop: str, unit: str | None = None) -> list[Any]:
    """A property's usable statements: value snaks, not deprecated, in the unit if given."""
    found = []
    for statement in claims.get(prop, []):
        snak = statement.get("mainsnak", {})
        if statement.get("rank") == "deprecated" or snak.get("snaktype") != "value":
            continue
        value = snak.get("datavalue", {}).get("value")
        if unit is not None and (not isinstance(value, dict) or value.get("unit") != unit):
            continue
        found.append(statement)
    return found


def best(claims: dict[str, Any], prop: str, unit: str | None = None) -> Any:
    """The preferred statement, else the one with the latest point in time, else the first."""
    usable = statements(claims, prop, unit)
    if not usable:
        return None
    preferred = [item for item in usable if item.get("rank") == "preferred"]
    pool = preferred or usable
    return max(pool, key=lambda item: point_in_time(item) or "")


def values(claims: dict[str, Any], prop: str) -> list[Any]:
    return [statement["mainsnak"]["datavalue"]["value"] for statement in statements(claims, prop)]


def entity_id(statement: Any) -> str:
    value = statement["mainsnak"]["datavalue"]["value"]
    return str(value["id"])


def quantity(statement: Any) -> int | float:
    amount = float(statement["mainsnak"]["datavalue"]["value"]["amount"])
    return int(amount) if amount.is_integer() else amount


def point_in_time(statement: Any) -> str | None:
    """The P585 qualifier as YYYY, YYYY-MM or YYYY-MM-DD by its precision."""
    for qualifier in statement.get("qualifiers", {}).get("P585", []):
        value = qualifier.get("datavalue", {}).get("value", {})
        text, precision = value.get("time"), value.get("precision")
        if not isinstance(text, str) or not isinstance(precision, int):
            continue
        day = text.lstrip("+")[:10]
        if precision >= 11:
            return day
        if precision == 10:
            return day[:7]
        if precision == 9:
            return day[:4]
    return None
