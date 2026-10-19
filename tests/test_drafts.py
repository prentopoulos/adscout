"""The media kit, and the writer, rule checker and critic loop (decisions 30 to 32)."""

import copy
import json
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from anthropic.types import Message

from adscout.config import ConfigError
from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.drafts.media_kit import load_media_kit
from adscout.drafts.rules import PLACEHOLDERS
from adscout.drafts.step import Drafter, store
from adscout.ids import uuid7
from adscout.llm.adapter import FakeTransport, ModelAdapter, ModelRequest
from adscout.llm.budget import SpendLedger
from adscout.llm.fakes import fake_message
from adscout.llm.prices import load_price_table
from adscout.llm.prompts import load_prompt
from adscout.pipeline.contracts import Lead
from adscout.pipeline.recorder import Run
from adscout.research.handoffs import Claim, SummaryPoint, VerifiedClaim

KITS = Path(__file__).resolve().parent / "fixtures" / "config" / "media-kit"
KIT = load_media_kit(KITS / "fixture-publisher.yaml")
CASES = Path(__file__).resolve().parent.parent / "evals" / "cases" / "drafts.jsonl"
GOOD = json.loads(CASES.read_text(encoding="utf-8").split("\n")[0])["inputs"]["draft"]
CLAIMS = json.loads(CASES.read_text(encoding="utf-8").split("\n")[0])["inputs"]["claims"]
LEAD = Lead(lead_id=str(uuid7()), company_id=1, domain="alpha.test", name="Alpha Gear")


def verified(claim_id: str, text: str) -> VerifiedClaim:
    return VerifiedClaim(
        claim_id=claim_id,
        worker="worker_ads",
        claim=Claim(topic="ad_activity", text=text, source_url="https://alpha.test/", quote=text),
        fetch_call_id="c",
        url_fetched_in_run=True,
        quote_found=True,
        numbers_ok=True,
        verifier_version="v1",
    )


def bad_draft() -> dict[str, Any]:
    found = copy.deepcopy(GOOD)
    found["sentences"][2] = {
        "text": "We reach 2 million gamers in the US and Canada.",
        "supports": ["mk-audience"],
    }
    return found


class Team:
    def __init__(self, writes: list[Any], critiques: list[Any]) -> None:
        self.writes, self.critiques = writes, critiques
        self.writer_prompt, self.critic_prompt = (
            load_prompt("draft_writer"),
            load_prompt("draft_critic"),
        )

    def __call__(self, request: ModelRequest) -> Message:
        system = str(request.system[0]["text"])
        if system.startswith(self.writer_prompt.text):
            return fake_message(
                request.model, data=self.writes.pop(0), input_tokens=2500, output_tokens=300
            )
        return fake_message(
            request.model, data=self.critiques.pop(0), input_tokens=1500, output_tokens=100
        )


APPROVE = {"verdict": "approve", "issues": []}
REVISE = {"verdict": "revise", "issues": [{"aspect": "ask", "problem": "The ask is vague."}]}


def drafter(team: Team, sink: Any = None) -> tuple[Drafter, FakeTransport]:
    from adscout.llm.adapter import CallSink

    transport = FakeTransport(team)
    adapter = ModelAdapter(
        transport,
        load_price_table(),
        SpendLedger(None),
        sink if sink is not None else CallSink(),
        today=lambda: date(2026, 10, 19),
    )
    return Drafter(adapter, KIT, team.writer_prompt, team.critic_prompt), transport


def run_draft(team: Team, sink: Any = None, run_id: str = "r") -> tuple[Any, FakeTransport]:
    drafts, transport = drafter(team, sink)
    claims = [verified(claim_id, text) for claim_id, text in CLAIMS.items()]
    points = [SummaryPoint(text="Alpha Gear launched the K1.", claim_ids=["L1"])]
    return drafts.draft(LEAD, points, claims, run_id), transport


def roles(transport: FakeTransport) -> list[str]:
    writer = load_prompt("draft_writer").text
    return [
        "writer" if str(r.system[0]["text"]).startswith(writer) else "critic"
        for r in transport.requests
    ]


