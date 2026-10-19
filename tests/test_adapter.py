"""The model adapter: modes, costing, call records, budget errors and key handling.

Live-mode tests drive the real SDK client over an in-process HTTP transport; nothing leaves
the process (pytest-socket blocks the network).
"""

import json
import sqlite3
from collections.abc import Callable, Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx2
import pytest

from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.env import env_value
from adscout.ids import ROOT, uuid7
from adscout.llm.adapter import (
    CallContext,
    CallSink,
    FakeTransport,
    LiveModeRefused,
    LiveTransport,
    ModelAdapter,
    ModelCallFailed,
    ModelRequest,
    live_transport,
    request_hash,
    require_live_settings,
    write_calls,
)
from adscout.llm.budget import BudgetExhausted, SpendLedger
from adscout.llm.fakes import fake_message, scripted
from adscout.llm.prices import load_price_table
from adscout.pipeline.recorder import Run

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
DAY = date(2026, 10, 19)
KEY = "sk-ant-api03-" + "x" * 40  # a made-up key; never a real one
PROMPT = "p-0123456789ab"
PARENT = "0123456789abcdef"
FETCH_TOOL: Any = {
    "name": "fetch_page",
    "description": "Fetch a page.",
    "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}},
}


def request(model: str = HAIKU, **changes: Any) -> ModelRequest:
    values: dict[str, Any] = {
        "model": model,
        "max_tokens": 500,
        "system": [{"type": "text", "text": "Rate the lead."}],
        "messages": [{"role": "user", "content": "example.test"}],
    } | changes
    return ModelRequest(**values)


def context(run_id: str, lead_id: str, **changes: Any) -> CallContext:
    values: dict[str, Any] = {
        "run_id": run_id,
        "step": "score",
        "lead_id": lead_id,
        "role": "scorer",
        "agent_name": "scorer",
        "prompt_version": PROMPT,
        "parent_span_id": PARENT,
    } | changes
    return CallContext(**values)


def adapter(
    transport: Any, cap: Decimal | None = None, sink: CallSink | None = None
) -> ModelAdapter:
    return ModelAdapter(
        transport, load_price_table(), SpendLedger(cap), sink or CallSink(), today=lambda: DAY
    )


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


@pytest.fixture
def run(db: sqlite3.Connection) -> Iterator[Run]:
    """A started run with one lead, whose rows the call records can reference."""
    started = Run(db, "pipeline", "test-segment", "fixture", {}, {})
    started.start()
    now = utc_now()
    db.execute(
        "INSERT INTO companies (company_id, domain, name, created_run_id, created_at) "
        "VALUES (1, 'example.test', 'Example', ?, ?)",
        (started.run_id, now),
    )
    db.execute(
        "INSERT INTO leads VALUES (?, 'test-segment', 1, 'test', 'none', 'v', ?, ?)",
        (str(uuid7()), started.run_id, now),
    )
    yield started


def lead_of(db: sqlite3.Connection) -> str:
    return str(db.execute("SELECT lead_id FROM leads").fetchone()[0])


def mock_live(
    handler: Callable[[httpx2.Request], httpx2.Response], **options: Any
) -> LiveTransport:
    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return LiveTransport(KEY, http_client=client, sleep=lambda seconds: None, **options)


def error_response(status: int, error_type: str, message: str, **extra: Any) -> httpx2.Response:
    error: dict[str, Any] = {"type": error_type, "message": message} | extra
    return httpx2.Response(status, json={"type": "error", "error": error})


def test_fake_call_is_costed_from_the_price_table_and_recorded(
    db: sqlite3.Connection, run: Run
) -> None:
    lead_id = lead_of(db)
    reply = fake_message(
        HAIKU,
        data={"rating": 4},
        input_tokens=2000,
        cache_read_tokens=1000,
        output_tokens=500,
        web_search_requests=1,
    )
    sink = CallSink()
    result = adapter(FakeTransport(scripted([reply])), sink=sink).call(
        request(), context(run.run_id, lead_id)
    )

    assert result.json() == {"rating": 4}
    assert result.cost_usd == Decimal("0.01046")
    [record] = sink.drain()
    assert (record.mode, record.status, record.call_role) == ("fake", "succeeded", "primary")
    assert record.cost_usd == pytest.approx(0.01046) and record.search_fee_usd == 0.01
    assert record.price_date == "2026-10-18" and record.reserved_usd > 0
    assert record.trace_id == lead_id.replace("-", "") and record.parent_span_id == PARENT
    assert len(record.span_id) == 16 and record.span_id == result.span_id
    assert record.request_sha256 == request_hash(request(), PROMPT)
    with db:
        db.execute(
            "INSERT INTO step_runs (run_id, step, seq, implementation, implementation_version, "
            "status, started_at, null_reasons_json) VALUES (?, 'score', 1, 'real', '1', "
            "'running', ?, '{}')",
            (run.run_id, utc_now()),
        )
        write_calls(db, [record])
    row = db.execute("SELECT * FROM model_calls").fetchone()
    assert (row["input_tokens"], row["cache_read_tokens"], row["output_tokens"]) == (
        2000,
        1000,
        500,
    )
    assert row["web_search_requests"] == 1 and row["stop_reason"] == "end_turn"


