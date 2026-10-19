"""Per-run spend caps: worst-case reservations under a lock (Phase 2 design, decision 16)."""

import sqlite3
import threading
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from anthropic.types import Message

from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.ids import uuid7
from adscout.llm.adapter import (
    CallContext,
    CallSink,
    FakeTransport,
    ModelAdapter,
    ModelRequest,
)
from adscout.llm.budget import (
    BYTES_PER_TOKEN,
    SEARCH_RESULT_TOKENS,
    TOOL_SYSTEM_TOKENS,
    BudgetExhausted,
    SpendLedger,
    estimate_prompt_tokens,
    worst_case_cost,
)
from adscout.llm.fakes import fake_message
from adscout.llm.prices import load_price_table
from adscout.pipeline.recorder import Run, RunFailed

HAIKU = "claude-haiku-5-5"
DAY = date(2026, 10, 19)


def scoring_request() -> ModelRequest:
    return ModelRequest(
        model=HAIKU,
        max_tokens=1000,
        system=[{"type": "text", "text": "Rate the lead."}],
        messages=[{"role": "user", "content": "example.test"}],
    )


def test_reservation_refused_past_the_cap_and_settled_to_actual() -> None:
    ledger = SpendLedger(Decimal("1.00"))
    first = ledger.reserve(Decimal("0.60"))
    with pytest.raises(BudgetExhausted, match=r"\$0\.60 reserved"):
        ledger.reserve(Decimal("0.50"))
    ledger.settle(first, Decimal("0.10"))
    assert (ledger.spent_usd, ledger.reserved_usd) == (Decimal("0.10"), Decimal(0))
    ledger.reserve(Decimal("0.90"))  # exactly at the cap is allowed
    with pytest.raises(ValueError, match="already settled"):
        ledger.settle(first, Decimal(0))
    with pytest.raises(ValueError, match="positive"):
        SpendLedger(Decimal(0))


def test_parallel_reservations_share_the_cap() -> None:
    ledger = SpendLedger(Decimal("1.00"))
    barrier = threading.Barrier(3)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        try:
            ledger.reserve(Decimal("0.40"))
            result = "reserved"
        except BudgetExhausted:
            result = "refused"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["refused", "reserved", "reserved"]
    assert ledger.reserved_usd == Decimal("0.80")


def test_parallel_calls_through_the_adapter_share_the_cap() -> None:
    worst = worst_case_cost(
        load_price_table(),
        HAIKU,
        prompt_tokens=estimate_prompt_tokens(len(scoring_request().canonical_bytes()), False, 0),
        max_tokens=1000,
        max_searches=0,
        on=DAY,
    )
    refused = threading.Event()

    def respond(request: ModelRequest) -> Message:
        # Keep both admitted calls in flight, holding their reservations, until the third
        # call has been refused; otherwise a settled call would free room for it.
        assert refused.wait(timeout=5)
        return fake_message(HAIKU, text="ok")

    transport = FakeTransport(respond)
    sink = CallSink()
    model = ModelAdapter(
        transport, load_price_table(), SpendLedger(worst * 2), sink, today=lambda: DAY
    )
    results: list[str] = []
    lock = threading.Lock()

    def call() -> None:
        try:
            model.call(scoring_request(), _context("r"))
            outcome = "called"
        except BudgetExhausted:
            outcome = "refused"
            refused.set()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=call) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["called", "called", "refused"]
    assert len(transport.requests) == 2
    assert sorted(record.status for record in sink.drain()) == [
        "refused",
        "succeeded",
        "succeeded",
    ]


def test_estimate_counts_bytes_tools_and_search_results() -> None:
    assert estimate_prompt_tokens(BYTES_PER_TOKEN * 10, False, 0) == 10
    assert estimate_prompt_tokens(BYTES_PER_TOKEN * 10 + 1, True, 2) == (
        11 + TOOL_SYSTEM_TOKENS + 2 * SEARCH_RESULT_TOKENS
    )


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


def test_cap_hit_mid_run_stops_the_run_and_keeps_its_rows(db: sqlite3.Connection) -> None:
    table = load_price_table()
    request = scoring_request()
    worst = worst_case_cost(
        table,
        HAIKU,
        prompt_tokens=estimate_prompt_tokens(len(request.canonical_bytes()), False, 0),
        max_tokens=1000,
        max_searches=0,
        on=DAY,
    )
    reply_cost = Decimal("0.0001")  # 1,000 input tokens on Haiku, no output
    # Room for two calls, settled at their actual cost, but not a third worst case.
    cap = 2 * reply_cost + worst - Decimal("0.000001")
    transport = FakeTransport(
        lambda request: fake_message(HAIKU, text="ok", input_tokens=1000, output_tokens=0)
    )
    run = Run(db, "pipeline", "test-segment", "fixture", {}, {}, budgets={"max_spend_usd": 0.0})
    model = ModelAdapter(transport, table, SpendLedger(cap), run.calls, today=lambda: DAY)
    with pytest.raises(RunFailed, match="BudgetExhausted"), run.recording():
        leads = _leads(db, run.run_id, 3)
        with run.step("score", "real", len(leads)):
            for lead_id in leads:
                model.call(request, _context(run.run_id, lead_id))

    assert len(transport.requests) == 2  # no call after the cap
    status = db.execute("SELECT status, error_category FROM runs").fetchone()
    assert tuple(status) == ("failed", "budget_exhausted")
    calls = db.execute("SELECT status, error_category FROM model_calls ORDER BY started_at")
    assert [tuple(row) for row in calls] == [
        ("succeeded", None),
        ("succeeded", None),
        ("refused", "budget_exhausted"),
    ]
    assert db.execute("SELECT count(*) FROM leads").fetchone()[0] == 3
    assert db.execute("SELECT status FROM step_runs").fetchone()[0] == "failed"


def _context(run_id: str, lead_id: str | None = None) -> CallContext:
    return CallContext(
        run_id=run_id,
        step="score",
        lead_id=lead_id or str(uuid7()),
        role="scorer",
        agent_name="scorer",
        prompt_version="p-0123456789ab",
        parent_span_id="0123456789abcdef",
    )


def _leads(db: sqlite3.Connection, run_id: str, count: int) -> list[str]:
    now = utc_now()
    leads = []
    for number in range(1, count + 1):
        db.execute(
            "INSERT INTO companies (company_id, domain, name, created_run_id, created_at) "
            "VALUES (?, ?, 'Example', ?, ?)",
            (number, f"example-{number}.test", run_id, now),
        )
        lead_id = str(uuid7())
        db.execute(
            "INSERT INTO leads VALUES (?, 'test-segment', ?, 'test', 'none', 'v', ?, ?)",
            (lead_id, number, run_id, now),
        )
        leads.append(lead_id)
    return leads
