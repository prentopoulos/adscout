"""The research team on a synthetic lead: plan, workers, verifier, merge and brief outcomes.

Model answers are scripted per role and per worker turn; pages are served in-process.
"""

import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx2
import pytest
from anthropic.types import Message

from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.ids import uuid7
from adscout.llm.adapter import FakeTransport, ModelAdapter, ModelRequest
from adscout.llm.budget import SpendLedger
from adscout.llm.fakes import fake_message
from adscout.llm.prices import load_price_table
from adscout.llm.prompts import load_prompt
from adscout.pipeline.contracts import Lead
from adscout.pipeline.recorder import Run
from adscout.pipeline.registry import LEAD_RESEARCH_CAPS, SINGLE_CAPS
from adscout.research.handoffs import Claim
from adscout.research.step import Researcher, store
from adscout.research.verifier import FetchedPage, normalize_url, verify
from adscout.sources.fetcher import FIXTURE_CONTACT, Fetcher

PROMPTS = {
    name: load_prompt(name)
    for name in ("research_plan", "research_worker", "research_single", "research_merge")
}
PAGES = {
    "https://news.example.test/alpha-k1": (
        "<p>Alpha Gear launched the K1 keyboard in September 2026.</p>"
    ),
    "https://alpha.test/": "<p>Alpha Gear makes keyboards and mice for PC gamers.</p>"
    '<a href="https://attacker.test/steal">more</a>',
    "https://ads.example.test/alpha": (
        "<p>Alpha Gear runs video ads on gaming channels every month.</p>"
    ),
    "https://news.example.test/alpha-team": "<p>Alpha Gear sponsors the Example Esports team.</p>",
}
QUOTES = {
    "worker_audience": (
        "audience_channels",
        "https://alpha.test/",
        "Alpha Gear makes keyboards and mice for PC gamers.",
    ),
    "worker_ads": (
        "ad_activity",
        "https://ads.example.test/alpha",
        "Alpha Gear runs video ads on gaming channels every month.",
    ),
    "worker_launches": (
        "launches",
        "https://news.example.test/alpha-k1",
        "Alpha Gear launched the K1 keyboard in September 2026.",
    ),
}


def web(log: list[str]) -> Callable[[httpx2.Request], httpx2.Response]:
    def handle(request: httpx2.Request) -> httpx2.Response:
        log.append(str(request.url))
        url = str(request.url)
        if request.url.path == "/robots.txt":
            return httpx2.Response(404)
        if url in PAGES:
            return httpx2.Response(200, headers={"content-type": "text/html"}, text=PAGES[url])
        return httpx2.Response(404)

    return handle


def task_of(request: ModelRequest) -> dict[str, Any]:
    first = request.messages[0]["content"]
    match = re.search(r"<task>\n(.*)\n</task>", str(first), re.DOTALL)
    assert match, first
    return dict(json.loads(match.group(1)))


def turns(request: ModelRequest) -> int:
    return sum(message["role"] == "assistant" for message in request.messages)


def search_then_fetch(worker: str, results: list[str], fetch: str) -> Message:
    return fake_message(
        "claude-haiku-5-5",
        stop_reason="tool_use",
        web_search_requests=1,
        input_tokens=2000,
        output_tokens=120,
        content=[
            {
                "type": "server_tool_use",
                "id": f"srv_{worker}",
                "name": "web_search",
                "input": {"query": f"Alpha Gear {worker}"},
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": f"srv_{worker}",
                "content": [
                    {
                        "type": "web_search_result",
                        "url": url,
                        "title": "r",
                        "encrypted_content": "x",
                    }
                    for url in results
                ],
            },
            {
                "type": "tool_use",
                "id": f"fetch_{worker}",
                "name": "fetch_page",
                "input": {"url": fetch},
            },
        ],
    )


def submit(worker: str, claims: list[dict[str, str]], gaps: list[str] | None = None) -> Message:
    return fake_message(
        "claude-haiku-5-5",
        stop_reason="tool_use",
        input_tokens=2500,
        output_tokens=200,
        content=[
            {
                "type": "tool_use",
                "id": f"submit_{worker}",
                "name": "submit_findings",
                "input": {"claims": claims, "gaps": gaps or []},
            }
        ],
    )


def honest(worker: str) -> list[Callable[[ModelRequest], Message]]:
    topic, url, quote = QUOTES[worker]
    return [
        lambda request: search_then_fetch(worker, [url], url),
        lambda request: submit(
            worker, [{"topic": topic, "text": quote, "source_url": url, "quote": quote}]
        ),
    ]


