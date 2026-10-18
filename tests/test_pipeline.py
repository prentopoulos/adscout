"""The pipeline, stub approver and CRM sync runs, on synthetic and on the real seeds."""

import json
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from adscout import cli
from adscout.config import ConfigError
from adscout.crm.writer import CrmWriteRefused, write_account
from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.pipeline.recorder import RunFailed, RunInProgress, process_alive
from adscout.pipeline.run import (
    DatabaseNotReady,
    SegmentFiles,
    run_crm_sync,
    run_pipeline,
    run_stub_approval,
)
from adscout.pipeline.stubs import load_stub_script

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "config"
SYNTHETIC = "synthetic-demo"
REAL = "gaming-hardware-na"
EXIT_REASONS = {
    "duplicate",
    "excluded",
    "out_of_profile",
    "missing_key_fields",
    "below_threshold",
    "draft_failed",
    "rejected",
}


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "adscout.db"
    upgrade(path)
    connection = connect(path)
    yield connection
    connection.close()


def synthetic() -> SegmentFiles:
    return SegmentFiles.load(FIXTURES, SYNTHETIC)


def rows(connection: sqlite3.Connection, sql: str, *params: object) -> list[sqlite3.Row]:
    return connection.execute(sql, params).fetchall()


def outcomes(connection: sqlite3.Connection, run_id: str) -> list[tuple[str, str, str | None]]:
    return [
        (row["domain"], row["step"], row["reason"] or row["flag"] or row["outcome"])
        for row in rows(
            connection,
            "SELECT c.domain, o.step, o.outcome, o.reason, o.flag FROM lead_step_outcomes AS o "
            "JOIN leads AS l ON l.lead_id = o.lead_id "
            "JOIN companies AS c ON c.company_id = l.company_id "
            "WHERE o.run_id = ? ORDER BY o.outcome_id",
            run_id,
        )
    ]


def person_edit(connection: sqlite3.Connection, domain: str, field: str, value: str) -> None:
    """A salesperson creates or edits the account in the fake CRM by hand."""
    connection.execute(
        "INSERT OR IGNORE INTO fake_crm_accounts (domain, created_by, created_at) "
        "VALUES (?, 'person', ?)",
        (domain, utc_now()),
    )
    account = connection.execute(
        "SELECT crm_account_id FROM fake_crm_accounts WHERE domain = ?", (domain,)
    ).fetchone()[0]
    connection.execute(
        "INSERT OR REPLACE INTO fake_crm_account_fields VALUES (?, ?, ?, 'person', ?)",
        (account, field, value, utc_now()),
    )


def test_pipeline_run_ends_with_drafts_waiting_for_approval(db: sqlite3.Connection) -> None:
    run_id = run_pipeline(db, synthetic())
    run = rows(db, "SELECT * FROM runs WHERE run_id = ?", run_id)[0]
    assert run["status"] == "succeeded" and run["kind"] == "pipeline"
    assert run["source"] == "fixture"
    drafts = rows(db, "SELECT status FROM drafts WHERE status = 'pending_approval'")
    assert len(drafts) == 4  # alpha, foxtrot, golf, hotel
    assert rows(db, "SELECT * FROM approvals") == []
    steps = [row["step"] for row in rows(db, "SELECT step FROM step_runs ORDER BY seq")]
    assert steps == ["source", "enrich", "rules", "score", "research", "draft"]


def test_duplicate_seed_row_creates_one_lead(db: sqlite3.Connection) -> None:
    run_id = run_pipeline(db, synthetic())
    assert ("alpha.test", "source", "duplicate") in outcomes(db, run_id)
    leads = rows(
        db,
        "SELECT count(*) FROM leads JOIN companies USING (company_id) WHERE domain = 'alpha.test'",
    )
    assert leads[0][0] == 1


def test_excluded_domain_exits_at_source_only(db: sqlite3.Connection) -> None:
    run_id = run_pipeline(db, synthetic())
    excluded = [o for o in outcomes(db, run_id) if o[0] == "excluded.test"]
    assert excluded == [("excluded.test", "source", "excluded")]


def test_second_run_records_existing_leads_as_duplicates(db: sqlite3.Connection) -> None:
    run_pipeline(db, synthetic())
    second = run_pipeline(db, synthetic())
    source = [o for o in outcomes(db, second) if o[1] == "source"]
    assert {reason for _, _, reason in source} == {"duplicate"}
    assert db.execute("SELECT count(*) FROM leads").fetchone()[0] == 9


