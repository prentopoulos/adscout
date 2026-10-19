"""The polite fetcher, robots.txt and egress rules (Phase 2 design, decisions 10 and 28).

Sites are served in-process (httpx2 mock transports or files on disk); nothing leaves the
process, and pytest-socket would refuse it if it tried.
"""

import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx2
import pytest

from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.llm.adapter import CallSink, write_calls
from adscout.llm.cache import ReplayCache
from adscout.sources import robots
from adscout.sources.fetcher import (
    FIXTURE_CONTACT,
    MAX_BYTES,
    ContactMissing,
    Fetcher,
    FetchFailed,
    FetchRefused,
    FixtureTransport,
    RecordingTransport,
    ReplayPageTransport,
    SourceCallRecord,
    SourceContext,
    live_contact,
    user_agent,
)
from adscout.sources.urls import egress_problem, on_site

SITE = "example.test"
CONTEXT = SourceContext(
    run_id="20261019T000000Z-aaaaaa",
    step="enrich",
    lead_id="0192f0c1-0000-7000-8000-000000000001",
    parent_span_id="0123456789abcdef",
)


class Clock:
    """A fake monotonic clock whose sleep moves time forward."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


Handler = Callable[[httpx2.Request], httpx2.Response]


def site(pages: dict[str, httpx2.Response], log: list[str] | None = None) -> Handler:
    def handle(request: httpx2.Request) -> httpx2.Response:
        if log is not None:
            log.append(str(request.url))
        return pages.get(request.url.path, httpx2.Response(404, text="missing"))

    return handle


def html(text: str = "<p>hi</p>", **headers: str) -> httpx2.Response:
    return httpx2.Response(
        200, headers={"content-type": "text/html; charset=utf-8", **headers}, text=text
    )


def fetcher(handler: Handler, clock: Clock | None = None) -> tuple[Fetcher, CallSink]:
    sink = CallSink()
    tick = clock or Clock()
    found = Fetcher(
        "fixture",
        httpx2.MockTransport(handler),
        sink,
        contact=FIXTURE_CONTACT,
        clock=tick,
        sleep=tick.sleep,
    )
    return found, sink


def records(sink: CallSink) -> list[SourceCallRecord]:
    return [record for record in sink.drain() if isinstance(record, SourceCallRecord)]


# --- robots.txt -------------------------------------------------------------------------


def test_robots_longest_match_wins_and_allow_wins_a_tie() -> None:
    rules = robots.parse(
        "User-agent: *\nDisallow: /shop\nAllow: /shop/news\nDisallow: /a\nAllow: /a\n"
    )
    assert not rules.allowed("/shop/cart")
    assert rules.allowed("/shop/news/today")
    assert rules.allowed("/a") and rules.allowed("/a/b")  # equal rules: Allow wins


def test_robots_wildcards_end_anchor_and_percent_encoding() -> None:
    rules = robots.parse("User-agent: *\nDisallow: /*.pdf$\nDisallow: /private*/x\n")
    assert not rules.allowed("/files/report.pdf")
    assert rules.allowed("/files/report.pdf?download=1")
    assert not rules.allowed("/private-area/x")
    assert robots.parse("User-agent: *\nDisallow: /%7Euser\n").allowed("/~user") is False


def test_robots_our_group_beats_the_star_group() -> None:
    text = (
        "User-agent: *\nDisallow: /\n\n"
        "User-agent: AdScoutBot\nUser-agent: other\nAllow: /\nCrawl-delay: 5\n"
    )
    rules = robots.parse(text)
    assert rules.allowed("/news") and rules.crawl_delay == 5
    assert not robots.parse("User-agent: AdScout\nDisallow: /\n").disallow_all
    assert robots.parse("User-agent: AdScout\nDisallow: /\n").allowed("/x")
    assert robots.parse("").allowed("/anything")


@pytest.mark.parametrize(
    ("status", "allowed"), [(200, True), (404, True), (410, True), (401, False), (403, False)]
)
def test_robots_status_rules(status: int, allowed: bool) -> None:
    assert robots.rules_for_status(status, "").allowed("/") is allowed
    assert not robots.rules_for_status(503, "User-agent: *\nAllow: /\n").allowed("/")


def test_robots_disallow_is_obeyed_and_recorded() -> None:
    log: list[str] = []
    robots_txt = httpx2.Response(200, text="User-agent: *\nDisallow: /news\n")
    get, sink = fetcher(site({"/robots.txt": robots_txt, "/": html()}, log))
    with pytest.raises(FetchRefused, match="robots"):
        get.fetch(f"https://{SITE}/news/launch", CONTEXT, site=SITE)
    get.fetch(f"https://{SITE}/", CONTEXT, site=SITE)
    assert log == [f"https://{SITE}/robots.txt", f"https://{SITE}/"]  # robots read once
    rows = records(sink)
    assert [(r.kind, r.status, r.robots_decision) for r in rows] == [
        ("robots", "succeeded", None),
        ("page", "refused", "disallowed"),
        ("page", "succeeded", "allowed"),
    ]
    assert rows[1].http_status is None and rows[2].http_status == 200


@pytest.mark.parametrize("failure", ["status", "network"])
def test_unreachable_robots_disallows_everything(failure: str) -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        if failure == "network":
            raise httpx2.ConnectError("refused")
        return httpx2.Response(503) if request.url.path == "/robots.txt" else html()

    get, sink = fetcher(handle)
    with pytest.raises(FetchRefused, match="robots"):
        get.fetch(f"https://{SITE}/", CONTEXT, site=SITE)
    assert records(sink)[0].status == "failed"


# --- politeness -------------------------------------------------------------------------


def test_user_agent_names_the_bot_and_contact_and_sends_no_cookies() -> None:
    seen: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx2.Response(404)
        return html(**{"set-cookie": "session=abc; Path=/"})

    get, _ = fetcher(handle)
    get.fetch(f"https://{SITE}/a", CONTEXT, site=SITE)
    get.fetch(f"https://{SITE}/b", CONTEXT, site=SITE)
    agent = seen[0].headers["user-agent"]
    assert agent == user_agent(FIXTURE_CONTACT)
    assert agent.startswith("AdScoutBot/") and "(portfolio research bot; " in agent
    assert " httpx2/" in agent
    assert all("cookie" not in request.headers for request in seen)
    assert all(request.method == "GET" for request in seen)


def test_requests_to_one_host_wait_a_second_or_the_crawl_delay() -> None:
    clock = Clock()
    pages = {"/robots.txt": httpx2.Response(200, text="User-agent: *\nCrawl-delay: 4\n")}
    pages |= {"/a": html(), "/b": html()}
    get, _ = fetcher(site(pages), clock)
    get.fetch(f"https://{SITE}/a", CONTEXT, site=SITE)
    get.fetch(f"https://{SITE}/b", CONTEXT, site=SITE)
    # robots.txt, then /a after 1 s (no delay known yet), then /b after the 4 s Crawl-delay.
    assert clock.sleeps == [1.0, 4.0]


def test_oversized_page_is_cut_and_refused() -> None:
    big = httpx2.Response(
        200, headers={"content-type": "text/html"}, content=b"x" * (MAX_BYTES + 10)
    )
    get, sink = fetcher(site({"/robots.txt": httpx2.Response(404), "/": big}))
    with pytest.raises(FetchFailed, match="over 2000000 bytes"):
        get.fetch(f"https://{SITE}/", CONTEXT, site=SITE)
    assert records(sink)[-1].bytes == MAX_BYTES + 1


def test_redirects_stay_on_site_and_stop_after_three() -> None:
    def moved(to: str) -> httpx2.Response:
        return httpx2.Response(301, headers={"location": to})

    pages = {
        "/robots.txt": httpx2.Response(404),
        "/old": moved("/new"),
        "/new": html("<p>new</p>"),
        "/away": moved("https://elsewhere.test/"),
        "/loop1": moved("/loop2"),
        "/loop2": moved("/loop3"),
        "/loop3": moved("/loop4"),
        "/loop4": moved("/loop5"),
    }
    get, _ = fetcher(site(pages))
    page = get.fetch(f"https://{SITE}/old", CONTEXT, site=SITE)
    assert page.final_url == f"https://{SITE}/new" and "new" in page.text
    with pytest.raises(FetchRefused, match=r"leaves example.test"):
        get.fetch(f"https://{SITE}/away", CONTEXT, site=SITE)
    with pytest.raises(FetchRefused, match="more than 3 redirects"):
        get.fetch(f"https://{SITE}/loop1", CONTEXT, site=SITE)


@pytest.mark.parametrize("status", [401, 403])
def test_forbidden_is_not_retried(status: int) -> None:
    log: list[str] = []
    get, _ = fetcher(site({"/robots.txt": httpx2.Response(404), "/": httpx2.Response(status)}, log))
    with pytest.raises(FetchFailed, match=f"HTTP {status} \\(not retried\\)"):
        get.fetch(f"https://{SITE}/", CONTEXT, site=SITE)
    assert log.count(f"https://{SITE}/") == 1


def test_one_retry_after_is_honoured_on_429() -> None:
    replies = [httpx2.Response(429, headers={"retry-after": "7"}), html()]
    clock = Clock()

    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404) if request.url.path == "/robots.txt" else replies.pop(0)

    get, sink = fetcher(handle, clock)
    assert get.fetch(f"https://{SITE}/", CONTEXT, site=SITE).status == 200
    assert 7.0 in clock.sleeps
    assert [r.http_status for r in records(sink)] == [404, 429, 200]

    again, _ = fetcher(site({"/robots.txt": httpx2.Response(404), "/": httpx2.Response(429)}))
    with pytest.raises(FetchFailed, match="HTTP 429"):
        again.fetch(f"https://{SITE}/", CONTEXT, site=SITE)


def test_non_text_content_is_refused() -> None:
    pdf = httpx2.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")
    get, _ = fetcher(site({"/robots.txt": httpx2.Response(404), "/r.pdf": pdf}))
    with pytest.raises(FetchFailed, match="application/pdf is not text"):
        get.fetch(f"https://{SITE}/r.pdf", CONTEXT, site=SITE)


# --- egress -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("ftp://example.test/", "scheme ftp"),
        ("https://user:pw@example.test/", "credentials"),
        ("https://93.184.216.34/", "IP address"),
        ("https://[::1]/", "IP address"),
        ("https://localhost/", "not a public DNS name"),
        ("https://intranet/", "not a public DNS name"),
        ("https://printer.local/", "not a public DNS name"),
        ("https://example.test:8080/", "port 8080"),
        ("https://example.test/?q=" + "a" * 300, "query string"),
        ("https://attacker.test/", "outside example.test"),
    ],
)
def test_unsafe_urls_are_refused_before_any_request(url: str, reason: str) -> None:
    log: list[str] = []
    get, sink = fetcher(site({}, log))
    with pytest.raises(FetchRefused, match=reason):
        get.fetch(url, CONTEXT, site=SITE)
    assert log == []
    assert records(sink)[0].status == "refused"


def test_resolver_refuses_names_that_point_inside() -> None:
    assert egress_problem("https://example.test/", lambda host: ["93.184.216.34"]) is None
    assert "non-public" in str(egress_problem("https://evil.test/", lambda host: ["10.0.0.5"]))
    assert "non-public" in str(egress_problem("https://evil.test/", lambda host: ["127.0.0.1"]))

    def fails(host: str) -> list[str]:
        raise OSError("no such host")

    assert "did not resolve" in str(egress_problem("https://gone.test/", fails))
    assert on_site("https://shop.example.test/x", SITE)
    assert not on_site("https://example.test.evil.test/", SITE)


def test_live_fetching_needs_a_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADSCOUT_CONTACT", raising=False)
    with pytest.raises(ContactMissing, match="ADSCOUT_CONTACT"):
        live_contact(tmp_path / ".env")
    (tmp_path / ".env").write_text("ADSCOUT_CONTACT=bot@example.test\n", encoding="utf-8")
    assert live_contact(tmp_path / ".env") == "bot@example.test"


# --- transports and records -------------------------------------------------------------


def test_fixture_sites_are_served_from_files(tmp_path: Path) -> None:
    root = tmp_path / "sites"
    (root / SITE).mkdir(parents=True)
    (root / SITE / "index.html").write_text("<h1>Home</h1>", encoding="utf-8")
    (root / SITE / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    clock = Clock()
    get = Fetcher(
        "fixture",
        FixtureTransport(root),
        CallSink(),
        contact=FIXTURE_CONTACT,
        clock=clock,
        sleep=clock.sleep,
    )
    assert "Home" in get.fetch(f"https://{SITE}/", CONTEXT, site=SITE).text
    with pytest.raises(FetchFailed, match="HTTP 404"):
        get.fetch(f"https://{SITE}/missing", CONTEXT, site=SITE)
    with pytest.raises(FetchFailed, match="HTTP 404"):
        get.fetch(f"https://{SITE}/../secret.txt", CONTEXT, site=SITE)


def test_recorded_pages_replay_without_the_network(tmp_path: Path) -> None:
    cache = ReplayCache(tmp_path / "cache.db")
    pages = {"/robots.txt": httpx2.Response(404), "/": html("<p>first</p>")}
    clock = Clock()
    live = Fetcher(
        "live",
        RecordingTransport(cache, "run-live", httpx2.MockTransport(site(pages))),
        CallSink(),
        contact=FIXTURE_CONTACT,
        clock=clock,
        sleep=clock.sleep,
    )
    original = live.fetch(f"https://{SITE}/", CONTEXT, site=SITE)
    replay = Fetcher(
        "replay",
        ReplayPageTransport(cache, "run-live"),
        CallSink(),
        contact=FIXTURE_CONTACT,
        clock=clock,
        sleep=clock.sleep,
    )
    again = replay.fetch(f"https://{SITE}/", CONTEXT, site=SITE)
    assert again.body == original.body and again.content_sha256 == original.content_sha256
    with pytest.raises(FetchFailed, match="never fetched"):
        replay.fetch(f"https://{SITE}/other", CONTEXT, site=SITE)
    cache.close()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


def test_source_call_rows_are_written(db: sqlite3.Connection) -> None:
    now = utc_now()
    db.execute(
        "INSERT INTO runs (run_id, kind, segment_id, status, started_at, source, code_revision, "
        "code_dirty, lock_digest, package_version, agent_version, prompt_version, "
        "python_version, platform, schema_version, budgets_json, null_reasons_json, pid, host) "
        "VALUES (?, 'pipeline', 's', 'running', ?, 'fixture', 'abc', 0, 'x', '0', 'v', 'none', "
        "'3.13', 't', 2, '{}', '{}', 1, 'h')",
        (CONTEXT.run_id, now),
    )
    db.execute(
        "INSERT INTO companies (company_id, domain, name, created_run_id, created_at) "
        "VALUES (1, ?, 'Example', ?, ?)",
        (SITE, CONTEXT.run_id, now),
    )
    db.execute(
        "INSERT INTO leads VALUES (?, 's', 1, 'test', 'none', 'v', ?, ?)",
        (CONTEXT.lead_id, CONTEXT.run_id, now),
    )
    db.execute(
        "INSERT INTO step_runs (run_id, step, seq, implementation, implementation_version, "
        "status, started_at, null_reasons_json) VALUES (?, 'enrich', 2, 'real', '1', 'running', "
        "?, '{}')",
        (CONTEXT.run_id, now),
    )
    get, sink = fetcher(site({"/robots.txt": httpx2.Response(404), "/": html()}))
    get.fetch(f"https://{SITE}/", CONTEXT, site=SITE)
    with pytest.raises(FetchRefused):
        get.fetch("https://10.0.0.1/", CONTEXT, site=SITE)
    write_calls(db, sink.drain())
    rows = db.execute("SELECT kind, status, cost_usd, operation FROM source_calls").fetchall()
    assert [tuple(row) for row in rows] == [
        ("robots", "succeeded", 0.0, "execute_tool"),
        ("page", "succeeded", 0.0, "execute_tool"),
        ("page", "refused", 0.0, "execute_tool"),
    ]
