"""The real enrich step on synthetic companies, with fake models and in-process sites."""

import json
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx2
import pytest
from anthropic.types import Message

from adscout.config import load_segment
from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.enrichment.step import Enricher, store
from adscout.ids import uuid7
from adscout.llm.adapter import FakeTransport, ModelAdapter, ModelRequest
from adscout.llm.budget import SpendLedger
from adscout.llm.fakes import fake_message
from adscout.llm.invoke import HAIKU, SONNET
from adscout.llm.prices import load_price_table
from adscout.llm.prompts import load_prompt
from adscout.pipeline.contracts import Lead
from adscout.pipeline.recorder import Run
from adscout.sources.fetcher import FIXTURE_CONTACT, Fetcher
from adscout.sources.site_list import load_site_list, site_list_path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "config"
TODAY = date(2026, 10, 19)
USD = "http://www.wikidata.org/entity/Q4917"

HOME = """<html><head>
<script src="https://www.googletagmanager.com/gtm.js?id=GTM-1"></script>
<script src="https://connect.facebook.net/en_US/fbevents.js"></script></head>
<body><a href="/news">Newsroom</a> <a href="/shipping">Shipping</a>
<h1>Alpha Gear</h1><p>Keyboards and mice for PC gaming.</p></body></html>"""
NEWS = "<html><body><h1>News</h1><p>September 2026: we launched the Alpha K1.</p></body></html>"
SHIPPING = "<html><body><p>We ship to the United States and Canada.</p></body></html>"


def value(prop: str, data: Any, kind: str, **qualifiers: Any) -> dict[str, Any]:
    statement: dict[str, Any] = {
        "rank": "normal",
        "mainsnak": {
            "snaktype": "value",
            "property": prop,
            "datavalue": {"value": data, "type": kind},
        },
    }
    if qualifiers:
        statement["qualifiers"] = {
            name: [{"datavalue": {"value": {"time": time, "precision": 11}}}]
            for name, time in qualifiers.items()
        }
    return statement


ENTITIES = {
    "Q100": {
        "labels": {"en": {"value": "Alpha Gear"}},
        "claims": {
            "P856": [value("P856", "https://www.alpha.test/", "string")],
            "P17": [value("P17", {"id": "Q30"}, "wikibase-entityid")],
            "P1128": [
                value(
                    "P1128",
                    {"amount": "+1500", "unit": "1"},
                    "quantity",
                    P585="+2025-12-31T00:00:00Z",
                )
            ],
            "P414": [value("P414", {"id": "Q13677"}, "wikibase-entityid")],
            "P5531": [value("P5531", "0001234567", "string")],
        },
    },
    "Q30": {
        "labels": {"en": {"value": "United States"}},
        "claims": {"P297": [value("P297", "US", "string")]},
    },
}
REVENUE = {
    "units": {
        "USD": [
            {
                "start": "2025-01-01",
                "end": "2025-12-31",
                "val": 2.6e9,
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "filed": "2026-02-20",
            }
        ]
    }
}


class Web:
    """The company sites, Wikidata and EDGAR, served in-process; logs every URL asked for."""

    def __init__(self, sites: dict[str, dict[str, str]]) -> None:
        self.sites = sites
        self.log: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.log.append(str(request.url))
        host, path = request.url.host, request.url.path
        if host == "www.wikidata.org" and path == "/w/api.php":
            name = parse_qs(request.url.query.decode())["search"][0]
            hits = [{"id": "Q100"}] if name == "Alpha Gear" else []
            return httpx2.Response(200, json={"search": hits})
        if host == "www.wikidata.org":
            qid = path.rsplit("/", 1)[1].removesuffix(".json")
            if qid in ENTITIES:
                return httpx2.Response(200, json={"entities": {qid: ENTITIES[qid]}})
        if host == "data.sec.gov" and path.endswith(
            "/RevenueFromContractWithCustomerExcludingAssessedTax.json"
        ):
            return httpx2.Response(200, json=REVENUE)
        pages = self.sites.get(host, {})
        if path in pages:
            return httpx2.Response(200, headers={"content-type": "text/html"}, text=pages[path])
        return httpx2.Response(404, text="not found")


def search_reply(model: str, launches: list[dict[str, Any]]) -> Message:
    return fake_message(
        model,
        stop_reason="tool_use",
        web_search_requests=1,
        content=[
            {
                "type": "server_tool_use",
                "id": "srvtoolu_1",
                "name": "web_search",
                "input": {"query": "Bravo Gear launches"},
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_1",
                "content": [
                    {
                        "type": "web_search_result",
                        "url": "https://news.example.test/bravo-b2",
                        "title": "Bravo B2",
                        "encrypted_content": "x",
                        "page_age": "2026-08-01",
                    }
                ],
            },
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "submit_launches",
                "input": {"launches": launches},
            },
        ],
    )


class Models:
    """Fake model answers by role: the extractor's JSON, and the launch search's tool turn."""

    def __init__(
        self, extractions: list[dict[str, Any]], launches: list[dict[str, Any]] | None = None
    ) -> None:
        self.extractions = extractions
        self.launches = launches or []

    def __call__(self, request: ModelRequest) -> Message:
        if request.tools:
            return search_reply(request.model, self.launches)
        return fake_message(
            request.model, data=self.extractions.pop(0), input_tokens=3000, output_tokens=200
        )


