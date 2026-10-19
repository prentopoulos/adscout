"""The polite fetcher: every outside page and API read goes through it (design decision 10).

It names itself (`AdScoutBot/<version> (portfolio research bot; <contact>) httpx2/<version>`),
obeys robots.txt per RFC 9309, waits at least a second per host (or the site's Crawl-delay),
sends only GET without cookies, times out at 5 s to connect and 15 s to read, stops at 2 MB,
follows at most 3 redirects and only within the site, never retries 401 or 403 and honours
one Retry-After on a 429. Every request and every refusal writes a `source_calls` row.

The three modes differ only in their HTTP transport: `fixture` serves files from disk,
`replay` serves the responses a recorded live run received, and `live` uses the network and
records every response into the replay cache. Robots, pacing and limits run in all three.
"""

import hashlib
import json
import re
import sqlite3
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, fields
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import ClassVar, Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx2

from adscout.db.connection import utc_now
from adscout.env import ENV_FILE, env_value
from adscout.ids import uuid7
from adscout.llm.adapter import CallSink, new_span_id, trace_id_for
from adscout.llm.cache import ReplayCache
from adscout.pipeline.contracts import Step
from adscout.sources import robots
from adscout.sources.robots import RobotsRules
from adscout.sources.urls import Resolver, egress_problem, on_site

SourceMode = Literal["fixture", "replay", "live"]
SourceKind = Literal["robots", "page", "wikidata", "sec_edgar", "web_search"]
SourceStatus = Literal["succeeded", "failed", "refused"]

CONTACT_NAME = "ADSCOUT_CONTACT"
FIXTURE_CONTACT = "fixture-contact@example.test"
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3
MIN_INTERVAL_S = 1.0
MAX_RETRY_AFTER_S = 60.0
TIMEOUT = httpx2.Timeout(15.0, connect=5.0)
TEXT_TYPES = (
    "text/",
    "application/xhtml+xml",
    "application/json",
    "application/ld+json",
    "application/sparql-results+json",
)


class FetchRefused(Exception):
    """Not requested: egress rules, robots.txt or the site boundary."""

    def __init__(self, category: str, detail: str) -> None:
        super().__init__(f"{category}: {detail}")
        self.category = category
        self.detail = detail


class FetchFailed(Exception):
    """Requested, but no usable page came back."""


class ContactMissing(RuntimeError):
    """Live fetching needs a contact for the User-Agent."""


@dataclass(frozen=True)
class SourceContext:
    """Which run, step and lead a read belongs to, and its parent span in the lead's trace."""

    run_id: str
    step: Step
    lead_id: str
    parent_span_id: str


@dataclass(frozen=True)
class SourceCallRecord:
    """One `source_calls` row."""

    write_order: ClassVar[int] = 2

    call_id: str
    run_id: str
    step: str
    lead_id: str
    kind: str
    target: str
    mode: str
    status: SourceStatus
    robots_decision: str | None
    http_status: int | None
    bytes: int | None
    content_sha256: str | None
    results_json: str
    model_call_id: str | None
    detail: str
    latency_ms: int | None
    trace_id: str
    span_id: str
    parent_span_id: str
    started_at: str
    ended_at: str

    def insert(self, connection: sqlite3.Connection) -> None:
        columns = [item.name for item in fields(self)]
        connection.execute(
            f"INSERT INTO source_calls ({', '.join(columns)}) "  # noqa: S608
            f"VALUES ({', '.join('?' * len(columns))})",
            tuple(getattr(self, name) for name in columns),
        )


@dataclass(frozen=True)
class Page:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    call_id: str
    span_id: str

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def text(self) -> str:
        charset = "utf-8"
        for part in self.content_type.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                charset = value.strip("\"'")
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    def json(self) -> object:
        return json.loads(self.text)


def user_agent(contact: str) -> str:
    return (
        f"AdScoutBot/{version('adscout')} (portfolio research bot; {contact}) "
        f"httpx2/{httpx2.__version__}"
    )


def live_contact(env_file: Path = ENV_FILE) -> str:
    contact = env_value(CONTACT_NAME, env_file)
    if not contact:
        raise ContactMissing(f"live fetching needs {CONTACT_NAME} in the environment or .env")
    return contact


# --- transports -------------------------------------------------------------------------


