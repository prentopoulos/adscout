"""The committed schema snapshot: `uv run python -m adscout.db.snapshot` rewrites it."""

import sys
import tempfile
from pathlib import Path

from adscout.db.connection import connect
from adscout.db.migrate import SNAPSHOT, dump_schema, upgrade


def fresh_schema() -> str:
    """The schema of a database built from nothing by the current migrations."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "fresh.db"
        upgrade(path)
        connection = connect(path)
        try:
            return dump_schema(connection)
        finally:
            connection.close()


def main(argv: list[str]) -> int:
    if argv:
        print("usage: python -m adscout.db.snapshot")
        return 2
    SNAPSHOT.write_text(fresh_schema(), encoding="utf-8", newline="\n")
    print(f"wrote {SNAPSHOT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
