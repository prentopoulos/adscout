"""Trace export, the trace check, the end-of-run cost table and `adscout trace` (decision 36)."""

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from adscout import cli
from adscout.check import check_run
from adscout.costs import NO_QUALIFIED, cost_summary
from adscout.db.migrate import upgrade
from adscout.export import (
    ATTRIBUTES,
    AgentSpanRecord,
    ModelCallRecord,
    OutcomeRecord,
    RunRecord,
    SourceCallRecord,
    StepRecord,
    StepSpanRecord,
    export_lines,
)
from adscout.pipeline.real import Steps
from adscout.schema_files import ROOT
from adscout.trace import trace_text

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXPORT_SCHEMA = ROOT / "src" / "adscout" / "schemas" / "run-export.schema.json"
SEGMENT = ["--segment", "synthetic-demo", "--config-dir", str(FIXTURES / "config")]
OFFLINE = [
    *SEGMENT,
    "--fixture-models",
    str(FIXTURES / "models" / "synthetic-demo.yaml"),
    "--fixture-sites",
    str(FIXTURES / "sites"),
    "--media-kit",
    str(FIXTURES / "config" / "media-kit" / "fixture-publisher.yaml"),
]
COUNTS = {
    "spans": "SELECT count(*) FROM spans WHERE run_id = ?",
    "model_calls": "SELECT count(*) FROM model_calls WHERE run_id = ?",
    "source_calls": "SELECT count(*) FROM source_calls WHERE run_id = ?",
}
RECORDS = (
    RunRecord,
    StepRecord,
    OutcomeRecord,
    StepSpanRecord,
    AgentSpanRecord,
    ModelCallRecord,
    SourceCallRecord,
)