def extraction(sells_in: list[str], launches: bool = True) -> dict[str, Any]:
    return {
        "categories": {"values": ["peripherals"], "source_url": "https://alpha.test/"},
        "sells_in": {"values": sells_in, "source_url": "https://alpha.test/shipping"},
        "recent_launches": (
            [{"name": "Alpha K1", "date": "2026-09", "source_url": "https://alpha.test/news"}]
            if launches
            else []
        ),
        "employee_count": None,
    }


SITES = {
    "alpha.test": {"/": HOME, "/news": NEWS, "/shipping": SHIPPING},
    "bravo.test": {"/": SHIPPING},
}


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


def setup(
    db: sqlite3.Connection, models: Models, *, mode: str = "fixture", site_list: Any = None
) -> tuple[Run, Enricher, Web, FakeTransport, dict[str, Lead]]:
    run = Run(db, "pipeline", "synthetic-demo", "fixture", {}, {})
    run.start()
    leads = {}
    for number, (domain, name) in enumerate(
        [("alpha.test", "Alpha Gear"), ("bravo.test", "Bravo Gear")], 1
    ):
        db.execute(
            "INSERT INTO companies (company_id, domain, name, created_run_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (number, domain, name, run.run_id, utc_now()),
        )
        lead = Lead(lead_id=str(uuid7()), company_id=number, domain=domain, name=name)
        db.execute(
            "INSERT INTO leads VALUES (?, 'synthetic-demo', ?, 'test', 'none', 'v', ?, ?)",
            (lead.lead_id, number, run.run_id, utc_now()),
        )
        leads[domain] = lead
    web = Web(SITES)
    transport = FakeTransport(models)
    adapter = ModelAdapter(
        transport, load_price_table(), SpendLedger(None), run.calls, today=lambda: TODAY
    )
    fetcher = Fetcher(
        mode,  # type: ignore[arg-type]
        httpx2.MockTransport(web),
        run.calls,
        contact=FIXTURE_CONTACT,
        clock=lambda: 0.0,
        sleep=lambda seconds: None,
        min_interval_s=0,
    )
    enricher = Enricher(
        adapter=adapter,
        fetcher=fetcher,
        segment=load_segment(FIXTURES / "segments" / "synthetic-demo.yaml"),
        extract_prompt=load_prompt("extract"),
        search_prompt=load_prompt("launch_search"),
        today=TODAY,
        site_list=site_list,
    )
    return run, enricher, web, transport, leads


def enrich_and_store(run: Run, enricher: Enricher, lead: Lead) -> Any:
    with run.step("enrich", "real", 1) as recorder:
        enriched = enricher.enrich(lead, run.run_id)
        recorder.defer(lambda: store(run.connection, run.run_id, enriched))
        recorder.outcomes.append(enriched.outcome)
    return enriched


def test_a_company_is_enriched_from_every_source(db: sqlite3.Connection) -> None:
    run, enricher, web, transport, leads = setup(db, Models([extraction(["US", "CA"])]))
    enriched = enrich_and_store(run, enricher, leads["alpha.test"])

    assert enriched.outcome.outcome == "kept"
    fields = enriched.summary()
    assert fields["categories"] == ["peripherals"] and fields["sells_in"] == ["CA", "US"]
    assert fields["employee_count"] == {"count": 1500}
    assert fields["hq_country"] == "US" and fields["ownership"] == "public"
    assert fields["revenue_usd"]["amount"] == 2.6e9
    assert [signal["tag"] for signal in fields["ad_signals"]] == [
        "google_tag_manager",
        "meta_pixel",
    ]
    assert fields["recent_launches"][0]["name"] == "Alpha K1"
    assert len(transport.requests) == 1  # one extraction; launches came from the pages
    assert [url for url in web.log if "alpha.test" in url] == [
        "https://alpha.test/robots.txt",
        "https://alpha.test/",
        "https://alpha.test/news",
        "https://alpha.test/shipping",
    ]

    rows = db.execute("SELECT * FROM enrichment_fields WHERE status = 'valid'").fetchall()
    assert {row["field"] for row in rows} == set(fields)
    for row in rows:
        assert (
            row["source_url"].startswith("https://") and row["source_kind"] and row["retrieved_at"]
        )
    signals = next(row for row in rows if row["field"] == "ad_signals")
    assert signals["method"] == "parsed" and signals["model_call_id"] is None
    employees = next(row for row in rows if row["field"] == "employee_count")
    assert employees["as_of"] == "2025-12-31" and employees["source_kind"] == "wikidata"


