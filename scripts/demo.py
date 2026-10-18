"""Run the Phase 1 flow end to end on one database and print each run's funnel.

    uv run --locked python scripts/demo.py --segment gaming-hardware-na --db data/demo.db

It upgrades the database, runs the pipeline, the stub approver and the CRM sync, checks each
run independently and prints its funnel. Everything is offline: the steps are scripted stubs
and the CRM is the local fake.
"""

import argparse
import sys
from pathlib import Path

from adscout.check import check_run
from adscout.db.connection import connect, resolve_db_path
from adscout.db.migrate import upgrade
from adscout.pipeline.run import SegmentFiles, run_crm_sync, run_pipeline, run_stub_approval
from adscout.report import funnel


def demo(segment_id: str, config_dir: Path, db: Path) -> list[str]:
    """Run upgrade, pipeline, approval and sync; check each run; return the run IDs."""
    upgrade(db)
    files = SegmentFiles.load(config_dir, segment_id)
    connection = connect(db)
    try:
        run_ids = [
            run_pipeline(connection, files),
            run_stub_approval(connection, files),
            run_crm_sync(connection, files.segment),
        ]
        for run_id in run_ids:
            result = check_run(connection, run_id)
            print(funnel(connection, run_id))
            for problem in result.problems:
                print(f"  check: {problem}")
            print()
        return run_ids
    finally:
        connection.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--segment", default="gaming-hardware-na")
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--db", help="database file (default: $ADSCOUT_DB, else data/adscout.db)")
    args = parser.parse_args(argv)
    db = resolve_db_path(args.db)
    run_ids = demo(args.segment, args.config_dir, db)
    connection = connect(db)
    try:
        outcomes = [
            connection.execute(
                "SELECT validation_outcome FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            for run_id in run_ids
        ]
    finally:
        connection.close()
    print("runs: " + ", ".join(run_ids))
    return 0 if set(outcomes) == {"pass"} else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
