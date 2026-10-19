"""Command-line entry point for AdScout."""

import argparse
import json
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

from adscout.check import check_run
from adscout.config import ConfigError, load_segment
from adscout.db.connection import connect, resolve_db_path
from adscout.db.migrate import MigrationError, upgrade
from adscout.export import ExportRefused, export_lines, write_export
from adscout.llm.adapter import LiveModeRefused
from adscout.llm.invoke import HAIKU, SONNET
from adscout.pipeline.models import ModelChoice, ModelsNotChosen
from adscout.pipeline.recorder import RunFailed, RunInProgress
from adscout.pipeline.rescore import run_rescore
from adscout.pipeline.run import (
    DatabaseNotReady,
    SegmentFiles,
    require_migrated,
    run_crm_sync,
    run_pipeline,
    run_stub_approval,
)
from adscout.report import funnel, list_runs

MODELS = {"haiku": HAIKU, "sonnet": SONNET}

Handler = Callable[[argparse.Namespace], int]
DEFAULT_CONFIG_DIR = Path("config")
# Failures a command reports in one line: bad config, a database that is missing, unmigrated
# or locked, another live run, a failed run, a missing file, or no Git checkout to version.
EXPECTED_ERRORS = (
    ConfigError,
    DatabaseNotReady,
    RunInProgress,
    RunFailed,
    ExportRefused,
    LookupError,
    OSError,
    sqlite3.Error,
    subprocess.CalledProcessError,
)


def fail(command: str, message: object) -> int:
    print(f"adscout {command}: {message}", file=sys.stderr)
    return 1


@contextmanager
def database(args: argparse.Namespace) -> Iterator[sqlite3.Connection]:
    """An existing, fully migrated database."""
    path = resolve_db_path(args.db)
    if not path.exists():
        raise DatabaseNotReady(f"{path} does not exist; run `adscout db upgrade` first")
    connection = connect(path)
    try:
        require_migrated(connection)
        yield connection
    finally:
        connection.close()


def db_upgrade(args: argparse.Namespace) -> int:
    path = resolve_db_path(args.db)
    try:
        names = upgrade(path)
    except (MigrationError, sqlite3.Error, OSError) as error:
        return fail("db upgrade", error)
    if names:
        print(f"{path}: applied {', '.join(names)}")
    else:
        print(f"{path}: up to date")
    return 0


def report(run_id: str, kind: str) -> int:
    print(f"{kind} run {run_id}: succeeded")
    return 0


def run(args: argparse.Namespace) -> int:
    try:
        files = SegmentFiles.load(args.config_dir, args.segment, args.seeds)
        with database(args) as connection:
            return report(run_pipeline(connection, files), "pipeline")
    except EXPECTED_ERRORS as error:
        return fail("run", error)


def approve(args: argparse.Namespace) -> int:
    if not args.stub:
        return fail("approve", "Phase 1 has only the stub approver; pass --stub")
    try:
        # An approval run reads stored drafts; it needs the stub script, not the seed list.
        files = SegmentFiles.load(args.config_dir, args.segment, with_seeds=False)
        with database(args) as connection:
            run_id = run_stub_approval(connection, files.segment, files.script)
            return report(run_id, "approval")
    except EXPECTED_ERRORS as error:
        return fail("approve", error)


def sync(args: argparse.Namespace) -> int:
    try:
        segment = load_segment(args.config_dir / "segments" / f"{args.segment}.yaml")
        with database(args) as connection:
            return report(run_crm_sync(connection, segment), "CRM sync")
    except EXPECTED_ERRORS as error:
        return fail("sync", error)


def runs(args: argparse.Namespace) -> int:
    try:
        with database(args) as connection:
            print(list_runs(connection, args.segment))
    except EXPECTED_ERRORS as error:
        return fail("runs", error)
    return 0


def show_funnel(args: argparse.Namespace) -> int:
    try:
        with database(args) as connection:
            print(funnel(connection, args.run_id))
    except EXPECTED_ERRORS as error:
        return fail("funnel", error)
    return 0


def check(args: argparse.Namespace) -> int:
    try:
        with database(args) as connection:
            result = check_run(connection, args.run_id)
    except EXPECTED_ERRORS as error:
        return fail("check", error)
    print(f"run {result.run_id}: {result.outcome}")
    for problem in result.problems:
        print(f"  {problem}")
    return 0 if result.outcome == "pass" else 1