def test_media_kit_loads_and_every_fact_is_simulated() -> None:
    assert KIT.name == "Fixture Gaming Media" and KIT.fictional
    assert all(fact.simulated for fact in KIT.facts)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["facts"][1].pop("simulated"), "fact 'mk-video' is not marked simulated: true"),
        (
            lambda d: d["facts"][0].update(simulated=False),
            "fact 'mk-audience' is not marked simulated",
        ),
        (lambda d: d["facts"].append(dict(d["facts"][0])), "fact IDs repeated"),
        (lambda d: d.update(publisher_id="other"), "differs from the file"),
        (lambda d: d.update(fictional=False), "fictional"),
    ],
)
def test_invalid_media_kits_are_refused(tmp_path: Path, change: Any, message: str) -> None:
    data = yaml.safe_load((KITS / "fixture-publisher.yaml").read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "fixture-publisher.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_media_kit(path)


def test_a_good_draft_approved_by_the_critic_waits_for_approval() -> None:
    drafted, transport = run_draft(Team([GOOD], [APPROVE]))
    assert (drafted.outcome.outcome, drafted.outcome.flag) == ("kept", None)
    assert drafted.outcome.detail == "pending_approval"
    assert roles(transport) == ["writer", "critic"]
    assert all(request.tools == [] for request in transport.requests)


def test_the_critic_cannot_pass_a_draft_the_rules_fail() -> None:
    drafted, transport = run_draft(Team([bad_draft(), bad_draft(), bad_draft()], [APPROVE] * 3))
    assert roles(transport) == ["writer", "writer", "writer"]  # the critic never saw it
    assert (drafted.outcome.outcome, drafted.outcome.reason) == ("exited", "draft_failed")
    assert "numbers" in drafted.outcome.detail and len(drafted.attempts) == 3


def test_a_rule_problem_goes_back_to_the_writer() -> None:
    drafted, transport = run_draft(Team([bad_draft(), GOOD], [APPROVE]))
    assert roles(transport) == ["writer", "writer", "critic"]
    feedback = transport.requests[1].messages[-1]["content"]
    assert (
        feedback.startswith("Revise the draft")
        and "numbers ['2'] are not in its supports" in feedback
    )
    assert drafted.outcome.outcome == "kept" and len(drafted.attempts) == 2


def test_an_unresolved_critic_flags_the_draft_and_keeps_its_notes() -> None:
    drafted, transport = run_draft(Team([GOOD, GOOD, GOOD], [REVISE, REVISE, REVISE]))
    assert roles(transport) == ["writer", "critic"] * 3
    assert (drafted.outcome.outcome, drafted.outcome.flag) == ("kept", "critic_unresolved")
    assert "ask: The ask is vague." in drafted.outcome.detail


def test_a_failed_writer_exits_as_draft_failed() -> None:
    drafted, transport = run_draft(Team(["not a draft", "nope", "nope"], []))
    assert drafted.outcome.reason == "draft_failed" and "writer failed" in drafted.outcome.detail
    assert len(transport.requests) == 3  # primary, retry, fallback


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


def test_the_stored_draft_has_the_footer_once_and_every_attempt(db: sqlite3.Connection) -> None:
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
    with run.step("draft", "real", 1) as recorder:
        drafted, _ = run_draft(
            Team([bad_draft(), GOOD, GOOD], [REVISE, APPROVE]), sink=run.calls, run_id=run.run_id
        )
        recorder.defer(lambda: store(db, run.run_id, drafted, None))
        recorder.outcomes.append(drafted.outcome)
    row = db.execute("SELECT * FROM drafts").fetchone()
    assert (row["status"], row["revision"], row["publisher_id"]) == (
        "pending_approval",
        3,
        "fixture-publisher",
    )
    assert all(row["body"].count(placeholder) == 1 for placeholder in PLACEHOLDERS)
    assert "Fixture Gaming Media" in row["body"]
    checks = json.loads(row["checks_json"])
    assert [bool(item["problems"]) for item in checks] == [True, False, False]
    assert [item["verdict"] for item in json.loads(row["critic_notes_json"])] == [
        "revise",
        "approve",
    ]
    spans = db.execute(
        "SELECT agent_name FROM spans WHERE agent_name IS NOT NULL ORDER BY started_at"
    ).fetchall()
    assert [r[0] for r in spans] == ["writer", "writer", "critic", "writer", "critic"]