def test_company_already_in_the_crm_exits_as_duplicate(db: sqlite3.Connection) -> None:
    person_edit(db, "alpha.test", "name", "Alpha Gear Inc.")
    run_id = run_pipeline(db, synthetic())
    first = next(o for o in outcomes(db, run_id) if o[0] == "alpha.test")
    assert first == ("alpha.test", "source", "duplicate")


def test_leads_get_their_source_fields_at_creation(db: sqlite3.Connection) -> None:
    run_id = run_pipeline(db, synthetic())
    for lead in rows(db, "SELECT * FROM leads"):
        assert lead["prompt_version"] == "none"
        assert re.fullmatch(r"\d+\.\d+\.\d+\+g[0-9a-f]{12}(\.dirty)?", lead["agent_version"])
        assert lead["source"].startswith(f"seed_list:{SYNTHETIC}@")
        assert lead["created_run_id"] == run_id


def test_stub_rows_are_labelled_and_state_no_facts(db: sqlite3.Connection) -> None:
    run_pipeline(db, synthetic())
    for table in ("enrichments", "scores", "briefs", "drafts"):
        kinds = {row[0] for row in rows(db, f"SELECT implementation FROM {table}")}  # noqa: S608
        assert kinds == {"stub"}, table
    assert {row[0] for row in rows(db, "SELECT claims_json FROM briefs")} == {"[]"}
    assert {row[0] for row in rows(db, "SELECT fields_json FROM enrichments")} == {"{}"}
    for row in rows(db, "SELECT detail, implementation FROM lead_step_outcomes"):
        if row["implementation"] == "stub":
            assert row["detail"].startswith("stub: scripted")


def test_stub_steps_have_explained_nulls(db: sqlite3.Connection) -> None:
    run_pipeline(db, synthetic())
    for step in rows(db, "SELECT * FROM step_runs"):
        assert step["model"] is None and step["input_tokens"] is None
        assert step["output_tokens"] is None and step["cost_usd"] is None
        reasons = json.loads(step["null_reasons_json"])
        assert set(reasons) == {"model", "input_tokens", "output_tokens", "cost_usd"}


def test_run_records_the_system_version(db: sqlite3.Connection) -> None:
    run_id = run_pipeline(db, synthetic())
    run = rows(db, "SELECT * FROM runs WHERE run_id = ?", run_id)[0]
    assert len(run["code_revision"]) == 40 and len(run["lock_digest"]) == 64
    assert run["prompt_version"] == "none" and run["schema_version"] == 1
    for name in ("icp_config_hash", "seed_list_hash", "stub_script_hash"):
        snapshot = rows(db, "SELECT kind FROM config_snapshots WHERE content_hash = ?", run[name])
        assert len(snapshot) == 1, name
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", run["started_at"])


def test_every_exit_reason_and_flag_is_exercised(db: sqlite3.Connection) -> None:
    files = synthetic()
    run_ids = [run_pipeline(db, files), run_stub_approval(db, files)]
    person_edit(db, "hotel.test", "name", "Hotel Gear (edited by sales)")
    run_ids.append(run_crm_sync(db, files.segment))
    seen = {reason for run_id in run_ids for _, _, reason in outcomes(db, run_id)}
    assert seen >= EXIT_REASONS | {"research_partial", "crm_conflict"}


def test_failed_run_keeps_its_rows(db: sqlite3.Connection, tmp_path: Path) -> None:
    config = tmp_path / "config"
    shutil.copytree(FIXTURES, config)
    script = config / "stubs" / f"{SYNTHETIC}.yaml"
    script.write_text(
        script.read_text("utf-8").replace(
            'schema_version: "1"', 'schema_version: "1"\nfail_at_step: score'
        ),
        "utf-8",
    )
    with pytest.raises(RunFailed) as caught:
        run_pipeline(db, SegmentFiles.load(config, SYNTHETIC))
    run = rows(db, "SELECT * FROM runs WHERE run_id = ?", caught.value.run_id)[0]
    assert run["status"] == "failed" and run["error_category"] == "step_error"
    steps = {row["step"]: row["status"] for row in rows(db, "SELECT step, status FROM step_runs")}
    assert steps == {
        "source": "succeeded",
        "enrich": "succeeded",
        "rules": "succeeded",
        "score": "failed",
    }
    assert db.execute("SELECT count(*) FROM leads").fetchone()[0] == 9
    assert db.execute("SELECT count(*) FROM enrichments").fetchone()[0] > 0


