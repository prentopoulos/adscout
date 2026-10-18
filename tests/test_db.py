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
    schema_version,
    upgrade,
)
from adscout.db.snapshot import fresh_schema
from adscout.ids import agent_version, code_version, uuid7
from conftest import run_git

LEAD_ID = "0192f0c1-0000-7000-8000-000000000001"


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
    assert upgrade(path) == ["0001_initial"]
    connection = connect(path)
    rows = connection.execute("SELECT version, name FROM schema_migrations").fetchall()
    assert [(row["version"], row["name"]) for row in rows] == [(1, "0001_initial")]
    assert schema_version(connection) == 1


def test_upgrade_twice_is_a_no_op_without_backup(tmp_path: Path) -> None:
    path = tmp_path / "adscout.db"
    upgrade(path)
    assert upgrade(path) == []
    assert not (tmp_path / "backups").exists()


def test_upgrade_backs_up_before_a_new_migration(tmp_path: Path) -> None:
    folder = copy_migrations(tmp_path)
    path = tmp_path / "adscout.db"
    upgrade(path, folder)
    (folder / "0002_note.sql").write_text("CREATE TABLE notes (x TEXT) STRICT;\n", "utf-8")
    assert upgrade(path, folder) == ["0002_note"]
    backups = list((tmp_path / "backups").glob("*.db"))
    assert len(backups) == 1 and "before-0002_note" in backups[0].name
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
    (folder / "0002_note.sql").write_text("CREATE TABLE notes (x TEXT) STRICT;\n", "utf-8")
    with pytest.raises(MigrationError, match="0001_initial was edited"):
        upgrade(path, folder)
    assert dump_schema(connect(path)) == before


def test_gap_in_migration_numbers_is_refused(tmp_path: Path) -> None:
    folder = copy_migrations(tmp_path)
    (folder / "0003_skip.sql").write_text("SELECT 1;\n", "utf-8")
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
    (folder / "0002_rebuild_leads.sql").write_text(
        "DROP VIEW v_lead_journey;\n"
        "CREATE TABLE leads_new AS SELECT * FROM leads;\n"
        "DROP TABLE leads;\n"
        "ALTER TABLE leads_new RENAME TO leads;\n",
        "utf-8",
    )
    path = tmp_path / "adscout.db"
    upgrade(path, folder)
    rebuilt = dump_schema(connect(path))
    assert "leads_never_deleted" not in rebuilt
    assert rebuilt != SNAPSHOT.read_text(encoding="utf-8")


def test_triggers_present_after_migration(tmp_path: Path) -> None:
    connection = migrated(tmp_path)
    names = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
    }
    assert names == {"leads_never_deleted", "leads_source_fields_immutable"}


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
    (folder / "0002_contact.sql").write_text(
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