def export(args: argparse.Namespace) -> int:
    try:
        with database(args) as connection:
            if args.out is None:
                for line in export_lines(connection, args.run_id):
                    print(json.dumps(line, ensure_ascii=False, sort_keys=True))
                return 0
            path = write_export(connection, args.run_id, args.out)
    except EXPECTED_ERRORS as error:
        return fail("export", error)
    print(f"wrote {path}")
    return 0


def rescore(args: argparse.Namespace) -> int:
    try:
        segment = load_segment(args.config_dir / "segments" / f"{args.segment}.yaml")
        choice = model_choice(args)
        with database(args) as connection:
            run_id = run_rescore(
                connection, segment, choice, model=MODELS[args.model], repeats=args.score_repeats
            )
    except (*EXPECTED_ERRORS, ModelsNotChosen, LiveModeRefused, ValueError) as error:
        return fail("rescore", error)
    print(f"rescore run {run_id} finished")
    return 0


def model_choice(args: argparse.Namespace) -> ModelChoice:
    cap = Decimal(args.max_spend_usd) if args.max_spend_usd is not None else None
    return ModelChoice(
        live=args.live,
        cap_usd=cap,
        replay_run_id=args.replay,
        scripted=args.fixture_models,
    )


def add_model_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--live", action="store_true", help="call the Anthropic API (paid)")
    parser.add_argument(
        "--max-spend-usd", help="this run's spend cap in US dollars; required with --live"
    )
    parser.add_argument("--replay", metavar="RUN_ID", help="replay a recorded live run at $0")
    parser.add_argument(
        "--fixture-models", type=Path, help="scripted model answers for synthetic fixtures"
    )


def add_db_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", help="database file (default: $ADSCOUT_DB, else data/adscout.db)")


def add_segment_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--segment", required=True, help="segment ID, e.g. gaming-hardware-na")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="folder holding segments/, seeds/ and stubs/ (default: config)",
    )
    add_db_option(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adscout",
        description="Advertiser prospecting and qualification agent (portfolio project).",
    )
    # The version comes from the installed package metadata, set once in pyproject.toml.
    parser.add_argument("--version", action="version", version=f"adscout {version('adscout')}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    db = commands.add_parser("db", help="manage the local database")
    db_commands = db.add_subparsers(dest="db_command", metavar="ACTION", required=True)
    db_up = db_commands.add_parser("upgrade", help="create the database or apply new migrations")
    add_db_option(db_up)
    db_up.set_defaults(handler=db_upgrade)

    run_parser = commands.add_parser(
        "run", help="source a segment's seeds and run every step up to drafts"
    )
    add_segment_options(run_parser)
    run_parser.add_argument("--seeds", type=Path, help="seed list CSV (default: the segment's)")
    run_parser.set_defaults(handler=run)

    approve_parser = commands.add_parser("approve", help="decide drafts waiting for approval")
    add_segment_options(approve_parser)
    approve_parser.add_argument(
        "--stub", action="store_true", help="use the scripted stub approver (Phase 1)"
    )
    approve_parser.set_defaults(handler=approve)

    sync_parser = commands.add_parser("sync", help="write approved leads to the CRM")
    add_segment_options(sync_parser)
    sync_parser.set_defaults(handler=sync)

    rescore_parser = commands.add_parser(
        "rescore", help="score a segment's stored enrichments again (no enrichment calls)"
    )
    add_segment_options(rescore_parser)
    add_model_options(rescore_parser)
    rescore_parser.add_argument("--model", choices=sorted(MODELS), default="sonnet")
    rescore_parser.add_argument("--score-repeats", type=int, default=1)
    rescore_parser.set_defaults(handler=rescore)

    runs_parser = commands.add_parser("runs", help="list recorded runs")
    runs_parser.add_argument("--segment", help="only this segment's runs")
    add_db_option(runs_parser)
    runs_parser.set_defaults(handler=runs)

    for name, handler, text in (
        ("funnel", show_funnel, "show a run's counts per step and its exit reasons"),
        ("check", check, "validate a run independently and record the outcome"),
        ("export", export, "write a run as JSON Lines (to stdout, or a new file with --out)"),
    ):
        sub = commands.add_parser(name, help=text)
        sub.add_argument("run_id")
        add_db_option(sub)
        if name == "export":
            sub.add_argument("--out", type=Path, help="new file to write; never overwritten")
        sub.set_defaults(handler=handler)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)
