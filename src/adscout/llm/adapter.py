"""The one model adapter: every model call goes through `ModelAdapter.call`.

Three modes (Phase 2 design, decision 13): `fake` answers from a scripted responder (tests
and the offline demo), `replay` from the record-and-replay cache, `live` from the Anthropic
API. Before a call is sent the adapter checks the agent's tool allowlist and the price table
and reserves the call's worst case against the run's cap; after it, it settles the cost and
records one `model_calls` row. Rows go to a `CallSink`, which the run writes in its own short
transaction, so a worker never writes the database (decision 37).

Only `LiveTransport` holds the API key. It turns the SDK's own retries off: the spend-cap and
spend-limit errors must never be retried (decision 17), so transient errors are retried here.
"""

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol

import anthropic
import httpx2
from anthropic.types import Message, MessageParam, TextBlockParam, ToolUnionParam

from adscout.db.connection import utc_now
from adscout.env import ENV_FILE, env_value
from adscout.ids import uuid7
from adscout.llm.budget import (
    BudgetExhausted,
    SpendLedger,
    estimate_prompt_tokens,
    worst_case_cost,
)
from adscout.llm.prices import MissingPrice, PriceTable, Usage, cost
from adscout.pipeline.contracts import Step

Mode = Literal["fake", "replay", "live"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]
CallRole = Literal["primary", "retry", "fallback", "escalation"]
CallStatus = Literal["succeeded", "failed", "refused"]

API_BASE_URL = "https://api.anthropic.com"
API_KEY_NAME = "ANTHROPIC_API_KEY"
NO_RESPONSE = "no response: the call was {status} ({category})"
NO_CHARGE = (Decimal(0), Decimal(0))  # a replay costs nothing; tokens and search fees


class ModelCallFailed(RuntimeError):
    """A call that produced no usable response; `category` names why."""

    def __init__(self, category: str, detail: str, *, fallback_allowed: bool) -> None:
        super().__init__(f"{category}: {detail}")
        self.category = category
        self.detail = detail
        self.fallback_allowed = fallback_allowed


class TransientError(ModelCallFailed):
    """Worth retrying the same request: overload, a server error, a rate limit, the network."""

    def __init__(self, category: str, detail: str, retry_after: float | None) -> None:
        super().__init__(category, detail, fallback_allowed=category != "rate_limited")
        self.retry_after = retry_after


class LiveModeRefused(RuntimeError):
    """Live mode needs `--live`, a spend cap and an API key; one is missing."""


@dataclass(frozen=True)
class ModelRequest:
    """One Messages API request. Prompt builders set its cache breakpoints."""

    model: str
    max_tokens: int
    system: list[TextBlockParam]
    messages: list[MessageParam]
    tools: list[ToolUnionParam] = field(default_factory=list)
    output_schema: dict[str, Any] | None = None
    effort: Effort | None = None

    def params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": self.system,
            "messages": self.messages,
        }
        if self.tools:
            params["tools"] = self.tools
        output_config: dict[str, Any] = {}
        if self.effort:
            output_config["effort"] = self.effort
        if self.output_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": self.output_schema}
        if output_config:
            params["output_config"] = output_config
        return params

    def canonical_bytes(self) -> bytes:
        text = json.dumps(self.params(), sort_keys=True, separators=(",", ":"), default=str)
        return text.encode("utf-8")

    def tool_specs(self) -> list[dict[str, Any]]:
        return [dict(tool) for tool in self.tools]

    @property
    def tool_names(self) -> set[str]:
        return {str(tool.get("name", tool.get("type"))) for tool in self.tool_specs()}

    @property
    def max_searches(self) -> int:
        """The searches this request may make: the web search tool's `max_uses`."""
        return sum(
            int(tool.get("max_uses") or 0)
            for tool in self.tool_specs()
            if str(tool.get("type", "")).startswith("web_search")
        )