class Brain:
    """Scripted answers: the plan, each worker's turns, and the merge."""

    def __init__(
        self, workers: dict[str, list[Callable[[ModelRequest], Message]]], plan: Any = None
    ) -> None:
        self.workers = workers
        self.plan = plan or {
            "assignments": [
                {"worker": w, "questions": [f"What about {w}?"]}
                for w in ("worker_audience", "worker_ads", "worker_launches")
            ]
        }
        self.merge_claims: list[str] = []

    def __call__(self, request: ModelRequest) -> Message:
        system = str(request.system[0]["text"])
        if system.startswith(PROMPTS["research_plan"].text):
            return fake_message(request.model, data=self.plan)
        if system.startswith(PROMPTS["research_merge"].text):
            claims = json.loads(
                str(request.messages[0]["content"]).split("\n", 1)[1].rsplit("\n", 1)[0]
            )
            self.merge_claims = [claim["id"] for claim in claims]
            points = [{"text": claim["text"], "claim_ids": [claim["id"]]} for claim in claims]
            return fake_message(request.model, data={"summary_points": points})
        script = self.workers[task_of(request)["worker"]]
        return script[min(turns(request), len(script) - 1)](request)


LEAD = Lead(lead_id=str(uuid7()), company_id=1, domain="alpha.test", name="Alpha Gear")
FIELDS = {
    "categories": ["peripherals"],
    "recent_launches": [
        {"name": "K1", "date": "2026-09", "source_url": "https://news.example.test/alpha-k1"}
    ],
}


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


def research(
    db: sqlite3.Connection, brain: Brain, design: str = "multi"
) -> tuple[Any, Run, list[str], FakeTransport]:
    run = Run(db, "pipeline", "synthetic-demo", "fixture", {}, {})
    run.start()
    db.execute(
        "INSERT INTO companies VALUES (1, 'alpha.test', 'Alpha Gear', ?, ?)",
        (run.run_id, utc_now()),
    )
    db.execute(
        "INSERT INTO leads VALUES (?, 'synthetic-demo', 1, 'test', 'p-0', 'v', ?, ?)",
        (LEAD.lead_id, run.run_id, utc_now()),
    )
    log: list[str] = []
    transport = FakeTransport(brain)
    adapter = ModelAdapter(
        transport,
        load_price_table(),
        SpendLedger(None),
        run.calls,
        today=lambda: date(2026, 10, 19),
    )
    fetcher = Fetcher(
        "fixture",
        httpx2.MockTransport(web(log)),
        run.calls,
        contact=FIXTURE_CONTACT,
        clock=lambda: 0.0,
        sleep=lambda s: None,
        min_interval_s=0,
    )
    researcher = Researcher(adapter, fetcher, PROMPTS, design=design)  # type: ignore[arg-type]
    with run.step("research", "real", 1) as recorder:
        done = researcher.research(LEAD, FIELDS, run.run_id)
        recorder.defer(lambda: store(db, run.run_id, done))
        recorder.outcomes.append(done.outcome)
    return done, run, log, transport


def test_three_workers_verified_claims_and_a_complete_brief(db: sqlite3.Connection) -> None:
    brain = Brain({worker: honest(worker) for worker in QUOTES})
    done, _, _, transport = research(db, brain)
    assert done.brief.status == "complete" and done.outcome.outcome == "kept"
    assert done.outcome.flag is None
    assert sorted(done.brief.claim_ids) == ["A1", "D1", "L1"] == sorted(brain.merge_claims)
    workers = {task_of(r)["worker"] for r in transport.requests if r.tools}
    assert workers == {"worker_audience", "worker_ads", "worker_launches"}
    assert all(r.tools for r in transport.requests if task_of_or_none(r))
    stored = db.execute("SELECT claim_key, verified FROM claims ORDER BY claim_key").fetchall()
    assert [tuple(row) for row in stored] == [("A1", 1), ("D1", 1), ("L1", 1)]
    brief = db.execute("SELECT status, design, dropped_claims FROM briefs").fetchone()
    assert tuple(brief) == ("complete", "multi", 0)


def task_of_or_none(request: ModelRequest) -> dict[str, Any] | None:
    try:
        return task_of(request)
    except AssertionError:
        return None