@pytest.fixture(scope="module")
def offline(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """One offline run of the real pipeline, shared by the tests that only read it."""
    db = tmp_path_factory.mktemp("observability") / "adscout.db"
    upgrade(db)
    assert cli.main(["run", *OFFLINE, "--db", str(db)]) == 0
    connection = sqlite3.connect(db)
    run_id = str(connection.execute("SELECT run_id FROM runs").fetchone()[0])
    connection.close()
    return db, run_id


def connect(db: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    return connection


# --- export -----------------------------------------------------------------------------------


def test_every_otel_and_langfuse_name_comes_from_the_one_mapping_table() -> None:
    mapped = set(ATTRIBUTES.values())
    for record in RECORDS:
        for name, info in record.model_fields.items():
            alias = info.alias or name
            if alias.startswith(("gen_ai.", "langfuse.", "error.", "http.")):
                assert alias in mapped, (record.__name__, alias)


def test_the_export_carries_every_trace_span(offline: tuple[Path, str]) -> None:
    db, run_id = offline
    connection = connect(db)
    lines = export_lines(connection, run_id)
    schema = json.loads(EXPORT_SCHEMA.read_text(encoding="utf-8"))
    for line in lines:
        jsonschema.validate(line, schema)
    assert set(ATTRIBUTES.values()) <= {key for line in lines for key in line}
    counts = {
        table: connection.execute(query, (run_id,)).fetchone()[0] for table, query in COUNTS.items()
    }
    kinds = [line["record"] for line in lines]
    assert kinds.count("step_span") + kinds.count("agent_span") == counts["spans"]
    assert kinds.count("model_call") == counts["model_calls"]
    assert kinds.count("source_call") == counts["source_calls"]

    calls = [line for line in lines if line["record"] == "model_call"]
    scorer = next(call for call in calls if call["gen_ai.agent.name"] == "scorer")
    assert scorer["gen_ai.usage.cache_read.input_tokens"] == 1200
    assert scorer["gen_ai.usage.input_tokens"] == 1800 + 1200  # cached tokens included
    assert scorer["gen_ai.provider.name"] == "anthropic"
    assert scorer["gen_ai.agent.version"].startswith("p-")
    assert scorer["name"] == "chat claude-sonnet-5-5"
    assert scorer["langfuse.observation.type"] == "generation"
    agents = [line for line in lines if line["record"] == "agent_span"]
    assert all(agent["gen_ai.agent.version"].startswith("p-") for agent in agents)
    failed = [a for a in agents if a["status_code"] == "ERROR"]
    assert {a["gen_ai.agent.name"] for a in failed} >= {"worker_ads"}  # hotel's planted failure
    run = lines[0]
    assert run["adscout.cost_summary"]["qualified_leads"] == 4
    connection.close()


def test_worker_calls_nest_under_the_research_step(offline: tuple[Path, str]) -> None:
    db, run_id = offline
    connection = connect(db)
    parents = dict(
        connection.execute("SELECT span_id, parent_span_id FROM spans WHERE run_id = ?", (run_id,))
    )
    roots = {
        row["span_id"]: (row["lead_id"], row["step"])
        for row in connection.execute(
            "SELECT * FROM spans WHERE run_id = ? AND operation = 'step'", (run_id,)
        )
    }
    workers = connection.execute(
        "SELECT lead_id, parent_span_id FROM model_calls "
        "WHERE run_id = ? AND agent_name LIKE 'worker_%'",
        (run_id,),
    ).fetchall()
    assert workers
    for call in workers:
        span = call["parent_span_id"]
        while parents.get(span) is not None:
            span = parents[span]
        assert roots[span] == (call["lead_id"], "research")
    connection.close()


def test_the_check_follows_parent_spans(offline: tuple[Path, str], tmp_path: Path) -> None:
    db, run_id = offline
    copy = tmp_path / "copy.db"
    source = sqlite3.connect(db)
    source.backup(target := sqlite3.connect(copy))
    source.close()
    target.close()
    connection = connect(copy)
    assert check_run(connection, run_id).outcome == "pass"
    span = connection.execute(
        "SELECT * FROM spans WHERE run_id = ? AND operation = 'invoke_agent' LIMIT 1", (run_id,)
    ).fetchone()
    connection.execute(
        "UPDATE spans SET parent_span_id = 'ffffffffffffffff' WHERE span_id = ?",
        (span["span_id"],),
    )
    connection.commit()
    result = check_run(connection, run_id)
    assert result.outcome == "fail"
    assert f"spans span {span['span_id']}: parent ffffffffffffffff" in result.detail
    connection.close()


# --- the cost table -------------------------------------------------------------------------


def test_the_cost_table_is_stored_and_adds_up(offline: tuple[Path, str]) -> None:
    db, run_id = offline
    connection = connect(db)
    stored = json.loads(
        connection.execute(
            "SELECT cost_summary_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
    )
    assert stored == cost_summary(connection, run_id)
    steps = {
        row["step"]: row["cost_usd"]
        for row in connection.execute(
            "SELECT step, cost_usd FROM step_runs WHERE run_id = ? AND cost_usd IS NOT NULL",
            (run_id,),
        )
    }
    total = Decimal(stored["total"]["cost_usd"])
    # Step totals are REAL sums in SQLite and drift in the last digits; the table is exact.
    assert total == round(sum(Decimal(str(cost)) for cost in steps.values()), 9)
    assert stored["total"]["calls"] == sum(row["calls"] for row in stored["rows"])
    assert {(row["step"], row["role"]) for row in stored["rows"]} >= {
        ("enrich", "extractor"),
        ("score", "scorer"),
        ("research", "worker_ads"),
        ("draft", "critic"),
    }
    # alpha, bravo, charlie, delta, echo, foxtrot, golf, hotel; alpha's repeat and the
    # excluded domain stop at source.
    assert (stored["leads"], stored["qualified_leads"]) == (8, 4)
    assert Decimal(stored["cost_per_qualified_lead_usd"]) == round(total / 4, 6)
    assert stored["null_reasons"] == {}
    connection.close()


def test_a_run_with_no_qualified_lead_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "adscout.db"
    upgrade(db)
    assert cli.main(["run", "--stub", *SEGMENT, "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "no model calls" in out
    assert f"cost per qualified lead: null ({NO_QUALIFIED})" in out
    connection = connect(db)
    summary = json.loads(connection.execute("SELECT cost_summary_json FROM runs").fetchone()[0])
    assert summary["cost_per_qualified_lead_usd"] is None
    assert summary["null_reasons"]["cost_per_qualified_lead_usd"] == NO_QUALIFIED
    connection.close()


def test_a_failed_run_still_stores_and_prints_its_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "adscout.db"
    upgrade(db)

    def broken(self: Steps, state: object) -> dict[str, object]:
        raise RuntimeError("draft step broke")

    monkeypatch.setattr(Steps, "draft", broken)
    assert cli.main(["run", *OFFLINE, "--db", str(db)]) == 1
    captured = capsys.readouterr()
    assert "draft step broke" in captured.err
    assert "cost by step, role and model" in captured.out
    connection = connect(db)
    run = connection.execute("SELECT status, cost_summary_json FROM runs").fetchone()
    assert run["status"] == "failed"
    assert json.loads(run["cost_summary_json"])["total"]["calls"] > 0
    connection.close()


# --- adscout trace --------------------------------------------------------------------------


def test_trace_prints_each_leads_tree_from_the_database(
    offline: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    db, run_id = offline
    assert cli.main(["trace", run_id, "--lead", "hotel.test", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("hotel.test (lead ")
    assert "last outcome: draft kept critic_unresolved" in out
    for expected in (
        "research step",
        "invoke_agent worker_ads p-",
        "[failed]",
        "execute_tool page https://hotel.test/news, HTTP 200",
        "chat claude-haiku-5-5 [worker_launches], in 2000 (+0 cached), out 80, $0.000240",
        "chat claude-sonnet-5-5 [scorer], in 1800 (+1200 cached)",
    ):
        assert expected in out, expected
    draft = out[out.index("draft step") :]
    agents = [
        line.split("invoke_agent ")[1].split()[0]
        for line in draft.splitlines()
        if "invoke_agent" in line
    ]
    assert agents == ["writer", "critic"] * 3  # the loop in the order it ran
    whole = trace_text(connect(db), run_id)
    assert "excluded.test" in whole and "no spans: no model or source call" in whole
    assert cli.main(["trace", run_id, "--lead", "nowhere.test", "--db", str(db)]) == 1
    assert f"no lead nowhere.test in run {run_id}" in capsys.readouterr().err