def request_hash(request: ModelRequest, prompt_version: str) -> str:
    """The replay-cache key: SHA-256 over the prompt version and the canonical request."""
    digest = hashlib.sha256(prompt_version.encode("utf-8") + b"\n")
    digest.update(request.canonical_bytes())
    return digest.hexdigest()


def new_span_id() -> str:
    return os.urandom(8).hex()


def trace_id_for(lead_id: str) -> str:
    """A lead's trace ID: its UUIDv7 as 32 hex digits."""
    return lead_id.replace("-", "")


@dataclass(frozen=True)
class CallContext:
    """Who is calling, for which lead, and where the call sits in the lead's trace."""

    run_id: str
    step: Step
    lead_id: str
    role: str
    agent_name: str
    prompt_version: str
    parent_span_id: str
    allowed_tools: frozenset[str] = frozenset()

    @property
    def trace_id(self) -> str:
        return trace_id_for(self.lead_id)


class Recordable(Protocol):
    """A row a run writes for a call or span; `write_order` puts parents before children."""

    write_order: ClassVar[int]

    def insert(self, connection: sqlite3.Connection) -> None: ...


@dataclass(frozen=True)
class CallRecord:
    """One `model_calls` row."""

    write_order: ClassVar[int] = 1

    call_id: str
    run_id: str
    step: str
    lead_id: str
    role: str
    agent_name: str
    model: str
    effort: str | None
    prompt_version: str
    call_role: str
    mode: str
    status: CallStatus
    error_category: str | None
    error_detail: str | None
    request_sha256: str
    input_tokens: int | None
    cache_write_tokens: int | None
    cache_read_tokens: int | None
    output_tokens: int | None
    web_search_requests: int
    search_fee_usd: float
    cost_usd: float
    original_cost_usd: float | None
    reserved_usd: float
    price_date: str | None
    latency_ms: int | None
    stop_reason: str | None
    trace_id: str
    span_id: str
    parent_span_id: str
    null_reasons: dict[str, str]
    started_at: str
    ended_at: str

    def insert(self, connection: sqlite3.Connection) -> None:
        columns = [item.name for item in fields(self) if item.name != "null_reasons"]
        values = [getattr(self, name) for name in columns]
        connection.execute(
            f"INSERT INTO model_calls ({', '.join(columns)}, null_reasons_json) "  # noqa: S608
            f"VALUES ({', '.join('?' * (len(columns) + 1))})",
            (*values, json.dumps(self.null_reasons, sort_keys=True)),
        )


class CallSink:
    """Model call, source call and span records from any thread, until the run writes them."""

    def __init__(self) -> None:
        self._records: list[Recordable] = []
        self._lock = threading.Lock()

    def add(self, record: Recordable) -> None:
        with self._lock:
            self._records.append(record)

    def drain(self) -> list[Recordable]:
        with self._lock:
            records, self._records = self._records, []
        return records

    def model_calls(self) -> list["CallRecord"]:
        """The model call records, drained; any other records stay."""
        with self._lock:
            calls = [record for record in self._records if isinstance(record, CallRecord)]
            self._records = [r for r in self._records if not isinstance(r, CallRecord)]
        return calls


@dataclass(frozen=True)
class Sent:
    """A transport's answer; a replay carries the cost the original call had."""

    message: Message
    original_cost_usd: Decimal | None = None


class Transport(Protocol):
    mode: Mode

    def send(self, request: ModelRequest, key: str) -> Sent: ...


class ResponseRecorder(Protocol):
    """Keeps what a live call returned, an error included, so a replay can reproduce it."""

    def response(self, key: str, message: Message, cost_usd: Decimal) -> None: ...

    def failure(self, key: str, failure: Exception) -> None: ...


@dataclass(frozen=True)
class ModelResult:
    message: Message
    usage: Usage
    cost_usd: Decimal
    call_id: str
    span_id: str

    @property
    def text(self) -> str:
        return "".join(block.text for block in self.message.content if block.type == "text")

    def json(self) -> Any:
        """The structured output: the text of a response constrained to a JSON schema."""
        return json.loads(self.text)


