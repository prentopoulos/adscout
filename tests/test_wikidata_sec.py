"""Wikidata and SEC EDGAR clients against synthetic responses in the documented JSON formats.

The entities, CIK and numbers are made up; only the shapes follow the Wikibase JSON format
and EDGAR's companyconcept API.
"""

from typing import Any
from urllib.parse import parse_qs

import httpx2
import pytest

from adscout.enrichment.sec import Sec, latest_annual
from adscout.enrichment.wikidata import USD, Wikidata
from adscout.llm.adapter import CallSink
from adscout.sources.fetcher import FIXTURE_CONTACT, Fetcher, SourceCallRecord, SourceContext

CONTEXT = SourceContext(
    run_id="20261019T000000Z-aaaaaa",
    step="enrich",
    lead_id="0192f0c1-0000-7000-8000-000000000001",
    parent_span_id="0123456789abcdef",
)


def snak(prop: str, value: Any, kind: str) -> dict[str, Any]:
    return {"snaktype": "value", "property": prop, "datavalue": {"value": value, "type": kind}}


def item(qid: str) -> dict[str, Any]:
    return {"entity-type": "item", "id": qid, "numeric-id": int(qid[1:])}


def time(text: str, precision: int) -> dict[str, Any]:
    return snak("P585", {"time": text, "precision": precision, "timezone": 0}, "time")


def statement(
    prop: str, value: Any, kind: str = "wikibase-entityid", rank: str = "normal", **qualifiers: Any
) -> dict[str, Any]:
    found: dict[str, Any] = {"type": "statement", "rank": rank, "mainsnak": snak(prop, value, kind)}
    if qualifiers:
        found["qualifiers"] = {name: [value] for name, value in qualifiers.items()}
    return found


def amount(value: str, unit: str = "1") -> dict[str, Any]:
    return {"amount": value, "unit": unit}


def entity(qid: str, label: str, **claims: list[dict[str, Any]]) -> dict[str, Any]:
    return {"entities": {qid: {"id": qid, "labels": {"en": {"value": label}}, "claims": claims}}}


ENTITIES = {
    "Q100": entity(
        "Q100",
        "Alpha Gear",
        P856=[statement("P856", "https://www.alpha.test/", "string")],
        P17=[statement("P17", item("Q30"))],
        P1128=[
            statement("P1128", amount("+1200"), "quantity", P585=time("+2023-00-00T00:00:00Z", 9)),
            statement("P1128", amount("+1500"), "quantity", P585=time("+2025-06-30T00:00:00Z", 11)),
            statement("P1128", amount("+9"), "quantity", "deprecated"),
        ],
        P2139=[
            statement(
                "P2139",
                amount("+2500000000", USD),
                "quantity",
                P585=time("+2025-00-00T00:00:00Z", 9),
            ),
            statement(
                "P2139", amount("+3000000000", "http://www.wikidata.org/entity/Q4916"), "quantity"
            ),
        ],
        P414=[statement("P414", item("Q13677"))],
        P749=[statement("P749", item("Q200"))],
        P5531=[statement("P5531", "0001234567", "string")],
        P2397=[statement("P2397", "UCabc", "string")],
        P2002=[statement("P2002", "alphagear", "string")],
    ),
    "Q101": entity(
        "Q101",
        "Alpha Gear (band)",
        P856=[statement("P856", "https://alphagear-band.test/", "string")],
    ),
    "Q30": entity("Q30", "United States", P297=[statement("P297", "US", "string")]),
    "Q200": entity("Q200", "Parent Holdings", P31=[statement("P31", item("Q4830453"))]),
}


def revenue_fact(
    fy: int, start: str, end: str, val: float, form: str = "10-K", fp: str = "FY"
) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "val": val,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": f"{fy + 1}-02-20",
    }


REVENUES = {
    "cik": 1234567,
    "taxonomy": "us-gaap",
    "tag": "Revenues",
    "units": {
        "USD": [
            revenue_fact(2024, "2024-01-01", "2024-12-31", 2.4e9),
            revenue_fact(2025, "2025-01-01", "2025-12-31", 2.6e9),
            revenue_fact(2026, "2026-01-01", "2026-03-31", 0.7e9, "10-Q", "Q1"),
            revenue_fact(2025, "2025-10-01", "2025-12-31", 0.8e9),  # a quarter inside the 10-K
        ]
    },
}


class Api:
    """Answers the Wikidata and EDGAR URLs the clients ask for, and logs every request."""

    def __init__(self, entities: dict[str, Any], sec: dict[str, Any]) -> None:
        self.entities = entities
        self.sec = sec
        self.log: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.log.append(str(request.url))
        path = request.url.path
        if path == "/w/api.php":
            search = parse_qs(request.url.query.decode())["search"][0]
            hits = [{"id": qid} for qid in ("Q101", "Q100")] if search == "Alpha Gear" else []
            return httpx2.Response(200, json={"search": hits})
        if path.startswith("/wiki/Special:EntityData/"):
            qid = path.rsplit("/", 1)[1].removesuffix(".json")
            if qid in self.entities:
                return httpx2.Response(200, json=self.entities[qid])
        if path.startswith("/api/xbrl/companyconcept/"):
            tag = path.rsplit("/", 1)[1].removesuffix(".json")
            if tag in self.sec:
                return httpx2.Response(200, json=self.sec[tag])
        return httpx2.Response(404, json={"error": "not found"})


