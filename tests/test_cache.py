"""The record-and-replay cache: a recorded run replays at $0 (Phase 2 design, decision 20).

The "live" run here drives the real SDK client over an in-process HTTP transport, so the
recording path is the live one while nothing leaves the process.
"""

import sqlite3
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx2
import pytest

from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.ids import uuid7
from adscout.llm.adapter import (
    CallContext,
    LiveTransport,
    ModelAdapter,
    ModelCallFailed,
    ModelRequest,
)
from adscout.llm.budget import SpendLedger
from adscout.llm.cache import Recorder, ReplayCache, ReplayMiss, ReplayTransport
from adscout.llm.fakes import fake_message
from adscout.llm.invoke import HAIKU, SONNET, InvalidOutput, invoke
from adscout.llm.prices import load_price_table
from adscout.pipeline.recorder import Run

DAY = date(2026, 10, 19)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


@pytest.fixture
def cache(tmp_path: Path) -> Iterator[ReplayCache]:
    opened = ReplayCache(tmp_path / "data" / "cache.db")
    yield opened
    opened.close()


def request(text: str) -> ModelRequest:
    return ModelRequest(
        model=HAIKU,
        max_tokens=300,
        system=[{"type": "text", "text": "Rate the lead."}],
        messages=[{"role": "user", "content": text}],
    )


def context(run_id: str, lead_id: str) -> CallContext:
    return CallContext(
        run_id=run_id,
        step="score",
        lead_id=lead_id,
        role="scorer",
        agent_name="scorer",
        prompt_version="p-0123456789ab",
        parent_span_id="0123456789abcdef",
    )


def lead(db: sqlite3.Connection, run_id: str) -> str:
    lead_id, now = str(uuid7()), utc_now()
    db.execute(
        "INSERT OR IGNORE INTO companies (company_id, domain, name, created_run_id, created_at) "
        "VALUES (1, 'example.test', 'Example', ?, ?)",
        (run_id, now),
    )
    db.execute(
        "INSERT OR IGNORE INTO leads VALUES (?, 'test-segment', 1, 'test', 'none', 'v', ?, ?)",
        (lead_id, run_id, now),
    )
    return str(db.execute("SELECT lead_id FROM leads").fetchone()[0])


def parse(result: Any) -> str:
    if result.text == "bad":
        raise InvalidOutput("bad answer")
    return str(result.text)


def live_replies() -> list[httpx2.Response]:
    def ok(text: str, model: str = HAIKU) -> httpx2.Response:
        return httpx2.Response(
            200, json=fake_message(model, text=text, input_tokens=900, output_tokens=40).to_dict()
        )

    overloaded = httpx2.Response(
        529, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
    )
    # Three different samples; then "other lead": invalid, the retry overloaded, fallback.
    return [ok("2"), ok("4"), ok("3"), ok("bad"), overloaded, ok("5", SONNET)]


def test_replay_reproduces_a_recorded_run_at_no_cost(
    db: sqlite3.Connection, cache: ReplayCache
) -> None:
    replies = live_replies()
    client = httpx2.Client(transport=httpx2.MockTransport(lambda outgoing: replies.pop(0)))
    live_run = Run(db, "pipeline", "test-segment", "live", {}, {})
    live = ModelAdapter(
        LiveTransport("sk-ant-test", http_client=client, attempts=1),
        load_price_table(),
        SpendLedger(Decimal(1)),
        live_run.calls,
        today=lambda: DAY,
        recorder=Recorder(cache, live_run.run_id),
    )
    live_run.start()
    lead_id = lead(db, live_run.run_id)
    original = run_flow(live, live_run, lead_id)
    assert original == ["2", "4", "3", "5"] and replies == []

    replay_run = Run(db, "pipeline", "test-segment", "replay", {}, {})
    replay = ModelAdapter(
        ReplayTransport(cache, live_run.run_id),
        load_price_table(),
        SpendLedger(None),
        replay_run.calls,
        today=lambda: DAY,
    )
    replay_run.start()
    assert run_flow(replay, replay_run, lead_id) == original

    def rows(run_id: str) -> list[sqlite3.Row]:
        return db.execute(
            "SELECT * FROM model_calls WHERE run_id = ? ORDER BY started_at, call_id", (run_id,)
        ).fetchall()

    recorded, replayed = rows(live_run.run_id), rows(replay_run.run_id)
    assert (
        [r["call_role"] for r in replayed]
        == [r["call_role"] for r in recorded]
        == [
            "primary",
            "primary",
            "primary",
            "primary",
            "retry",
            "fallback",
        ]
    )
    assert [r["status"] for r in replayed] == [r["status"] for r in recorded]
    assert all(r["mode"] == "replay" and r["cost_usd"] == 0 for r in replayed)
    assert [r["original_cost_usd"] for r in replayed] == [r["cost_usd"] for r in recorded]
    assert [r["request_sha256"] for r in replayed] == [r["request_sha256"] for r in recorded]
    assert sum(r["cost_usd"] for r in recorded) > 0
    assert (
        db.execute("SELECT source FROM runs WHERE run_id = ?", (replay_run.run_id,)).fetchone()[0]
        == "replay"
    )


def run_flow(model: ModelAdapter, run: Run, lead_id: str) -> list[str]:
    """Three scoring samples of one request, then a call that is retried and falls back."""
    outputs = []
    with run.step("score", "real", 1):
        for _ in range(3):
            outputs.append(model.call(request("same lead"), context(run.run_id, lead_id)).text)
        outputs.append(
            invoke(model, request("other lead"), context(run.run_id, lead_id), parse).value
        )
    run.finish("succeeded")
    return outputs


def test_replay_of_an_unrecorded_request_fails_without_a_fallback(cache: ReplayCache) -> None:
    transport = ReplayTransport(cache, "20261019T000000Z-aaaaaa")
    with pytest.raises(ReplayMiss, match="recorded no answer #1") as caught:
        transport.send(request("never seen"), "0" * 64)
    assert isinstance(caught.value, ModelCallFailed) and not caught.value.fallback_allowed


def test_cache_counts_responses_per_run(cache: ReplayCache) -> None:
    recorder = Recorder(cache, "run-a")
    message = fake_message(HAIKU, text="x")
    recorder.response("a" * 64, message, Decimal("0.001"))
    recorder.response("a" * 64, message, Decimal("0.002"))
    recorder.failure("b" * 64, RuntimeError("not a call error"))
    assert cache.responses("run-a") == 2
    assert cache.load("run-a", "a" * 64, 2)[1] == Decimal("0.002")
