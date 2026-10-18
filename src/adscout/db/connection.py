"""Open the pipeline database with the settings every connection needs."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_DB = Path("data") / "adscout.db"
DB_ENV = "ADSCOUT_DB"


def resolve_db_path(argument: str | Path | None = None) -> Path:
    """`--db` if given, else `ADSCOUT_DB`, else `data/adscout.db`."""
    if argument:
        return Path(argument)
    return Path(os.environ.get(DB_ENV) or DEFAULT_DB)


def connect(path: Path) -> sqlite3.Connection:
    """Foreign keys on and WAL journal mode, with transactions opened explicitly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, autocommit=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One write transaction, taken immediately so concurrent writers wait, not deadlock."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


def utc_now() -> str:
    """UTC RFC 3339 with milliseconds and a Z, the format of every stored timestamp."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