def usage_of(message: Message) -> Usage:
    usage = message.usage
    created = usage.cache_creation
    write_1h = created.ephemeral_1h_input_tokens if created else 0
    write_total = usage.cache_creation_input_tokens or 0
    searches = usage.server_tool_use.web_search_requests if usage.server_tool_use else 0
    return Usage(
        input_tokens=usage.input_tokens,
        cache_write_5m_tokens=write_total - write_1h,
        cache_write_1h_tokens=write_1h,
        cache_read_tokens=usage.cache_read_input_tokens or 0,
        output_tokens=usage.output_tokens,
        web_search_requests=searches,
    )


def error_body(error: anthropic.APIStatusError) -> dict[str, Any]:
    body = error.body
    if isinstance(body, dict):
        inner = body.get("error", body)
        if isinstance(inner, dict):
            return inner
    return {}


def classify(error: Exception) -> Exception:
    """Map an SDK error to BudgetExhausted, a TransientError or a ModelCallFailed."""
    if isinstance(error, (BudgetExhausted, ModelCallFailed)):
        return error
    if isinstance(error, anthropic.APIStatusError):
        body = error_body(error)
        message = str(body.get("message") or error.message)
        details = body.get("details")
        code = details.get("error_code") if isinstance(details, dict) else None
        status = error.status_code
        if (
            status == 402
            or error.type == "billing_error"
            or (status == 400 and message.startswith("You have reached your specified"))
            or "credit balance is too low" in message
            or (status == 429 and code == "enforced_spend_limit_reached")
        ):
            return BudgetExhausted(f"the provider refused on spend: HTTP {status}: {message}")
        if status == 429:
            retry_after = error.response.headers.get("retry-after")
            return TransientError(
                "rate_limited", message, float(retry_after) if retry_after else None
            )
        if status >= 500:
            category = "overloaded" if status == 529 else "server_error"
            return TransientError(category, f"HTTP {status}: {message}", None)
        category = {401: "authentication", 403: "permission"}.get(status, "invalid_request")
        return ModelCallFailed(category, f"HTTP {status}: {message}", fallback_allowed=False)
    if isinstance(error, anthropic.APIConnectionError):
        return TransientError("connection", type(error).__name__, None)
    return error


def redact(text: str, secret: str | None) -> str:
    return text.replace(secret, "[redacted]") if secret else text


class FakeTransport:
    """Scripted responses for tests and the offline demo; nothing leaves the process."""

    mode: Mode = "fake"

    def __init__(self, responder: Callable[[ModelRequest], Message]) -> None:
        self.responder = responder
        self.requests: list[ModelRequest] = []
        self._lock = threading.Lock()

    def send(self, request: ModelRequest, key: str) -> Sent:
        with self._lock:
            self.requests.append(request)
        return Sent(self.responder(request))