class FixtureTransport(httpx2.BaseTransport):
    """Serves `<root>/<host>/<path>` files; `/` is `index.html`. Missing files are 404.

    A query string becomes `__<query>` after the path, and characters Windows forbids in
    file names (such as `:` in `Special:EntityData`) become `_`. A `.json` path or one with a
    `__format=json`-style query is served as JSON.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path.lstrip("/") or "index.html"
        query = request.url.query.decode()
        if query:
            path += "__" + query
        safe = re.sub(r'[\\:*?"<>|]', "_", path)
        target = (self.root / request.url.host / safe).resolve()
        if not target.is_relative_to(self.root) or not target.is_file():
            return httpx2.Response(404, text="not found")
        json_body = target.suffix.lower() == ".json" or "format=json" in query
        content_type = (
            "application/json"
            if json_body
            else "text/plain; charset=utf-8"
            if target.suffix.lower() == ".txt"
            else "text/html; charset=utf-8"
        )
        return httpx2.Response(
            200, headers={"content-type": content_type}, content=target.read_bytes()
        )


class RecordingTransport(httpx2.BaseTransport):
    """The network, with each response (up to the size limit) kept in the replay cache."""

    def __init__(self, cache: ReplayCache, run_id: str, inner: httpx2.BaseTransport) -> None:
        self.cache = cache
        self.run_id = run_id
        self.inner = inner
        self.seen: Counter[str] = Counter()
        self._lock = threading.Lock()

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        response = self.inner.handle_request(request)
        body = read_capped(_byte_stream(response))
        headers = list(response.headers.multi_items())
        url = str(request.url)
        with self._lock:
            self.seen[url] += 1
            occurrence = self.seen[url]
        self.cache.store_page(self.run_id, url, occurrence, response.status_code, headers, body)
        return httpx2.Response(response.status_code, headers=headers, content=body)


class ReplayPageTransport(httpx2.BaseTransport):
    """The responses a recorded run received, in the order it requested each URL."""

    def __init__(self, cache: ReplayCache, source_run_id: str) -> None:
        self.cache = cache
        self.source_run_id = source_run_id
        self.seen: Counter[str] = Counter()
        self._lock = threading.Lock()

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        with self._lock:
            self.seen[url] += 1
            occurrence = self.seen[url]
        found = self.cache.load_page(self.source_run_id, url, occurrence)
        if found is None:
            raise httpx2.ConnectError(f"replay: run {self.source_run_id} never fetched {url}")
        status, headers, body = found
        return httpx2.Response(status, headers=headers, content=body)


def _byte_stream(response: httpx2.Response) -> Iterable[bytes]:
    stream = response.stream
    if not isinstance(stream, httpx2.SyncByteStream):
        raise TypeError("the fetcher needs a synchronous transport")
    return stream


def read_capped(chunks: Iterable[bytes]) -> bytes:
    """At most MAX_BYTES + 1 bytes, so an oversized body is seen as oversized."""
    kept: list[bytes] = []
    size = 0
    try:
        for chunk in chunks:
            kept.append(chunk)
            size += len(chunk)
            if size > MAX_BYTES:
                break
    finally:
        close = getattr(chunks, "close", None)
        if callable(close):
            close()
    return b"".join(kept)[: MAX_BYTES + 1]


# --- the fetcher ------------------------------------------------------------------------


@dataclass
class _Host:
    lock: threading.Lock = field(default_factory=threading.Lock)
    next_at: float = 0.0
    rules: RobotsRules | None = None


class Fetcher:
    """Robots, pacing, limits and records around one HTTP transport."""

    def __init__(
        self,
        mode: SourceMode,
        transport: httpx2.BaseTransport,
        sink: CallSink,
        *,
        contact: str,
        resolver: Resolver | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        min_interval_s: float = MIN_INTERVAL_S,
    ) -> None:
        self.mode = mode
        self.sink = sink
        self.resolver = resolver
        self.clock = clock
        self.sleep = sleep
        self.min_interval_s = min_interval_s
        self.user_agent = user_agent(contact)
        self._hosts: dict[str, _Host] = {}
        self._hosts_lock = threading.Lock()
        self._client = httpx2.Client(
            transport=transport,
            headers={"user-agent": self.user_agent, "accept": "text/html,application/json;q=0.9"},
            timeout=TIMEOUT,
            follow_redirects=False,
            trust_env=False,  # no proxy or certificate settings from the environment
        )

    def close(self) -> None:
        self._client.close()

    def fetch(
        self,
        url: str,
        context: SourceContext,
        *,
        site: str,
        kind: SourceKind = "page",
        check_robots: bool = True,
    ) -> Page:
        """GET one URL on `site` (a domain whose subdomains count too)."""
        problem = egress_problem(url, self.resolver)
        if problem is None and not on_site(url, site):
            problem = f"{url} is outside {site}"
        if problem is not None:
            self._record(context, kind, url, "refused", detail=problem)
            raise FetchRefused("egress", problem)
        target, retried_429, redirects = url, False, 0
        while True:
            decision = None
            if check_robots:
                if not self._robots(target, context).allowed(_path(target)):
                    detail = "robots.txt disallows this path"
                    self._record(
                        context, kind, target, "refused", robots="disallowed", detail=detail
                    )
                    raise FetchRefused("robots", f"robots.txt disallows {target}")
                decision = "allowed"
            started, clock = utc_now(), self.clock()

            # This attempt's row, with its target, robots decision and timing bound now.
            record = partial(
                self._record, context, kind, target, robots=decision, started=started, clock=clock
            )

            try:
                response, body = self._send(target)
            except (httpx2.HTTPError, OSError) as error:
                detail = f"{type(error).__name__}: {error}"
                record("failed", detail=detail)
                raise FetchFailed(detail) from None
            status, size = response.status_code, len(body)
            if status == 429 and not retried_429:
                wait = _retry_after(response)
                record(
                    "failed", detail=f"HTTP 429; waiting {wait:g} s once", http=status, size=size
                )
                retried_429 = True
                self.sleep(wait)
                continue
            if 300 <= status < 400 and "location" in response.headers:
                location = urljoin(target, response.headers["location"])
                record("succeeded", detail=f"redirect to {location}", http=status, size=size)
                redirects += 1
                problem = egress_problem(location, self.resolver)
                if redirects > MAX_REDIRECTS:
                    problem = f"more than {MAX_REDIRECTS} redirects"
                elif problem is None and not on_site(location, site):
                    problem = f"redirect leaves {site}: {location}"
                if problem is not None:
                    self._record(context, kind, location, "refused", detail=problem)
                    raise FetchRefused("redirect", problem)
                target = location
                continue
            content_type = response.headers.get("content-type", "")
            failure = None
            if size > MAX_BYTES:
                failure = f"response over {MAX_BYTES} bytes"
            elif not 200 <= status < 300:
                failure = f"HTTP {status}" + (" (not retried)" if status in (401, 403) else "")
            elif not content_type.lower().startswith(TEXT_TYPES):
                failure = f"content type {content_type or '(none)'} is not text"
            if failure is not None:
                record("failed", detail=failure, http=status, size=size)
                raise FetchFailed(failure)
            digest = hashlib.sha256(body).hexdigest()
            kept = record("succeeded", detail="ok", http=status, size=size, digest=digest)
            return Page(url, target, status, content_type, body, kept.call_id, kept.span_id)

    def _send(self, url: str) -> tuple[httpx2.Response, bytes]:
        host = self._host(url)
        with host.lock:
            wait = host.next_at - self.clock()
            if wait > 0:
                self.sleep(wait)
            try:
                with self._client.stream("GET", url) as response:
                    body = read_capped(response.iter_bytes())  # decoded, so the cap holds
            finally:
                self._client.cookies.clear()  # never send back what a site set
                crawl_delay = host.rules.crawl_delay if host.rules else None
                host.next_at = self.clock() + max(self.min_interval_s, crawl_delay or 0.0)
        return response, body

    def _host(self, url: str) -> _Host:
        key = urlsplit(url).netloc.lower()
        with self._hosts_lock:
            return self._hosts.setdefault(key, _Host())

    def _robots(self, url: str, context: SourceContext) -> RobotsRules:
        host = self._host(url)
        if host.rules is not None:
            return host.rules
        parts = urlsplit(url)
        robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        started, clock = utc_now(), self.clock()
        try:
            response, body = self._send(robots_url)
            status = response.status_code
            if 300 <= status < 400:
                # RFC 9309 allows following robots redirects; one hop on the same host is
                # all a company site needs, and anything else reads as unreachable.
                location = urljoin(robots_url, response.headers.get("location", ""))
                if urlsplit(location).netloc.lower() != parts.netloc.lower():
                    raise httpx2.ConnectError(f"robots.txt redirects off the host: {location}")
                response, body = self._send(location)
                status = response.status_code
            rules = robots.rules_for_status(status, body.decode("utf-8", errors="replace"))
            self._record(
                context,
                "robots",
                robots_url,
                "succeeded" if status < 500 else "failed",
                http=status,
                size=len(body),
                detail=rules.note or "parsed",
                started=started,
                clock=clock,
            )
        except (httpx2.HTTPError, OSError) as error:
            rules = robots.DISALLOW_ALL
            detail = f"unreachable, so all disallowed: {type(error).__name__}: {error}"
            self._record(
                context, "robots", robots_url, "failed", detail=detail, started=started, clock=clock
            )
        host.rules = rules
        return rules

    def _record(
        self,
        context: SourceContext,
        kind: SourceKind,
        target: str,
        status: SourceStatus,
        *,
        detail: str,
        robots: str | None = None,
        http: int | None = None,
        size: int | None = None,
        digest: str | None = None,
        started: str | None = None,
        clock: float | None = None,
    ) -> SourceCallRecord:
        record = SourceCallRecord(
            call_id=str(uuid7()),
            run_id=context.run_id,
            step=context.step,
            lead_id=context.lead_id,
            kind=kind,
            target=target,
            mode=self.mode,
            status=status,
            robots_decision=robots,
            http_status=http,
            bytes=size,
            content_sha256=digest,
            results_json="[]",
            model_call_id=None,
            detail=detail,
            latency_ms=round((self.clock() - clock) * 1000) if clock is not None else None,
            trace_id=trace_id_for(context.lead_id),
            span_id=new_span_id(),
            parent_span_id=context.parent_span_id,
            started_at=started or utc_now(),
            ended_at=utc_now(),
        )
        self.sink.add(record)
        return record


def _path(url: str) -> str:
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def _retry_after(response: httpx2.Response) -> float:
    try:
        seconds = float(response.headers.get("retry-after", "1"))
    except ValueError:
        seconds = 1.0
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_S)