def test_dead_running_run_is_marked_interrupted(db: sqlite3.Connection) -> None:
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    assert not process_alive(finished.pid)
    first = run_pipeline(db, synthetic())
    db.execute(
        "UPDATE runs SET status = 'running', ended_at = NULL, pid = ? WHERE run_id = ?",
        (finished.pid, first),
    )
    second = run_pipeline(db, synthetic())
    old = rows(db, "SELECT status, error_category FROM runs WHERE run_id = ?", first)[0]
    assert (old["status"], old["error_category"]) == ("interrupted", "interrupted")
    assert rows(db, "SELECT status FROM runs WHERE run_id = ?", second)[0][0] == "succeeded"
    assert db.execute("SELECT count(*) FROM step_runs WHERE run_id = ?", (first,)).fetchone()[0]


def test_concurrent_run_is_refused_without_writing(db: sqlite3.Connection) -> None:
    first = run_pipeline(db, synthetic())
    db.execute("UPDATE runs SET status = 'running', ended_at = NULL WHERE run_id = ?", (first,))
    counts = [
        db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: S608
        for t in ("runs", "leads", "step_runs")
    ]
    with pytest.raises(RunInProgress, match="still running"):
        run_pipeline(db, synthetic())
    assert counts == [
        db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: S608
        for t in ("runs", "leads", "step_runs")
    ]


def test_stub_approval_is_labelled_and_bound_to_the_draft(db: sqlite3.Connection) -> None:
    files = synthetic()
    run_pipeline(db, files)
    run_stub_approval(db, files)
    approvals = rows(
        db,
        "SELECT a.*, d.body_sha256, d.status FROM approvals AS a JOIN drafts AS d USING (draft_id)",
    )
    assert len(approvals) == 4
    for approval in approvals:
        assert approval["approver_kind"] == "stub"
        assert approval["draft_sha256"] == approval["body_sha256"]
        assert approval["status"] == approval["decision"]
    decisions = {row["decision"] for row in approvals}
    assert decisions == {"approved", "rejected"}


def test_changed_draft_is_not_synced(db: sqlite3.Connection) -> None:
    files = synthetic()
    run_pipeline(db, files)
    run_stub_approval(db, files)
    db.execute(
        "UPDATE drafts SET body = body || ' (edited)' WHERE lead_id = "
        "(SELECT lead_id FROM leads JOIN companies USING (company_id) "
        "WHERE domain = 'alpha.test')"
    )
    run_id = run_crm_sync(db, files.segment)
    synced = {domain for domain, _, _ in outcomes(db, run_id)}
    assert "alpha.test" not in synced and "foxtrot.test" in synced


def test_only_approved_leads_reach_the_crm(db: sqlite3.Connection) -> None:
    files = synthetic()
    run_pipeline(db, files)
    run_stub_approval(db, files)
    run_crm_sync(db, files.segment)
    domains = {row[0] for row in rows(db, "SELECT domain FROM fake_crm_accounts")}
    assert domains == {"alpha.test", "foxtrot.test", "hotel.test"}


def test_person_edited_field_is_kept_and_logged(db: sqlite3.Connection) -> None:
    files = synthetic()
    run_pipeline(db, files)
    run_stub_approval(db, files)
    person_edit(db, "hotel.test", "name", "Hotel Gear (edited by sales)")
    run_id = run_crm_sync(db, files.segment)
    value = rows(
        db,
        "SELECT f.value, f.owner FROM fake_crm_account_fields AS f JOIN "
        "fake_crm_accounts AS a USING (crm_account_id) "
        "WHERE a.domain = 'hotel.test' AND f.field = 'name'",
    )[0]
    assert (value["value"], value["owner"]) == ("Hotel Gear (edited by sales)", "person")
    write = rows(db, "SELECT * FROM crm_writes WHERE domain = 'hotel.test'")[0]
    assert json.loads(write["fields_skipped_json"]) == ["name"]
    assert write["operation"] == "update" and write["target"] == "local_fake"
    assert ("hotel.test", "crm_sync", "crm_conflict") in outcomes(db, run_id)


def test_second_sync_is_idempotent(db: sqlite3.Connection) -> None:
    files = synthetic()
    run_pipeline(db, files)
    run_stub_approval(db, files)
    run_crm_sync(db, files.segment)
    second = run_crm_sync(db, files.segment)
    assert db.execute("SELECT count(*) FROM fake_crm_accounts").fetchone()[0] == 3
    operations = {
        row[0] for row in rows(db, "SELECT operation FROM crm_writes WHERE run_id = ?", second)
    }
    assert operations == {"no_op"}