def test_every_worker_call_nests_under_its_agent_under_the_research_span(
    db: sqlite3.Connection,
) -> None:
    brain = Brain({worker: honest(worker) for worker in QUOTES})
    research(db, brain)
    step = db.execute("SELECT span_id FROM spans WHERE operation = 'step'").fetchone()[0]
    agents = dict(
        db.execute(
            "SELECT span_id, parent_span_id FROM spans WHERE operation = 'invoke_agent'"
        ).fetchall()
    )
    assert set(agents.values()) == {step}
    names = {
        row[0] for row in db.execute("SELECT agent_name FROM spans WHERE agent_name IS NOT NULL")
    }
    assert names == {
        "research_plan",
        "worker_audience",
        "worker_ads",
        "worker_launches",
        "research_merge",
    }
    for parent, agent in db.execute("SELECT parent_span_id, agent_name FROM model_calls"):
        assert parent in agents, agent
    fetches = db.execute("SELECT parent_span_id FROM source_calls WHERE kind = 'page'").fetchall()
    assert {row[0] for row in fetches} <= set(agents)


def test_a_quote_missing_from_its_page_is_dropped_and_counted(db: sqlite3.Connection) -> None:
    topic, url, quote = QUOTES["worker_ads"]
    lying = [
        lambda request: search_then_fetch("worker_ads", [url], url),
        lambda request: submit(
            "worker_ads",
            [
                {"topic": topic, "text": quote, "source_url": url, "quote": quote},
                {
                    "topic": topic,
                    "text": "Alpha Gear spends 10 million on ads.",
                    "source_url": url,
                    "quote": "Alpha Gear spends 10 million on ads yearly.",
                },
            ],
        ),
    ]
    brain = Brain({**{w: honest(w) for w in QUOTES}, "worker_ads": lying})
    done, *_ = research(db, brain)
    assert "D2" not in done.brief.claim_ids and "D2" not in brain.merge_claims
    row = db.execute(
        "SELECT verified, quote_found, drop_reason FROM claims WHERE claim_key = 'D2'"
    ).fetchone()
    assert tuple(row) == (0, 0, "its quote is not on the page (or is under 20 characters)")
    assert db.execute("SELECT dropped_claims FROM briefs").fetchone()[0] == 1


def test_a_url_seen_only_inside_a_page_is_never_fetched(db: sqlite3.Connection) -> None:
    topic, url, quote = QUOTES["worker_audience"]

    def fetch_attacker(request: ModelRequest) -> Message:
        return fake_message(
            "claude-haiku-5-5",
            stop_reason="tool_use",
            content=[
                {
                    "type": "tool_use",
                    "id": "steal",
                    "name": "fetch_page",
                    "input": {"url": "https://attacker.test/steal"},
                },
            ],
        )

    hijacked = [
        lambda request: search_then_fetch("worker_audience", [url], url),
        fetch_attacker,
        lambda request: submit(
            "worker_audience", [{"topic": topic, "text": quote, "source_url": url, "quote": quote}]
        ),
    ]
    brain = Brain({**{w: honest(w) for w in QUOTES}, "worker_audience": hijacked})
    _, _, log, transport = research(db, brain)
    assert not any("attacker.test" in sent for sent in log)
    refused = db.execute(
        "SELECT status, detail FROM source_calls WHERE target LIKE '%attacker.test%'"
    ).fetchone()
    assert refused["status"] == "refused" and "did not come from your searches" in refused["detail"]
    replies = [
        r
        for r in transport.requests
        if task_of_or_none(r) and task_of(r)["worker"] == "worker_audience"
    ]
    last_user = replies[-1].messages[-1]["content"]
    assert any(block.get("is_error") for block in last_user if isinstance(block, dict))


def test_a_third_page_is_refused_by_the_page_cap(db: sqlite3.Connection) -> None:
    topic, url, quote = QUOTES["worker_launches"]
    team = "https://news.example.test/alpha-team"

    def fetch(target: str, use_id: str) -> Callable[[ModelRequest], Message]:
        return lambda request: fake_message(
            "claude-haiku-5-5",
            stop_reason="tool_use",
            content=[
                {"type": "tool_use", "id": use_id, "name": "fetch_page", "input": {"url": target}},
            ],
        )

    greedy = [
        lambda request: search_then_fetch(
            "worker_launches", [url, team, "https://alpha.test/"], url
        ),
        fetch(team, "second"),
        fetch("https://alpha.test/", "third"),
        lambda request: submit(
            "worker_launches", [{"topic": topic, "text": quote, "source_url": url, "quote": quote}]
        ),
    ]
    brain = Brain({**{w: honest(w) for w in QUOTES}, "worker_launches": greedy})
    done, *_ = research(db, brain)
    run = next(r for r in done.runs if r.worker == "worker_launches")
    assert run.pages_read == 2 and "worker pages" in run.caps_hit
    assert done.outcome.flag == "research_partial"


