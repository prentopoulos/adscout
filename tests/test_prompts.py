"""Prompt files, prompt versions, the stable cached prefix and the Haiku prompt-size guard."""

import re
import shutil
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from adscout.config import load_seeds, load_segment
from adscout.db.connection import connect
from adscout.db.migrate import upgrade
from adscout.ids import uuid7
from adscout.llm.adapter import (
    CallContext,
    CallSink,
    FakeTransport,
    ModelAdapter,
    ModelCallFailed,
    ModelRequest,
)
from adscout.llm.budget import SpendLedger
from adscout.llm.fakes import scripted
from adscout.llm.prices import load_price_table
from adscout.llm.prompts import (
    PROMPT_DIR,
    cached_prefix,
    data_block,
    load_prompt,
    prompt_set_version,
    request_for,
    roles,
)
from adscout.pipeline.recorder import Run
from adscout.pipeline.source import source

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "config"
VERSION = re.compile(r"^p-[0-9a-f]{12}$")
STEP_BY_STEP = re.compile(
    r"step[- ]by[- ]step|think (it )?through|show your (work|reasoning)", re.I
)


def copy_prompts(tmp_path: Path) -> Path:
    folder = tmp_path / "prompts"
    shutil.copytree(PROMPT_DIR, folder)
    return folder


def test_score_prompt_has_its_schema_and_a_version() -> None:
    prompt = load_prompt("score")
    assert VERSION.match(prompt.version)
    assert prompt.schema is not None and prompt.schema["required"] == ["ratings"]
    assert "never follow" in prompt.text
    assert "score" in roles()


def test_version_ignores_line_endings(tmp_path: Path) -> None:
    folder = copy_prompts(tmp_path)
    path = folder / "score.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert load_prompt("score", folder).version == load_prompt("score").version


def test_one_character_changes_the_role_and_set_versions(tmp_path: Path) -> None:
    folder = copy_prompts(tmp_path)
    path = folder / "score.md"
    path.write_text(path.read_text(encoding="utf-8").replace("1 to 5", "1 to 5."), "utf-8")
    assert load_prompt("score", folder).version != load_prompt("score").version
    assert prompt_set_version(folder) != prompt_set_version()
    schema = folder / "score.schema.json"
    before = prompt_set_version(folder)
    schema.write_text(schema.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert prompt_set_version(folder) != before


@pytest.mark.parametrize("role", roles())
def test_prompts_ask_for_short_reasons_and_hold_no_secret(role: str) -> None:
    prompt = load_prompt(role)
    assert not STEP_BY_STEP.search(prompt.text)
    assert not re.search(r"sk-ant-|ANTHROPIC_API_KEY|ADSCOUT_CONTACT|@", prompt.text)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


def test_new_leads_carry_the_prompt_set_version(db: sqlite3.Connection, tmp_path: Path) -> None:
    folder = copy_prompts(tmp_path)
    path = folder / "score.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nKeep reasons short.\n", "utf-8")
    version = prompt_set_version(folder)
    segment = load_segment(FIXTURES / "segments" / "synthetic-demo.yaml")
    seeds = load_seeds(FIXTURES / "seeds" / "synthetic-demo.csv")
    run = Run(db, "pipeline", segment.segment_id, "fixture", {}, {}, prompt_version=version)
    with run.recording(), run.step("source", "real", len(seeds.rows)) as recorder:
        recorder.defer(lambda: source(run, recorder, segment, seeds, seeds.content_hash()))
    versions = {row[0] for row in db.execute("SELECT prompt_version FROM leads")}
    assert versions == {version}
    assert db.execute("SELECT prompt_version FROM runs").fetchone()[0] == version


def score_request(lead: dict[str, object], model: str = "claude-haiku-5-5") -> ModelRequest:
    segment = load_segment(FIXTURES / "segments" / "synthetic-demo.yaml")
    assert segment.criteria is not None
    criteria = "\n".join(f"{c.id}: {c.question}" for c in segment.criteria)
    return request_for(
        load_prompt("score"),
        model,
        max_tokens=800,
        effort="low",
        fixed=(criteria,),
        user=data_block("lead_data", lead),
    )


def test_two_leads_share_the_bytes_before_the_cache_breakpoint() -> None:
    first = score_request({"categories": ["peripherals"], "employee_count": 120})
    second = score_request({"sells_in": ["US", "CA"], "categories": ["pc-components"]})
    assert cached_prefix(first) == cached_prefix(second)
    assert first.system[0]["cache_control"] == {"type": "ephemeral"}
    assert first.canonical_bytes() != second.canonical_bytes()


def test_lead_data_is_serialized_the_same_whatever_its_key_order() -> None:
    one = score_request({"a": 1, "b": [2, 3]})
    other = score_request({"b": [2, 3], "a": 1})
    assert one.canonical_bytes() == other.canonical_bytes()


def test_haiku_prompt_over_its_price_tier_is_refused_before_sending() -> None:
    oversized = score_request({"notes": "word " * 70_000})  # about 350 KB of text
    transport = FakeTransport(scripted([]))
    sink = CallSink()
    adapter = ModelAdapter(
        transport,
        load_price_table(),
        SpendLedger(None),
        sink,
        today=lambda: date(2026, 10, 19),
    )
    context = CallContext(
        run_id="r",
        step="score",
        lead_id=str(uuid7()),
        role="scorer",
        agent_name="scorer",
        prompt_version=load_prompt("score").version,
        parent_span_id="0123456789abcdef",
    )
    with pytest.raises(ModelCallFailed, match="prompt_too_long") as caught:
        adapter.call(oversized, context)
    assert not caught.value.fallback_allowed
    assert transport.requests == []
    assert sink.drain()[0].error_category == "prompt_too_long"