def test_writer_refuses_fields_adscout_does_not_own(db: sqlite3.Connection) -> None:
    with pytest.raises(CrmWriteRefused, match="deal_stage"):
        write_account(
            db,
            run_id="r",
            lead_id="l",
            approval_id="a",
            domain="x.test",
            fields={"deal_stage": "won"},
        )


def test_no_other_module_writes_crm_tables() -> None:
    writes = re.compile(
        r"(INSERT|UPDATE|DELETE|REPLACE)[^;]*\b(fake_crm_\w+|crm_writes)\b",
        re.IGNORECASE | re.DOTALL,
    )
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "src" / "adscout").rglob("*.py")
        if path.name != "writer.py" and writes.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_real_seeds_follow_the_desk_research_script(db: sqlite3.Connection) -> None:
    files = SegmentFiles.load(CONFIG, REAL)
    run_ids = [run_pipeline(db, files), run_stub_approval(db, files)]
    run_ids.append(run_crm_sync(db, files.segment))
    final = {
        domain: (step, reason)
        for run_id in run_ids
        for domain, step, reason in outcomes(db, run_id)
    }
    assert final == {
        "8bitdo.com": ("score", "below_threshold"),
        "corsair.com": ("crm_sync", "kept"),
        "nzxt.com": ("approve", "rejected"),
        "razer.com": ("crm_sync", "kept"),
        "turtlebeach.com": ("crm_sync", "kept"),
    }
    assert rows(db, "SELECT DISTINCT source FROM runs")[0][0] == "stub"
    for row in rows(db, "SELECT detail FROM lead_step_outcomes WHERE implementation = 'stub'"):
        assert "not a pipeline assessment" in row["detail"]


def test_real_seed_without_a_source_is_refused(tmp_path: Path) -> None:
    script = tmp_path / f"{REAL}.yaml"
    text = (CONFIG / "stubs" / f"{REAL}.yaml").read_text("utf-8")
    start = text.index("  corsair.com:")
    end = text.index("  nzxt.com:")
    script.write_text(
        text[:start] + "  corsair.com: {expected: synced, approval: approved}\n" + text[end:],
        "utf-8",
    )
    with pytest.raises(ConfigError, match=r"corsair\.com: a real company"):
        load_stub_script(script)


def test_seed_missing_from_the_stub_script_fails_the_run(
    db: sqlite3.Connection, tmp_path: Path
) -> None:
    config = tmp_path / "config"
    shutil.copytree(FIXTURES, config)
    seeds = config / "seeds" / f"{SYNTHETIC}.csv"
    seeds.write_text(seeds.read_text("utf-8") + "India Gear,india.test,t,t,2026-10-18,\n", "utf-8")
    with pytest.raises(RunFailed, match=r"no entry for india\.test"):
        run_pipeline(db, SegmentFiles.load(config, SYNTHETIC))


def test_unmigrated_database_is_refused(tmp_path: Path) -> None:
    connection = connect(tmp_path / "empty.db")
    with pytest.raises(DatabaseNotReady, match="db upgrade"):
        run_pipeline(connection, synthetic())
    connection.close()


def test_commands_run_the_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = str(tmp_path / "cli.db")
    common = ["--segment", SYNTHETIC, "--config-dir", str(FIXTURES), "--db", path]
    assert cli.main(["run", *common]) == 1  # no database yet
    assert "db upgrade" in capsys.readouterr().err
    assert cli.main(["db", "upgrade", "--db", path]) == 0
    assert cli.main(["run", *common]) == 0
    assert cli.main(["approve", *common]) == 1  # --stub is required in Phase 1
    assert cli.main(["approve", "--stub", *common]) == 0
    assert cli.main(["sync", *common]) == 0
    out = capsys.readouterr().out
    assert "pipeline run" in out and "approval run" in out and "CRM sync run" in out


def test_command_reports_a_config_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "--segment", "no-such-segment"]) == 1
    assert "adscout run:" in capsys.readouterr().err


def test_no_command_deletes_or_resets_data() -> None:
    parser = cli.build_parser()
    names: set[str] = set()
    stack = [parser]
    while stack:
        current = stack.pop()
        for action in current._actions:
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                names.update(choices)
                stack.extend(choices.values())
    assert names >= {"db", "upgrade", "run", "approve", "sync"}
    assert not names & {"reset", "drop", "delete", "clean", "purge"}
