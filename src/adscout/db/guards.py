"""Schema guards that enforce PROJECT.md §5 rules on the database's shape."""

import re
import sqlite3

# Column names that would hold a real person's contact data (§5: synthetic contacts only).
CONTACT_COLUMN = re.compile(
    r"e_?mail|phone|first_?name|last_?name|full_?name|person|contact|linkedin", re.IGNORECASE
)
# The Phase 4 contacts table, whose CHECKs keep its data synthetic (Phase 1 design, decision 8).
CONTACT_TABLES = frozenset({"contacts"})


def tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def contact_columns(connection: sqlite3.Connection) -> list[str]:
    """`table.column` for every column outside a contacts table that looks like contact data."""
    found = []
    for table in tables(connection):
        if table in CONTACT_TABLES:
            continue
        for column in connection.execute(f"PRAGMA table_info({table})").fetchall():
            if CONTACT_COLUMN.search(column[1]):
                found.append(f"{table}.{column[1]}")
    return found