def clients(api: Api) -> tuple[Wikidata, Sec, CallSink]:
    sink = CallSink()
    fetcher = Fetcher(
        "fixture",
        httpx2.MockTransport(api),
        sink,
        contact=FIXTURE_CONTACT,
        clock=lambda: 0.0,
        sleep=lambda seconds: None,
        min_interval_s=0,
    )
    return Wikidata(fetcher), Sec(fetcher), sink


def by_field(candidates: list[Any]) -> dict[str, Any]:
    return {candidate.field: candidate for candidate in candidates}


def test_wikidata_matches_the_domain_not_the_namesake() -> None:
    api = Api(ENTITIES, {})
    wikidata, _, sink = clients(api)
    result = wikidata.enrich("Alpha Gear", "alpha.test", CONTEXT)
    assert result is not None and result.entity.qid == "Q100" and result.cik == 1234567
    fields = by_field(result.candidates)
    assert fields["hq_country"].value == "US"
    assert fields["ownership"].value == "public"
    assert fields["parent"].value == "Parent Holdings"
    assert (fields["employee_count"].value, fields["employee_count"].as_of) == (1500, "2025-06-30")
    assert fields["revenue_usd"].value == {
        "amount": 2500000000,
        "currency": "USD",
        "fiscal_year": 2025,
    }
    assert fields["revenue_usd"].as_of == "2025"
    assert [account["platform"] for account in fields["social_accounts"].value] == ["x", "youtube"]
    assert all(c.source_url == "https://www.wikidata.org/wiki/Q100" for c in result.candidates)
    assert all(c.source_kind == "wikidata" and c.source_call_id for c in result.candidates)
    assert not any("robots.txt" in url for url in api.log)  # an API, not crawled
    kinds = {record.kind for record in sink.drain() if isinstance(record, SourceCallRecord)}
    assert kinds == {"wikidata"}


def test_country_lookups_are_cached_per_run() -> None:
    api = Api(ENTITIES, {})
    wikidata, _, _ = clients(api)
    wikidata.enrich("Alpha Gear", "alpha.test", CONTEXT)
    wikidata.enrich("Alpha Gear", "alpha.test", CONTEXT)
    assert sum(url.endswith("/Q30.json") for url in api.log) == 1


def test_preferred_rank_beats_a_later_normal_statement() -> None:
    entities = dict(ENTITIES)
    data = entity(
        "Q100",
        "Alpha Gear",
        P856=[statement("P856", "https://alpha.test/", "string")],
        P1128=[
            statement(
                "P1128",
                amount("+700"),
                "quantity",
                "preferred",
                P585=time("+2020-01-00T00:00:00Z", 10),
            ),
            statement("P1128", amount("+900"), "quantity", P585=time("+2025-01-01T00:00:00Z", 11)),
        ],
        P749=[statement("P749", item("Q5000"))],
    )
    entities["Q100"] = data
    entities["Q5000"] = entity("Q5000", "A Founder", P31=[statement("P31", item("Q5"))])
    wikidata, _, _ = clients(Api(entities, {}))
    result = wikidata.enrich("Alpha Gear", "alpha.test", CONTEXT)
    assert result is not None
    fields = by_field(result.candidates)
    assert (fields["employee_count"].value, fields["employee_count"].as_of) == (700, "2020-01")
    assert "parent" not in fields  # a person is never stored as a parent
    assert fields["ownership"].value == "subsidiary"


def test_no_matching_item_gives_nothing() -> None:
    wikidata, _, _ = clients(Api(ENTITIES, {}))
    assert wikidata.enrich("Unknown Gear", "unknown.test", CONTEXT) is None
    assert wikidata.enrich("Alpha Gear", "other.test", CONTEXT) is None


def test_sec_reads_the_latest_full_fiscal_year_from_a_10k() -> None:
    api = Api({}, {"Revenues": REVENUES})
    _, sec, _ = clients(api)
    fields = by_field(sec.enrich(1234567, CONTEXT))
    assert fields["revenue_usd"].value == {"amount": 2.6e9, "currency": "USD", "fiscal_year": 2025}
    assert fields["revenue_usd"].as_of == "2025-12-31"
    assert fields["ownership"].value == "public"
    assert "employee_count" not in fields
    assert fields["revenue_usd"].source_url == (
        "https://data.sec.gov/api/xbrl/companyconcept/CIK0001234567/us-gaap/Revenues.json"
    )
    # The first revenue tag is not used by this filer, so the client moved on to the next.
    assert [url.rsplit("/", 1)[1] for url in api.log] == [
        "RevenueFromContractWithCustomerExcludingAssessedTax.json",
        "Revenues.json",
        "EntityNumberOfEmployees.json",
    ]


def test_sec_employees_when_the_filer_tags_them() -> None:
    employees = {
        "units": {
            "pure": [{"end": "2025-12-31", "val": 3100, "form": "10-K", "filed": "2026-02-20"}]
        }
    }
    _, sec, _ = clients(Api({}, {"EntityNumberOfEmployees": employees}))
    fields = by_field(sec.enrich(1234567, CONTEXT))
    assert (fields["employee_count"].value, fields["employee_count"].as_of) == (3100, "2025-12-31")
    assert "revenue_usd" not in fields


@pytest.mark.parametrize("data", [None, {}, {"units": {"USD": [{"form": "10-K"}]}}])
def test_latest_annual_tolerates_missing_facts(data: Any) -> None:
    assert latest_annual(data, "USD") is None
