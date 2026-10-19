"""Apply numbered SQL migrations, back up first, and dump the schema snapshot.

Each `migrations/NNNN_name.sql` runs once, in one transaction, and is recorded with its
SHA-256. An applied migration whose file has changed stops the upgrade before anything runs.
"""

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from adscout.db.connection import connect, transaction, utc_now

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
SNAPSHOT = Path(__file__).resolve().parent / "schema.sql"
NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")

CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    applied_at TEXT NOT NULL
) STRICT
"""


class MigrationError(RuntimeError):
    """The database and the migration files disagree; nothing was changed."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    sha256: str


def migrations(folder: Path = MIGRATIONS) -> list[Migration]:
    found = []
    for path in sorted(folder.glob("*.sql")):
        match = NAME.match(path.name)
        if not match:
            raise MigrationError(f"{path.name}: migration names look like 0001_name.sql")
        data = path.read_bytes()
        found.append(
            Migration(
                version=int(match.group(1)),
                name=path.stem,
                sql=data.decode("utf-8"),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )
    versions = [migration.version for migration in found]
    if versions != list(range(1, len(found) + 1)):
        raise MigrationError(f"migration numbers must run 1, 2, 3… without gaps: {versions}")
    return found


def applied(connection: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if not exists:
        return {}
    rows = connection.execute("SELECT version, name, sha256 FROM schema_migrations").fetchall()
    return {row["version"]: row for row in rows}


def pending(connection: sqlite3.Connection, folder: Path = MIGRATIONS) -> list[Migration]:
    """Migrations not yet applied; fails if an applied one was edited or is missing."""
    available = {migration.version: migration for migration in migrations(folder)}
    done = applied(connection)
    for version, row in sorted(done.items()):
        migration = available.get(version)
        if migration is None:
            raise MigrationError(f"applied migration {row['name']} has no file")
        if migration.sha256 != row["sha256"]:
            raise MigrationError(f"applied migration {row['name']} was edited after it ran")
    return [migration for version, migration in sorted(available.items()) if version not in done]


def schema_version(connection: sqlite3.Connection) -> int:
    return max(applied(connection), default=0)


def backup(connection: sqlite3.Connection, path: Path, before: Migration) -> Path:
    folder = path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().replace(":", "").replace("-", "").replace(".", "")
    target = folder / f"{path.stem}-{stamp}-before-{before.name}.db"
    with sqlite3.connect(target) as copy:
        connection.backup(copy)
    copy.close()
    return target


def upgrade(path: Path, folder: Path = MIGRATIONS) -> list[str]:
    """Apply every pending migration in order; returns the names applied."""
    existed = path.exists() and path.stat().st_size > 0
    connection = connect(path)
    try:
        todo = pending(connection, folder)
        if not todo:
            return []
        if existed and applied(connection):
            backup(connection, path, todo[0])
        connection.execute(CREATE_MIGRATIONS_TABLE)
        # SQLite's table-rebuild procedure: foreign keys off (outside any transaction), then
        # a foreign-key check inside each migration's transaction before it commits.
        connection.execute("PRAGMA foreign_keys = OFF")
        for migration in todo:
            with transaction(connection):
                connection.executescript(migration.sql)
                broken = connection.execute("PRAGMA foreign_key_check").fetchall()
                if broken:
                    first = broken[0]
                    raise MigrationError(
                        f"{migration.name} leaves {len(broken)} broken foreign key(s), "
                        f"first in {first['table']} row {first['rowid']} → {first['parent']}"
                    )
                connection.execute(
                    "INSERT INTO schema_migrations (version, name, sha256, applied_at) "
                    "VALUES (?, ?, ?, ?)",
                    (migration.version, migration.name, migration.sha256, utc_now()),
                )
        return [migration.name for migration in todo]
    finally:
        connection.close()


def dump_schema(connection: sqlite3.Connection) -> str:
    """Tables, indexes, triggers and views, in a stable order, as the snapshot holds them."""
    rows = connection.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
        "ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 "
        "WHEN 'trigger' THEN 2 ELSE 3 END, name"
    ).fetchall()
    header = "-- Generated from a freshly migrated database; do not edit by hand.\n"
    header += "-- Regenerate: uv run python -m adscout.db.snapshot\n\n"
    return header + "".join(f"{row['sql'].strip()};\n\n" for row in rows).rstrip("\n") + "\n"