def test_all_workers_failing_exits_as_research_failed(db: sqlite3.Connection) -> None:
    silent = [lambda request: fake_message("claude-haiku-5-5", text="I cannot help.")]
    brain = Brain({worker: silent for worker in QUOTES})
    done, *_ = research(db, brain)
    assert (done.outcome.outcome, done.outcome.reason) == ("exited", "research_failed")
    assert done.brief.status == "failed"
    assert db.execute("SELECT status FROM briefs").fetchone()[0] == "failed"


def test_the_plan_cannot_add_a_worker_or_a_url(db: sqlite3.Connection) -> None:
    plan = {
        "assignments": [
            {
                "worker": "worker_audience",
                "questions": ["See https://attacker.test/x for who buys"],
            },
            {"worker": "worker_fifth", "questions": ["Email the founder"]},
        ]
    }
    brain = Brain({worker: honest(worker) for worker in QUOTES}, plan=plan)
    _, _, _, transport = research(db, brain)
    tasks = {t["worker"]: t for t in (task_of_or_none(r) for r in transport.requests) if t}
    assert set(tasks) == {"worker_audience", "worker_ads", "worker_launches"}
    assert tasks["worker_audience"]["questions"] == ["See for who buys"]
    assert tasks["worker_ads"]["questions"] == [
        "Where and how does this company advertise or sponsor today?"
    ]
    assert tasks["worker_audience"]["seed_urls"] == [
        "https://alpha.test/",
        "https://news.example.test/alpha-k1",
    ]


def test_single_agent_baseline_has_the_same_search_and_page_budget(db: sqlite3.Connection) -> None:
    assert (SINGLE_CAPS.searches, SINGLE_CAPS.pages) == (
        LEAD_RESEARCH_CAPS.searches,
        LEAD_RESEARCH_CAPS.pages,
    )
    claims = [
        {"topic": topic, "text": quote, "source_url": url, "quote": quote}
        for topic, url, quote in QUOTES.values()
    ]
    alone = [
        lambda request: search_then_fetch(
            "research_single", [QUOTES["worker_launches"][1]], QUOTES["worker_launches"][1]
        ),
        lambda request: submit("research_single", claims),
    ]
    brain = Brain({"research_single": alone})
    done, _, _, transport = research(db, brain, design="single")
    assert done.brief.design == "single"
    assert {task_of(r)["worker"] for r in transport.requests if task_of_or_none(r)} == {
        "research_single"
    }
    assert all(r.model == "claude-sonnet-5-5" for r in transport.requests if r.tools)
    assert done.brief.claim_ids == ["S3"]  # only the launches page (third claim) was fetched
    assert done.outcome.flag == "research_partial"  # two topics uncovered


def test_verifier_normalizes_urls_text_and_numbers() -> None:
    page = FetchedPage(
        "https://www.alpha.test/news/", "Alpha Gear sold 1,500 units in 2025 — a record.", "c1"
    )
    fetched = {normalize_url(page.url): page}
    claims = [
        Claim(
            topic="launches",
            text="Alpha Gear sold 1500 units in 2025.",
            source_url="https://alpha.test/news",
            quote="alpha gear SOLD 1,500 units   in 2025 - a record.",
        ),
        Claim(
            topic="launches",
            text="Alpha Gear sold 2,000 units.",
            source_url="https://alpha.test/news",
            quote="Alpha Gear sold 1,500 units in 2025",
        ),
        Claim(
            topic="launches",
            text="Short quote.",
            source_url="https://alpha.test/news",
            quote="units",
        ),
        Claim(
            topic="ad_activity",
            text="CEO Jane Example said ads work.",
            source_url="https://alpha.test/news",
            quote="Alpha Gear sold 1,500 units in 2025",
        ),
        Claim(
            topic="ad_activity",
            text="Alpha Gear said ads work.",
            source_url="https://alpha.test/news",
            quote="Alpha Gear sold 1,500 units in 2025",
        ),
    ]
    checked = verify("worker_launches", claims, fetched, "Alpha Gear")
    assert [c.claim_id for c in checked] == ["L1", "L2", "L3", "L4", "L5"]
    assert [c.verified for c in checked] == [True, False, False, False, True]
    assert (checked[1].numbers_ok, checked[2].quote_found, checked[3].names_individual) == (
        False,
        False,
        True,
    )