def test_calls_form_one_trace_under_the_lead_step_span(db: sqlite3.Connection) -> None:
    run, enricher, _, _, leads = setup(db, Models([extraction(["US", "CA"])]))
    enrich_and_store(run, enricher, leads["alpha.test"])
    step = db.execute("SELECT * FROM spans WHERE operation = 'step'").fetchone()
    agent = db.execute("SELECT * FROM spans WHERE operation = 'invoke_agent'").fetchone()
    call = db.execute("SELECT * FROM model_calls").fetchone()
    assert agent["parent_span_id"] == step["span_id"] and agent["agent_name"] == "extractor"
    assert call["parent_span_id"] == agent["span_id"] and call["trace_id"] == step["trace_id"]
    sources = db.execute("SELECT DISTINCT parent_span_id FROM source_calls").fetchall()
    assert [row[0] for row in sources] == [step["span_id"]]


def test_invalid_key_field_escalates_the_extraction_to_sonnet(db: sqlite3.Connection) -> None:
    run, enricher, _, transport, leads = setup(
        db, Models([extraction(["USA", "CA"]), extraction(["US", "CA"])])
    )
    enriched = enrich_and_store(run, enricher, leads["alpha.test"])
    assert [request.model for request in transport.requests] == [HAIKU, SONNET]
    assert enriched.summary()["sells_in"] == ["CA", "US"]
    roles = [row[0] for row in db.execute("SELECT call_role FROM model_calls ORDER BY started_at")]
    assert roles == ["primary", "escalation"]
    details = {row[0] for row in db.execute("SELECT status_detail FROM enrichment_fields")}
    assert "replaced by the escalation to Sonnet" in details
    assert "not ISO 3166-1 alpha-2 codes" in details


def test_missing_employee_count_exits_naming_the_field(db: sqlite3.Connection) -> None:
    models = Models([], launches=[])
    run, enricher, _, _, leads = setup(db, models)
    enricher.extract_prompt = load_prompt("extract")
    models.extractions = [
        {
            "categories": {"values": ["peripherals"], "source_url": "https://bravo.test/"},
            "sells_in": {"values": ["US", "CA"], "source_url": "https://bravo.test/"},
            "recent_launches": [],
            "employee_count": None,
        }
    ]
    enriched = enrich_and_store(run, enricher, leads["bravo.test"])
    assert enriched.outcome.reason == "missing_key_fields"
    assert enriched.outcome.detail.startswith("missing key fields: employee_count")
    assert "Wikidata has no item with this website" in enriched.outcome.detail


def test_live_run_never_reads_a_site_missing_from_the_approved_list(db: sqlite3.Connection) -> None:
    sites = load_site_list(site_list_path("synthetic-demo", FIXTURES / "site-checks"))
    run, enricher, web, _, leads = setup(db, Models([]), mode="live", site_list=sites)
    enriched = enrich_and_store(run, enricher, leads["bravo.test"])
    assert not any("bravo.test" in url for url in web.log)
    assert "the approved site list skips bravo.test" in enriched.outcome.detail
    refused = db.execute(
        "SELECT status, detail FROM source_calls WHERE target LIKE '%bravo.test%'"
    ).fetchone()
    assert refused["status"] == "refused" and "approved site list" in refused["detail"]


def test_launch_search_runs_when_the_pages_name_none(db: sqlite3.Connection) -> None:
    launches = [
        {"name": "Bravo B2", "date": "2026-08", "source_url": "https://news.example.test/bravo-b2"},
        {"name": "Made up", "date": "2026-07", "source_url": "https://invented.example.test/x"},
    ]
    models = Models([extraction(["US", "CA"], launches=False)], launches)
    run, enricher, _, transport, leads = setup(db, models)
    enriched = enrich_and_store(run, enricher, leads["alpha.test"])
    search = transport.requests[1]
    tool = next(tool for tool in search.tool_specs() if tool["name"] == "web_search")
    assert tool["type"] == "web_search_20250305" and tool["max_uses"] == 1
    assert tool["allowed_callers"] == ["direct"] and "linkedin.com" in tool["blocked_domains"]
    assert [item["name"] for item in enriched.summary()["recent_launches"]] == ["Bravo B2"]
    audit = db.execute("SELECT * FROM source_calls WHERE kind = 'web_search'").fetchone()
    assert audit["target"] == "Bravo Gear launches" and audit["cost_usd"] == 0
    assert json.loads(audit["results_json"])[0]["url"] == "https://news.example.test/bravo-b2"
    paid = db.execute(
        "SELECT web_search_requests, search_fee_usd FROM model_calls WHERE call_id = ?",
        (audit["model_call_id"],),
    ).fetchone()
    assert tuple(paid) == (1, 0.01)
    dropped = db.execute(
        "SELECT status_detail FROM enrichment_fields WHERE source_url LIKE '%invented%'"
    ).fetchone()
    assert dropped[0] == "not among the search results"


def test_failed_extraction_is_noted_and_the_lead_goes_on(db: sqlite3.Connection) -> None:
    bad = {"nothing": True}
    run, enricher, _, transport, leads = setup(db, Models([bad, bad, bad], launches=[]))
    enriched = enrich_and_store(run, enricher, leads["alpha.test"])
    assert len([r for r in transport.requests if not r.tools]) == 3  # primary, retry, fallback
    assert "extraction failed" in enriched.outcome.detail
    assert enriched.outcome.reason == "missing_key_fields"
