"""The independent run check, run summaries, the run export and the demo script."""

import json
import socket
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import demo
import jsonschema
import pytest
from pytest_socket import SocketBlockedError

from adscout import cli
from adscout.check import check_run
from adscout.db.connection import connect
from adscout.db.migrate import upgrade
from adscout.export import ATTRIBUTES, EVIDENCE, ExportRefused, export_lines, write_export
from adscout.pipeline.run import SegmentFiles, run_crm_sync, run_pipeline, run_stub_approval
from adscout.report import funnel, list_runs
from adscout.schema_files import ROOT

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "config"
SYNTHETIC = "synthetic-demo"
EXPORT_SCHEMA = ROOT / "src" / "adscout" / "schemas" / "run-export.schema.json"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


@pytest.fixture
def flow(db: sqlite3.Connection) -> list[str]:
    files = SegmentFiles.load(FIXTURES, SYNTHETIC)
    return [
        run_pipeline(db, files),
        run_stub_approval(db, files.segment, files.script),
        run_crm_sync(db, files.segment),
    ]


def validation(db: sqlite3.Connection, run_id: str) -> tuple[str, str]:
    row = db.execute(
        "SELECT validation_outcome, validation_detail FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    return row[0], row[1]


def test_clean_runs_pass_and_record_it(db: sqlite3.Connection, flow: list[str]) -> None:
    for run_id in flow:
        result = check_run(db, run_id)
        assert result.outcome == "pass", result.problems
        assert validation(db, run_id) == ("pass", "all checks passed")


def test_broken_conservation_fails_and_names_the_step(
    db: sqlite3.Connection, flow: list[str]
) -> None:
    db.execute(
        "UPDATE step_runs SET kept = kept + 1 WHERE run_id = ? AND step = 'rules'", (flow[0],)
    )
    result = check_run(db, flow[0])
    assert result.outcome == "fail"
    assert any(problem.startswith("rules: kept") for problem in result.problems)
    assert validation(db, flow[0])[0] == "fail"


def test_rising_funnel_fails(db: sqlite3.Connection, flow: list[str]) -> None:
    db.execute("UPDATE step_runs SET entering = 99 WHERE run_id = ? AND step = 'draft'", (flow[0],))
    problems = check_run(db, flow[0]).problems
    assert any("draft: entering 99 exceeds" in problem for problem in problems)


def test_unlabelled_stub_row_fails(db: sqlite3.Connection, flow: list[str]) -> None:
    # Briefs cannot be relabelled at all: a real brief needs a design (migration 0002).
    db.execute("UPDATE drafts SET implementation = 'real' WHERE run_id = ?", (flow[0],))
    problems = check_run(db, flow[0]).problems
    assert any(problem.startswith("drafts:") for problem in problems)


def test_stub_brief_with_claims_fails(db: sqlite3.Connection, flow: list[str]) -> None:
    db.execute(
        "UPDATE briefs SET claims_json = ? WHERE run_id = ?",
        (json.dumps([{"text": "x", "source_url": "https://example.test"}]), flow[0]),
    )
    assert "briefs: " in "; ".join(check_run(db, flow[0]).problems)


def test_crm_write_without_valid_approval_fails(db: sqlite3.Connection, flow: list[str]) -> None:
    db.execute("UPDATE drafts SET body = body || ' tampered' WHERE status = 'approved'")
    problems = check_run(db, flow[2]).problems
    assert problems and all("has no valid approval" in problem for problem in problems)


def test_failed_run_is_checked_on_the_steps_it_finished(db: sqlite3.Connection) -> None:
    files = SegmentFiles.load(FIXTURES, SYNTHETIC)
    run_id = run_pipeline(db, files)
    db.execute("UPDATE runs SET status = 'running', ended_at = NULL WHERE run_id = ?", (run_id,))
    assert "the run is still running" in check_run(db, run_id).problems


def test_unknown_run_is_reported(db: sqlite3.Connection) -> None:
    with pytest.raises(LookupError):
        check_run(db, "no-such-run")


def test_runs_and_funnel_summaries(db: sqlite3.Connection, flow: list[str]) -> None:
    listing = list_runs(db)
    assert all(run_id in listing for run_id in flow)
    assert list_runs(db, "other-segment") == "no runs yet"
    text = funnel(db, flow[0])
    assert "source of data: fixture (scripted stub steps" in text
    assert "below_threshold 1" in text and "missing_key_fields 1" in text
    assert "research_partial 1" in text
    assert "rejected 1" in funnel(db, flow[1])


def test_export_validates_against_the_committed_schema(
    db: sqlite3.Connection, flow: list[str]
) -> None:
    schema = json.loads(EXPORT_SCHEMA.read_text(encoding="utf-8"))
    for run_id in flow:
        lines = export_lines(db, run_id)
        for line in lines:
            jsonschema.validate(line, schema)
        assert lines[0]["record"] == "run" and lines[0]["langfuse.session.id"] == run_id
    steps = [line for line in export_lines(db, flow[0]) if line["record"] == "step"]
    for step in steps:
        assert step["gen_ai.request.model"] is None
        assert step["gen_ai.usage.input_tokens"] is None
        assert set(step["null_reasons"]) == {
            "gen_ai.request.model",
            "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens",
            "gen_ai.usage.cost",
        }
    run = export_lines(db, flow[0])[0]
    assert run["adscout.minutes_per_account"] is None
    assert "adscout.minutes_per_account" in run["null_reasons"]
    approval = export_lines(db, flow[1])[0]
    assert approval["adscout.seed_list_hash"] is None
    assert set(approval["null_reasons"]) == {
        "adscout.seed_list_hash",
        "adscout.minutes_per_account",
    }
    assert set(ATTRIBUTES.values()) <= {key for line in export_lines(db, flow[0]) for key in line}


def test_export_never_overwrites(db: sqlite3.Connection, flow: list[str], tmp_path: Path) -> None:
    out = tmp_path / "run.jsonl"
    write_export(db, flow[0], out)
    assert len(out.read_text(encoding="utf-8").splitlines()) == len(export_lines(db, flow[0]))
    with pytest.raises(FileExistsError):
        write_export(db, flow[0], out)


def test_evidence_export_from_a_dirty_tree_is_refused(
    db: sqlite3.Connection, flow: list[str]
) -> None:
    db.execute("UPDATE runs SET code_dirty = 1 WHERE run_id = ?", (flow[0],))
    target = EVIDENCE / "must-not-exist.jsonl"
    with pytest.raises(ExportRefused, match="clean tree"):
        write_export(db, flow[0], target)
    assert not target.exists()


def test_commands_summarize_check_and_export(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "cli.db"
    run_ids = demo.demo(SYNTHETIC, FIXTURES, path)
    capsys.readouterr()
    db = ["--db", str(path)]
    assert cli.main(["runs", *db]) == 0
    assert run_ids[0] in capsys.readouterr().out
    assert cli.main(["funnel", run_ids[0], *db]) == 0
    assert "below_threshold" in capsys.readouterr().out
    assert cli.main(["check", run_ids[1], *db]) == 0
    assert "pass" in capsys.readouterr().out
    assert cli.main(["export", run_ids[2], *db]) == 0
    assert '"record": "run"' in capsys.readouterr().out
    out = tmp_path / "export.jsonl"
    assert cli.main(["export", run_ids[2], *db, "--out", str(out)]) == 0
    assert cli.main(["export", run_ids[2], *db, "--out", str(out)]) == 1
    assert cli.main(["funnel", "no-such-run", *db]) == 1
    assert cli.main(["check", "no-such-run", *db]) == 1
    assert cli.main(["runs", "--db", str(tmp_path / "missing.db")]) == 1


def test_check_command_fails_on_a_broken_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "cli.db"
    run_ids = demo.demo(SYNTHETIC, FIXTURES, path)
    connection = connect(path)
    connection.execute(
        "UPDATE step_runs SET exited = 7 WHERE run_id = ? AND step = 'score'", (run_ids[0],)
    )
    connection.close()
    capsys.readouterr()
    assert cli.main(["check", run_ids[0], "--db", str(path)]) == 1
    assert "score: kept" in capsys.readouterr().out


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_demo_runs_offline_and_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SocketBlockedError):
        socket.socket()
    code = demo.main(
        ["--segment", SYNTHETIC, "--config-dir", str(FIXTURES), "--db", str(tmp_path / "demo.db")]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("check pass") == 3
    assert "crm_sync run" in out