def test_tool_outside_the_allowlist_is_refused_before_sending() -> None:
    transport = FakeTransport(scripted([]))
    sink = CallSink()
    with pytest.raises(ModelCallFailed, match="tool_not_allowed") as caught:
        adapter(transport, sink=sink).call(
            request(tools=[FETCH_TOOL]), context("r", str(uuid7()), agent_name="scorer")
        )
    assert not caught.value.fallback_allowed
    assert transport.requests == []
    [record] = sink.drain()
    assert (record.status, record.error_category) == ("refused", "tool_not_allowed")
    assert record.input_tokens is None and "refused" in record.null_reasons["input_tokens"]


def test_allowlisted_tool_is_sent() -> None:
    transport = FakeTransport(scripted([fake_message(HAIKU, text="ok")]))
    allowed = context("r", str(uuid7()), allowed_tools=frozenset({"fetch_page"}))
    adapter(transport).call(request(tools=[FETCH_TOOL]), allowed)
    assert len(transport.requests) == 1


def test_model_without_a_price_is_refused_before_sending() -> None:
    transport = FakeTransport(scripted([]))
    sink = CallSink()
    with pytest.raises(ModelCallFailed, match="missing_price"):
        adapter(transport, sink=sink).call(request("claude-opus-5-5"), context("r", "l" * 36))
    assert transport.requests == []
    assert sink.drain()[0].error_category == "missing_price"


SPEND_LIMIT = (
    "You have reached your specified workspace API usage limits. Access resumes on 2026-11-01."
)
SPEND_CAP = (
    "You have reached your API usage limits: your organization has crossed its monthly "
    "API usage threshold."
)


@pytest.mark.parametrize(
    "response",
    [
        error_response(400, "invalid_request_error", SPEND_LIMIT),
        error_response(
            429,
            "rate_limit_error",
            SPEND_CAP,
            details={"error_code": "enforced_spend_limit_reached"},
        ),
        error_response(
            400,
            "invalid_request_error",
            "Your credit balance is too low to access the Anthropic API.",
        ),
        error_response(402, "billing_error", "Payment required."),
    ],
    ids=["workspace-limit", "spend-cap", "credit-balance", "billing"],
)
def test_budget_errors_stop_the_call_without_a_retry(response: httpx2.Response) -> None:
    sent: list[httpx2.Request] = []

    def handler(outgoing: httpx2.Request) -> httpx2.Response:
        sent.append(outgoing)
        return response

    sink = CallSink()
    with pytest.raises(BudgetExhausted, match="refused on spend"):
        adapter(mock_live(handler), cap=Decimal(1), sink=sink).call(
            request(), context("r", str(uuid7()))
        )
    assert len(sent) == 1
    [record] = sink.drain()
    assert (record.status, record.error_category, record.cost_usd) == (
        "failed",
        "budget_exhausted",
        0.0,
    )


def test_overload_is_retried_then_fails_with_a_fallback_allowed() -> None:
    sent: list[httpx2.Request] = []

    def handler(outgoing: httpx2.Request) -> httpx2.Response:
        sent.append(outgoing)
        return error_response(529, "overloaded_error", "Overloaded")

    with pytest.raises(ModelCallFailed, match=r"overloaded.*after 3 attempts") as caught:
        adapter(mock_live(handler), cap=Decimal(1)).call(request(), context("r", str(uuid7())))
    assert len(sent) == 3 and caught.value.fallback_allowed


def test_rate_limit_waits_for_retry_after_then_succeeds() -> None:
    waits: list[float] = []
    replies = [
        error_response(
            429,
            "rate_limit_error",
            "Too many requests",
        ),
        httpx2.Response(200, json=fake_message(HAIKU, text="ok").to_dict()),
    ]
    replies[0].headers["retry-after"] = "2"

    def handler(outgoing: httpx2.Request) -> httpx2.Response:
        assert outgoing.headers["x-api-key"] == KEY
        assert outgoing.url.host == "api.anthropic.com"
        return replies.pop(0)

    transport = mock_live(handler)
    transport.sleep = waits.append
    result = adapter(transport, cap=Decimal(1)).call(request(), context("r", str(uuid7())))
    assert result.text == "ok" and waits == [2.0]