class LiveTransport:
    """The Anthropic API. The only holder of the API key."""

    mode: Mode = "live"

    def __init__(
        self,
        api_key: str,
        *,
        attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        http_client: httpx2.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self.attempts = attempts
        self.sleep = sleep
        # Explicit key and base URL: no saved profile or ANTHROPIC_BASE_URL can redirect it.
        self._client = anthropic.Anthropic(
            api_key=api_key,
            base_url=API_BASE_URL,
            max_retries=0,
            timeout=anthropic.Timeout(120.0, connect=10.0),
            http_client=http_client,
        )

    def send(self, request: ModelRequest, key: str) -> Sent:
        for attempt in range(1, self.attempts + 1):
            try:
                return Sent(self._client.messages.create(**request.params()))
            except Exception as error:  # never re-raised raw: it could carry the key
                failure = self.redacted(error)
                if isinstance(failure, TransientError) and attempt < self.attempts:
                    self.sleep(failure.retry_after or min(2.0**attempt, 30.0))
                    continue
                if isinstance(failure, TransientError):
                    failure = ModelCallFailed(
                        failure.category,
                        f"{failure.detail} (after {attempt} attempts)",
                        fallback_allowed=failure.fallback_allowed,
                    )
                raise failure from None
        raise AssertionError("unreachable")  # pragma: no cover

    def redacted(self, error: Exception) -> Exception:
        """The classified error, rebuilt with the key removed from its text."""
        failure = classify(error)
        if isinstance(failure, TransientError):
            return TransientError(
                failure.category, redact(failure.detail, self._api_key), failure.retry_after
            )
        if isinstance(failure, ModelCallFailed):
            return ModelCallFailed(
                failure.category,
                redact(failure.detail, self._api_key),
                fallback_allowed=failure.fallback_allowed,
            )
        if isinstance(failure, BudgetExhausted):
            return BudgetExhausted(redact(str(failure), self._api_key))
        detail = redact(f"{type(error).__name__}: {error}", self._api_key)
        return ModelCallFailed("client_error", detail, fallback_allowed=False)


class ModelAdapter:
    """Checks, reserves, sends, costs and records every model call of one run."""

    def __init__(
        self,
        transport: Transport,
        prices: PriceTable,
        ledger: SpendLedger,
        sink: CallSink,
        *,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
        recorder: ResponseRecorder | None = None,
    ) -> None:
        self.transport = transport
        self.prices = prices
        self.ledger = ledger
        self.sink = sink
        self.today = today
        self.recorder = recorder

    @property
    def mode(self) -> Mode:
        return self.transport.mode

    def call(
        self, request: ModelRequest, context: CallContext, call_role: CallRole = "primary"
    ) -> ModelResult:
        call_id, span_id = str(uuid7()), new_span_id()
        started_at, clock = utc_now(), time.perf_counter()
        key = request_hash(request, context.prompt_version)
        on = self.today()

        def write(
            status: CallStatus,
            *,
            reserved: Decimal = Decimal(0),
            message: Message | None = None,
            usage: Usage | None = None,
            paid: tuple[Decimal, Decimal] = (Decimal(0), Decimal(0)),
            original: Decimal | None = None,
            price_date: date | None = None,
            category: str | None = None,
            detail: str | None = None,
        ) -> None:
            if self.mode == "replay" and original is None:
                original = Decimal(0)  # a failed or refused call cost nothing the first time
            reasons = {}
            if usage is None:
                reason = NO_RESPONSE.format(status=status, category=category)
                reasons = dict.fromkeys(
                    ("input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens"),
                    reason,
                )
            self.sink.add(
                CallRecord(
                    call_id=call_id,
                    run_id=context.run_id,
                    step=context.step,
                    lead_id=context.lead_id,
                    role=context.role,
                    agent_name=context.agent_name,
                    model=request.model,
                    effort=request.effort,
                    prompt_version=context.prompt_version,
                    call_role=call_role,
                    mode=self.mode,
                    status=status,
                    error_category=category,
                    error_detail=detail,
                    request_sha256=key,
                    input_tokens=usage.input_tokens if usage else None,
                    cache_write_tokens=usage.cache_write_tokens if usage else None,
                    cache_read_tokens=usage.cache_read_tokens if usage else None,
                    output_tokens=usage.output_tokens if usage else None,
                    web_search_requests=usage.web_search_requests if usage else 0,
                    search_fee_usd=float(paid[1]),
                    cost_usd=float(paid[0] + paid[1]),
                    original_cost_usd=float(original) if original is not None else None,
                    reserved_usd=float(reserved),
                    price_date=price_date.isoformat() if price_date else None,
                    latency_ms=round((time.perf_counter() - clock) * 1000),
                    stop_reason=message.stop_reason if message else None,
                    trace_id=context.trace_id,
                    span_id=span_id,
                    parent_span_id=context.parent_span_id,
                    null_reasons=reasons,
                    started_at=started_at,
                    ended_at=utc_now(),
                )
            )

        disallowed = sorted(request.tool_names - context.allowed_tools)
        if disallowed:
            detail = f"{context.agent_name} may not use {disallowed}"
            write("refused", category="tool_not_allowed", detail=detail)
            raise ModelCallFailed("tool_not_allowed", detail, fallback_allowed=False)
        try:
            prompt_tokens = estimate_prompt_tokens(
                len(request.canonical_bytes()), bool(request.tools), request.max_searches
            )
            worst = worst_case_cost(
                self.prices,
                request.model,
                prompt_tokens=prompt_tokens,
                max_tokens=request.max_tokens,
                max_searches=request.max_searches,
                on=on,
            )
            limit = self.prices.base_tier_limit(request.model, on)
        except MissingPrice as error:
            write("refused", category="missing_price", detail=str(error))
            raise ModelCallFailed("missing_price", str(error), fallback_allowed=False) from None
        if limit is not None and prompt_tokens > limit:
            # Haiku prompts stay under 100K tokens (decision 18): past that every token
            # costs five times as much. An oversized prompt is a construction bug.
            detail = f"about {prompt_tokens} prompt tokens, over the {limit}-token price tier"
            write("refused", category="prompt_too_long", detail=detail)
            raise ModelCallFailed("prompt_too_long", detail, fallback_allowed=False)
        try:
            reservation = self.ledger.reserve(Decimal(0) if self.mode == "replay" else worst)
        except BudgetExhausted as error:
            write("refused", reserved=worst, category="budget_exhausted", detail=str(error))
            raise
        try:
            sent = self.transport.send(request, key)
        except Exception as error:
            self.ledger.settle(reservation, Decimal(0))
            failure = classify(error)
            category = getattr(failure, "category", "client_error")
            write("failed", reserved=worst, category=category, detail=str(failure))
            if self.mode == "live" and self.recorder is not None:
                self.recorder.failure(key, failure)
            if failure is error:
                raise
            raise failure from None
        usage = usage_of(sent.message)
        if sent.original_cost_usd is not None:
            charged, original = NO_CHARGE, sent.original_cost_usd
            price_date = None
        else:
            priced = cost(self.prices, request.model, usage, on)
            charged, original = (priced.tokens_usd, priced.search_fee_usd), None
            price_date = priced.price_date
        self.ledger.settle(reservation, charged[0] + charged[1])
        if self.mode == "live" and self.recorder is not None:
            self.recorder.response(key, sent.message, charged[0] + charged[1])
        write(
            "succeeded",
            reserved=worst,
            message=sent.message,
            usage=usage,
            paid=charged,
            original=original,
            price_date=price_date,
        )
        result = ModelResult(
            message=sent.message,
            usage=usage,
            cost_usd=charged[0] + charged[1],
            call_id=call_id,
            span_id=span_id,
        )
        if sent.message.stop_reason == "refusal":
            raise ModelCallFailed(
                "refusal", f"{request.model} declined the request", fallback_allowed=True
            )
        return result


def write_calls(connection: sqlite3.Connection, records: Sequence[Recordable]) -> None:
    """Insert records, model calls before the source calls that name them."""
    for record in sorted(records, key=lambda item: item.write_order):
        record.insert(connection)


def live_transport(env_file: Path = ENV_FILE) -> LiveTransport:
    """The live transport, with the key from the environment or `.env`."""
    api_key = env_value(API_KEY_NAME, env_file)
    if not api_key:
        raise LiveModeRefused(f"{API_KEY_NAME} is not set in the environment or {env_file.name}")
    return LiveTransport(api_key)


def require_live_settings(*, live_flag: bool, cap_usd: Decimal | None) -> None:
    """Live mode refuses to start without `--live` and a per-run spend cap."""
    if not live_flag:
        raise LiveModeRefused("live model calls need the --live flag")
    if cap_usd is None:
        raise LiveModeRefused("live model calls need a spend cap: --max-spend-usd")
