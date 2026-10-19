"""Reproducible offline MVP: real pipeline code, synthetic sites, scripted model answers."""

import argparse
from pathlib import Path

from adscout.check import check_run
from adscout.config import load_seeds, load_segment
from adscout.db.connection import connect
from adscout.db.migrate import upgrade
from adscout.ids import ROOT
from adscout.pipeline.models import ModelChoice
from adscout.pipeline.real import RunSettings, run_real_pipeline
from adscout.web import serve

FIXTURES = ROOT / "tests" / "fixtures"
SEGMENT = "synthetic-demo"


def prepare(path: Path) -> str:
    """Create or resume a demo. Existing human decisions and failed runs are preserved."""
    upgrade(path)
    connection = connect(path)
    try:
        previous = connection.execute(
            "SELECT run_id FROM runs WHERE segment_id=? AND kind='pipeline' "
            "AND status='succeeded' ORDER BY rowid DESC LIMIT 1",
            (SEGMENT,),
        ).fetchone()
        if previous:
            return str(previous[0])
        config = FIXTURES / "config"
        run_id = run_real_pipeline(
            connection,
            load_segment(config / "segments" / f"{SEGMENT}.yaml"),
            load_seeds(config / "seeds" / f"{SEGMENT}.csv", SEGMENT),
            RunSettings(
                models=ModelChoice(scripted=FIXTURES / "models" / f"{SEGMENT}.yaml"),
                fixture_sites=FIXTURES / "sites",
                media_kit=config / "media-kit" / "fixture-publisher.yaml",
            ),
        )
        result = check_run(connection, run_id)
        if result.outcome != "pass":
            raise ValueError(f"Demo failed its independent check: {result.detail}")
        return run_id
    finally:
        connection.close()


def command(args: argparse.Namespace) -> int:
    path = Path(args.db or "data/demo.db")
    run_id = prepare(path)
    print(f"Offline demo ready: {run_id}. Synthetic companies; scripted model responses.")
    if not args.prepare:
        serve(path, FIXTURES / "config", SEGMENT, args.port)
    return 0
