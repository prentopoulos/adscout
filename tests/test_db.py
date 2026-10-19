"""The local database: migrations, the schema snapshot, lead identity and the schema guards."""

import shutil
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from adscout import cli
from adscout.db.connection import connect, resolve_db_path, transaction
from adscout.db.connection import connect as open_database
from adscout.db.guards import contact_columns, tables
from adscout.db.migrate import (
    MIGRATIONS,
    SNAPSHOT,
    MigrationError,
    dump_schema,
    migrations,
    schema_version,
    upgrade,
)
from adscout.db.snapshot import fresh_schema
from adscout.ids import agent_version, code_version, uuid7
from conftest import run_git

LEAD_ID = "0192f0c1-0000-7000-8000-000000000001"
PHASE_1_ROWS = Path(__file__).resolve().parent / "fixtures" / "phase-1-rows.sql"
# The number of the next migration a test plants in a copy of the migrations folder.
NEXT = f"{len(migrations()) + 1:04d}"


@pytest.fixture(autouse=True)
def close_connections(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Close every connection a test opens through `connect`."""
    opened: list[sqlite3.Connection] = []

    def tracking(path: Path) -> sqlite3.Connection:
        connection = open_database(path)
        opened.append(connection)
        return connection

    monkeypatch.setitem(globals(), "connect", tracking)
    yield
    for connection in opened:
        connection.close()


def migrated(tmp_path: Path) -> sqlite3.Connection:
    path = tmp_path / "adscout.db"
    upgrade(path)
    return connect(path)


def insert_run(connection: sqlite3.Connection, run_id: str = "20261018T000000Z-aaaaaa") -> str:
    connection.execute(
        "INSERT INTO runs (run_id, kind, segment_id, status, started_at, source, code_revision, "
        "code_dirty, lock_digest, package_version, agent_version, prompt_version, "
        "python_version, platform, schema_version, budgets_json, null_reasons_json, pid, host) "
        "VALUES (?, 'pipeline', 'test-segment', 'running', '2026-10-18T00:00:00.000Z', 'stub', "
        "'abc', 0, 'x', '0.1.0', '0.1.0+gabc', 'none', '3.13', 'test', 1, '{}', '{}', 1, 'h')",
        (run_id,),
    )
    return run_id


def insert_lead(connection: sqlite3.Connection) -> str:
    run_id = insert_run(connection)
    connection.execute(
        "INSERT INTO companies (company_id, domain, name, created_run_id, created_at) "
        "VALUES (1, 'example.test', 'Example', ?, '2026-10-18T00:00:00.000Z')",
        (run_id,),
    )
    connection.execute(
        "INSERT INTO leads VALUES (?, 'test-segment', 1, 'seed_list:test', 'none', "
        "'0.1.0+gabc', ?, '2026-10-18T00:00:00.000Z')",
        (LEAD_ID, run_id),
    )
    return LEAD_ID


def copy_migrations(tmp_path: Path) -> Path:
    folder = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS, folder)
    return folder


def test_fresh_database_applies_and_records_every_migration(tmp_path: Path) -> None:
    path = tmp_path / "new" / "adscout.db"
    assert upgrade(path) == ["0001_initial", "0002_ai_pipeline"]
    connection = connect(path)
    rows = connection.execute("SELECT version, name FROM schema_migrations").fetchall()
    assert [(row["version"], row["name"]) for row in rows] == [
        (1, "0001_initial"),
        (2, "0002_ai_pipeline"),
    ]
    assert schema_version(connection) == 2


def test_upgrade_twice_is_a_no_op_without_backup(tmp_path: Path) -> None:
    path = tmp_path / "adscout.db"
    upgrade(path)
    assert upgrade(path) == []
    assert not (tmp_path / "backups").exists()


def test_upgrade_backs_up_before_a_new_migration(tmp_path: Path) -> None:
    folder = copy_migrations(tmp_path)
    path = tmp_path / "adscout.db"
    upgrade(path, folder)
    (folder / f"{NEXT}_note.sql").write_text("CREATE TABLE notes (x TEXT) STRICT;\n", "utf-8")
    assert upgrade(path, folder) == [f"{NEXT}_note"]
    backups = list((tmp_path / "backups").glob("*.db"))
    assert len(backups) == 1 and f"before-{NEXT}_note" in backups[0].name
    copy = sqlite3.connect(backups[0])
    assert "notes" not in tables(copy)
    copy.close()


def test_edited_migration_stops_the_upgrade(tmp_path: Path) -> None:
    folder = copy_migrations(tmp_path)
    path = tmp_path / "adscout.db"
    upgrade(path, folder)
    before = dump_schema(connect(path))
    sql = folder / "0001_initial.sql"
    sql.write_text(sql.read_text("utf-8") + "\n-- edited\n", "utf-8")
    (folder / f"{NEXT}_note.sql").write_text("CREATE TABLE notes (x TEXT) STRICT;\n", "utf-8")
    with pytest.raises(MigrationError, match="0001_initial was edited"):
        upgrade(path, folder)
    assert dump_schema(connect(path)) == before


def test_gap_in_migration_numbers_is_refused(tmp_path: Path) -> None:
    folder = copy_migrations(tmp_path)
    (folder / f"{int(NEXT) + 1:04d}_skip.sql").write_text("SELECT 1;\n", "utf-8")
    with pytest.raises(MigrationError, match="without gaps"):
        upgrade(tmp_path / "adscout.db", folder)


def test_fresh_migration_matches_the_committed_snapshot() -> None:
    assert SNAPSHOT.read_text(encoding="utf-8") == fresh_schema(), (
        "schema.sql is stale; run `uv run python -m adscout.db.snapshot`"
    )


def test_snapshot_catches_a_table_rebuild_that_drops_triggers(tmp_path: Path) -> None:
    folder = copy_migrations(tmp_path)
    # The usual SQLite rebuild: copy, drop, rename. Dropping the table silently drops its
    # triggers, and this migration forgets to recreate them.
    (folder / f"{NEXT}_rebuild_claims.sql").write_text(
        "CREATE TABLE claims_new AS SELECT * FROM claims;\n"
        "DROP TABLE claims;\n"
        "ALTER TABLE claims_new RENAME TO claims;\n",
        "utf-8",
    )
    path = tmp_path / "adscout.db"
    upgrade(path, folder)
    rebuilt = dump_schema(connect(path))
    assert "claims_never_deleted" not in rebuilt
    assert rebuilt != SNAPSHOT.read_text(encoding="utf-8")


def test_triggers_present_after_migration(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    names = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
    }
    assert names == {
        "leads_never_deleted",
        "leads_source_fields_immutable",
        "model_calls_append_only",
        "model_calls_never_deleted",
        "source_calls_append_only",
        "source_calls_never_deleted",
        "claims_append_only",
        "claims_never_deleted",
    }


def test_every_table_is_strict_and_wal_is_on(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    loose = [
        row["name"]
        for row in connection.execute("PRAGMA table_list").fetchall()
        if row["schema"] == "main"
        and row["type"] == "table"
        and not row["strict"]
        and not row["name"].startswith("sqlite_")
    ]
    assert loose == []


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    run_id = insert_run(connection)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        connection.execute(
            "INSERT INTO leads VALUES (?, 's', 999, 'x', 'none', 'v', ?, 't')", (LEAD_ID, run_id)
        )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE leads SET source = 'edited'",
        "UPDATE leads SET agent_version = '9.9.9'",
        "UPDATE leads SET prompt_version = 'v2'",
    ],
)
def test_immutable_lead_fields_refuse_updates(tmp_path: Path, statement: str) -> None:
    connection = migrated(tmp_path)
    insert_lead(connection)
    before = tuple(connection.execute("SELECT * FROM leads").fetchone())
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(statement)
    assert tuple(connection.execute("SELECT * FROM leads").fetchone()) == before


def test_leads_are_never_deleted(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    insert_lead(connection)
    with pytest.raises(sqlite3.IntegrityError, match="never deleted"):
        connection.execute("DELETE FROM leads")
    assert connection.execute("SELECT count(*) FROM leads").fetchone()[0] == 1


def test_lead_is_unique_per_segment_and_company(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    insert_lead(connection)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        connection.execute(
            "INSERT INTO leads SELECT ?, segment_id, company_id, source, prompt_version, "
            "agent_version, created_run_id, created_at FROM leads",
            (str(uuid7()),),
        )


def test_unknown_exit_reason_is_refused(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    lead_id = insert_lead(connection)
    connection.execute(
        "INSERT INTO step_runs (run_id, step, seq, implementation, implementation_version, "
        "status, started_at, null_reasons_json) "
        "VALUES ('20261018T000000Z-aaaaaa', 'score', 4, 'stub', '1', 'running', 't', '{}')"
    )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        connection.execute(
            "INSERT INTO lead_step_outcomes (run_id, step, lead_id, outcome, reason, detail, "
            "implementation, started_at, ended_at) VALUES ('20261018T000000Z-aaaaaa', 'score', "
            "?, 'exited', 'bad_vibes', 'x', 'stub', 't', 't')",
            (lead_id,),
        )


def test_schema_has_no_personal_contact_columns(tmp_path: Path) -> None:
    assert contact_columns(migrated(tmp_path)) == []


def test_contact_column_guard_names_a_planted_column(tmp_path: Path) -> None:
    folder = copy_migrations(tmp_path)
    (folder / f"{NEXT}_contact.sql").write_text(
        "ALTER TABLE companies ADD COLUMN contact_email TEXT;\n", "utf-8"
    )
    path = tmp_path / "adscout.db"
    upgrade(path, folder)
    assert contact_columns(connect(path)) == ["companies.contact_email"]


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    with pytest.raises(RuntimeError), transaction(connection):
        insert_run(connection)
        raise RuntimeError("stop")
    assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_database_path_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADSCOUT_DB", raising=False)
    assert resolve_db_path(None) == Path("data") / "adscout.db"
    monkeypatch.setenv("ADSCOUT_DB", "elsewhere/x.db")
    assert resolve_db_path(None) == Path("elsewhere/x.db")
    assert resolve_db_path("given.db") == Path("given.db")


def test_db_upgrade_command_uses_the_environment_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "env.db"
    monkeypatch.setenv("ADSCOUT_DB", str(target))
    assert cli.main(["db", "upgrade"]) == 0
    assert "applied 0001_initial" in capsys.readouterr().out
    assert target.exists()
    assert cli.main(["db", "upgrade"]) == 0
    assert "up to date" in capsys.readouterr().out


def test_db_upgrade_command_reports_an_edited_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = copy_migrations(tmp_path)
    path = tmp_path / "adscout.db"
    upgrade(path, folder)
    sql = folder / "0001_initial.sql"
    sql.write_text(sql.read_text("utf-8") + "\n-- edited\n", "utf-8")
    monkeypatch.setattr("adscout.db.migrate.MIGRATIONS", folder)
    monkeypatch.setattr(cli, "upgrade", lambda target: upgrade(target, folder))
    assert cli.main(["db", "upgrade", "--db", str(path)]) == 1
    assert "was edited" in capsys.readouterr().err


def test_uuid7_is_version_7_and_time_ordered() -> None:
    ids = [uuid7() for _ in range(2000)]
    assert all(value.version == 7 and value.variant == uuid.RFC_4122 for value in ids)
    assert ids == sorted(ids)
    assert len({str(value) for value in ids}) == len(ids)


def test_agent_version_format() -> None:
    revision = "1a2b3c4d5e6f7a8b9c0d"
    assert agent_version(revision, False, "0.2.0") == "0.2.0+g1a2b3c4d5e6f"
    assert agent_version(revision, True, "0.2.0") == "0.2.0+g1a2b3c4d5e6f.dirty"


def test_code_version_sees_uncommitted_changes(git_repo: Path) -> None:
    (git_repo / "a.txt").write_text("a", encoding="utf-8")
    run_git(git_repo, "add", "a.txt")
    run_git(git_repo, "commit", "-q", "-m", "chore: a")
    revision, dirty = code_version(git_repo)
    assert len(revision) == 40 and not dirty
    (git_repo / "a.txt").write_text("b", encoding="utf-8")
    assert code_version(git_repo) == (revision, True)


# Migration 0002 (Phase 2 design, "Data model").

PHASE_1_TABLES = (
    "config_snapshots",
    "runs",
    "step_runs",
    "companies",
    "leads",
    "lead_step_outcomes",
    "enrichments",
    "scores",
    "briefs",
    "drafts",
    "approvals",
    "fake_crm_accounts",
    "fake_crm_account_fields",
    "crm_writes",
)
RUN_ID = "20261018T000000Z-aaaaaa"
SPAN = "0123456789abcdef"
TRACE = LEAD_ID.replace("-", "")


def table_rows(
    connection: sqlite3.Connection, columns: dict[str, list[str]]
) -> dict[str, list[tuple[object, ...]]]:
    return {
        table: [
            tuple(row)
            for row in connection.execute(
                f"SELECT {', '.join(names)} FROM {table} ORDER BY 1"  # noqa: S608
            )
        ]
        for table, names in columns.items()
    }


def test_upgrade_from_phase_1_keeps_every_row_and_trigger(tmp_path: Path) -> None:
    # The rows the merged Phase 1 code wrote for the synthetic fixtures, on its schema.
    phase_1 = tmp_path / "phase-1-migrations"
    phase_1.mkdir()
    shutil.copy(MIGRATIONS / "0001_initial.sql", phase_1)
    path = tmp_path / "adscout.db"
    upgrade(path, phase_1)
    connection = connect(path)
    connection.executescript(PHASE_1_ROWS.read_text(encoding="utf-8"))
    columns = {
        table: [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        for table in PHASE_1_TABLES
    }
    before = table_rows(connection, columns)
    connection.close()

    assert upgrade(path) == ["0002_ai_pipeline"]

    assert len(list((tmp_path / "backups").glob("*-before-0002_ai_pipeline.db"))) == 1
    connection = connect(path)
    assert schema_version(connection) == 2
    assert all(before[table] for table in ("runs", "leads", "drafts", "crm_writes"))
    assert table_rows(connection, columns) == before
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("UPDATE leads SET source = 'edited'")
    with pytest.raises(sqlite3.IntegrityError, match="never deleted"):
        connection.execute("DELETE FROM leads")
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_a_migration_that_breaks_a_foreign_key_is_refused(tmp_path: Path) -> None:
    folder = copy_migrations(tmp_path)
    path = tmp_path / "adscout.db"
    upgrade(path, folder)
    insert_lead(connect(path))
    before = dump_schema(connect(path))
    (folder / f"{NEXT}_orphan.sql").write_text("DELETE FROM companies;\n", "utf-8")
    with pytest.raises(MigrationError, match=f"{NEXT}_orphan leaves 1 broken foreign key"):
        upgrade(path, folder)
    connection = connect(path)
    assert dump_schema(connection) == before
    assert connection.execute("SELECT count(*) FROM companies").fetchone()[0] == 1
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def insert_step(connection: sqlite3.Connection, step: str = "research") -> None:
    connection.execute(
        "INSERT INTO step_runs (run_id, step, seq, implementation, implementation_version, "
        "status, started_at, null_reasons_json) VALUES (?, ?, 5, 'real', '1', 'running', 't', "
        "'{}')",
        (RUN_ID, step),
    )


def insert_model_call(connection: sqlite3.Connection, **overrides: object) -> None:
    values: dict[str, object] = {
        "call_id": str(uuid7()),
        "run_id": RUN_ID,
        "step": "research",
        "lead_id": LEAD_ID,
        "role": "research_worker",
        "agent_name": "worker_ads",
        "model": "claude-haiku-5-5",
        "effort": "low",
        "prompt_version": "p-0123456789ab",
        "call_role": "primary",
        "mode": "fake",
        "status": "succeeded",
        "request_sha256": "0" * 64,
        "cost_usd": 0.001,
        "reserved_usd": 0.01,
        "trace_id": TRACE,
        "span_id": uuid.uuid4().hex[:16],
        "parent_span_id": SPAN,
        "null_reasons_json": "{}",
        "started_at": "t",
        "ended_at": "t",
    } | overrides
    columns, marks = ", ".join(values), ", ".join("?" * len(values))
    connection.execute(
        f"INSERT INTO model_calls ({columns}) VALUES ({marks})",  # noqa: S608
        tuple(values.values()),
    )


def insert_brief(connection: sqlite3.Connection) -> int:
    cursor = connection.execute(
        "INSERT INTO briefs (lead_id, run_id, implementation, status, summary, claims_json, "
        "created_at, design, verifier_version) VALUES (?, ?, 'real', 'partial', '', '[]', 't', "
        "'multi', 'v1')",
        (LEAD_ID, RUN_ID),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def insert_claim(connection: sqlite3.Connection, brief_id: int, quote: str, key: str) -> None:
    connection.execute(
        "INSERT INTO claims (brief_id, claim_key, agent_name, topic, text, source_url, quote, "
        "url_fetched_in_run, quote_found, numbers_ok, verified, verifier_version, created_at) "
        "VALUES (?, ?, 'worker_ads', 'ad_activity', 'Runs ads.', 'https://example.test/a', ?, "
        "1, 0, 1, 0, 'v1', 't')",
        (brief_id, key, quote),
    )


def test_new_exit_reasons_flag_run_kinds_and_source_are_accepted(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    lead_id = insert_lead(connection)
    insert_step(connection, "score")
    for outcome, reason, flag in [
        ("exited", "near_miss", None),
        ("exited", "score_failed", None),
        ("exited", "research_failed", None),
        ("kept", None, "critic_unresolved"),
    ]:
        connection.execute(
            "INSERT INTO lead_step_outcomes (run_id, step, lead_id, outcome, reason, flag, "
            "detail, implementation, started_at, ended_at) "
            "VALUES (?, 'score', ?, ?, ?, ?, 'x', 'real', 't', 't')",
            (RUN_ID, lead_id, outcome, reason, flag),
        )
    for kind, source in [("rescore", "replay"), ("eval", "live")]:
        connection.execute(
            "UPDATE runs SET kind = ?, source = ? WHERE run_id = ?", (kind, source, RUN_ID)
        )
    assert connection.execute("SELECT count(*) FROM lead_step_outcomes").fetchone()[0] == 4


def test_claim_quote_longer_than_300_characters_is_refused(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    insert_lead(connection)
    brief_id = insert_brief(connection)
    insert_claim(connection, brief_id, "q" * 300, "D1")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        insert_claim(connection, brief_id, "q" * 301, "D2")


def test_model_calls_and_claims_are_append_only(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    insert_lead(connection)
    insert_step(connection)
    insert_model_call(connection)
    insert_claim(connection, insert_brief(connection), "a quote of twenty characters", "D1")
    for statement in [
        "UPDATE model_calls SET cost_usd = 0",
        "DELETE FROM model_calls",
        "UPDATE claims SET verified = 1",
        "DELETE FROM claims",
    ]:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(statement)


@pytest.mark.parametrize(
    "overrides",
    [
        {"mode": "replay", "cost_usd": 0.0},  # a replay keeps its original cost
        {"mode": "replay", "cost_usd": 0.5, "original_cost_usd": 0.5},  # and costs nothing
        {"mode": "live", "original_cost_usd": 0.5},  # only a replay has an original cost
        {"status": "refused"},  # a refused call names its error category
        {"call_role": "second_try"},
        {"prompt_version": "none"},
        {"span_id": "short"},
    ],
)
def test_model_call_rules(tmp_path: Path, overrides: dict[str, object]) -> None:
    connection = migrated(tmp_path)
    insert_lead(connection)
    insert_step(connection)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        insert_model_call(connection, **overrides)


def test_replay_and_refused_calls_are_recorded(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    insert_lead(connection)
    insert_step(connection)
    insert_model_call(connection, mode="replay", cost_usd=0.0, original_cost_usd=0.002)
    insert_model_call(connection, status="refused", error_category="budget_exhausted", cost_usd=0)
    assert connection.execute("SELECT count(*) FROM model_calls").fetchone()[0] == 2


def test_real_brief_needs_its_design_and_verifier_version(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    insert_lead(connection)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        connection.execute(
            "INSERT INTO briefs (lead_id, run_id, implementation, status, summary, claims_json, "
            "created_at) VALUES (?, ?, 'real', 'failed', '', '[]', 't')",
            (LEAD_ID, RUN_ID),
        )


def test_step_spans_are_roots_and_agent_spans_are_named(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    insert_lead(connection)
    insert_step(connection)

    def span(span_id: str, operation: str, parent: str | None, agent: str | None) -> None:
        connection.execute(
            "INSERT INTO spans (span_id, trace_id, parent_span_id, run_id, lead_id, step, "
            "operation, agent_name, status, detail, started_at, ended_at) "
            "VALUES (?, ?, ?, ?, ?, 'research', ?, ?, 'succeeded', '', 't', 't')",
            (span_id, TRACE, parent, RUN_ID, LEAD_ID, operation, agent),
        )

    span(SPAN, "step", None, None)
    span("1" * 16, "invoke_agent", SPAN, "worker_ads")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        span("2" * 16, "step", SPAN, None)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        span("3" * 16, "invoke_agent", SPAN, None)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        span("4" * 16, "step", None, None)