def test_authentication_error_never_shows_the_key() -> None:
    def handler(outgoing: httpx2.Request) -> httpx2.Response:
        return error_response(401, "authentication_error", f"invalid x-api-key {KEY}")

    sink = CallSink()
    with pytest.raises(ModelCallFailed, match="authentication") as caught:
        adapter(mock_live(handler), cap=Decimal(1), sink=sink).call(
            request(), context("r", str(uuid7()))
        )
    [record] = sink.drain()
    for text in (str(caught.value), caught.value.detail, record.error_detail or ""):
        assert KEY not in text and "[redacted]" in text
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_environment_base_url_cannot_redirect_live_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://elsewhere.example")
    hosts: list[str] = []

    def handler(outgoing: httpx2.Request) -> httpx2.Response:
        hosts.append(outgoing.url.host)
        return httpx2.Response(200, json=fake_message(HAIKU, text="ok").to_dict())

    adapter(mock_live(handler), cap=Decimal(1)).call(request(), context("r", str(uuid7())))
    assert hosts == ["api.anthropic.com"]


def test_refusal_is_recorded_as_billed_and_raised_for_a_fallback() -> None:
    sink = CallSink()
    reply = fake_message(SONNET, text="", stop_reason="refusal", output_tokens=5)
    with pytest.raises(ModelCallFailed, match="refusal") as caught:
        adapter(FakeTransport(scripted([reply])), sink=sink).call(
            request(SONNET), context("r", str(uuid7()))
        )
    assert caught.value.fallback_allowed
    [record] = sink.drain()
    assert (record.status, record.stop_reason) == ("succeeded", "refusal")
    assert record.cost_usd > 0


def test_live_mode_needs_the_flag_a_cap_and_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(LiveModeRefused, match="--live"):
        require_live_settings(live_flag=False, cap_usd=Decimal(1))
    with pytest.raises(LiveModeRefused, match="--max-spend-usd"):
        require_live_settings(live_flag=True, cap_usd=None)
    require_live_settings(live_flag=True, cap_usd=Decimal("2.50"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    with pytest.raises(LiveModeRefused, match="ANTHROPIC_API_KEY is not set"):
        live_transport(env_file)
    env_file.write_text(f'export ANTHROPIC_API_KEY="{KEY}"\n', encoding="utf-8")
    assert isinstance(live_transport(env_file), LiveTransport)


def test_env_value_reads_the_environment_before_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nOTHER=1\nADSCOUT_CONTACT='bot@example.test'\nEMPTY=\n", encoding="utf-8"
    )
    monkeypatch.delenv("ADSCOUT_CONTACT", raising=False)
    assert env_value("ADSCOUT_CONTACT", env_file) == "bot@example.test"
    assert env_value("EMPTY", env_file) is None
    assert env_value("MISSING", env_file) is None
    assert env_value("MISSING", tmp_path / "absent.env") is None
    monkeypatch.setenv("ADSCOUT_CONTACT", "env@example.test")
    assert env_value("ADSCOUT_CONTACT", env_file) == "env@example.test"


def test_only_the_adapter_reads_the_api_key() -> None:
    readers = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src").rglob("*.py")
        if "ANTHROPIC_API_KEY" in path.read_text(encoding="utf-8")
    )
    assert readers == ["src/adscout/llm/adapter.py"]


def test_step_totals_are_the_sums_of_its_calls(db: sqlite3.Connection, run: Run) -> None:
    lead_id = lead_of(db)
    replies = [
        fake_message(HAIKU, text="a", input_tokens=1000, cache_read_tokens=500, output_tokens=50),
        fake_message(SONNET, text="b", input_tokens=2000, cache_write_tokens=300, output_tokens=70),
    ]
    model = adapter(FakeTransport(scripted(replies)), sink=run.calls)
    with run.step("score", "real", 1):
        model.call(request(), context(run.run_id, lead_id))
        model.call(request(SONNET), context(run.run_id, lead_id))
    step = db.execute("SELECT * FROM step_runs WHERE step = 'score'").fetchone()
    calls = db.execute(
        "SELECT sum(cost_usd), sum(output_tokens) FROM model_calls WHERE step = 'score'"
    ).fetchone()
    assert step["model"] == f"{HAIKU},{SONNET}"
    assert step["input_tokens"] == 1000 + 500 + 2000 + 300
    assert step["output_tokens"] == calls[1] == 120
    assert step["cost_usd"] == pytest.approx(calls[0])
    assert json.loads(step["null_reasons_json"]) == {}


def test_failed_step_keeps_the_calls_it_paid_for(db: sqlite3.Connection, run: Run) -> None:
    lead_id = lead_of(db)
    model = adapter(FakeTransport(scripted([fake_message(HAIKU, text="a")])), sink=run.calls)
    with pytest.raises(RuntimeError, match="later failure"), run.step("score", "real", 1):
        model.call(request(), context(run.run_id, lead_id))
        raise RuntimeError("later failure")
    assert db.execute("SELECT status FROM step_runs").fetchone()[0] == "failed"
    assert db.execute("SELECT count(*) FROM model_calls").fetchone()[0] == 1
