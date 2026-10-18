"""Command-line entry point for AdScout."""

import argparse
import sqlite3
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path

from adscout.config import ConfigError, load_segment
from adscout.db.connection import connect, resolve_db_path
from adscout.db.migrate import MigrationError, upgrade
from adscout.pipeline.recorder import RunFailed, RunInProgress
from adscout.pipeline.run import (
    DatabaseNotReady,
    SegmentFiles,
    run_crm_sync,
    run_pipeline,
    run_stub_approval,
)

Handler = Callable[[argparse.Namespace], int]
DEFAULT_CONFIG_DIR = Path("config")


def fail(command: str, message: object) -> int:
    print(f"adscout {command}: {message}", file=sys.stderr)
    return 1


@contextmanager
def database(args: argparse.Namespace) -> Iterator[sqlite3.Connection]:
    path = resolve_db_path(args.db)
    if not path.exists():
        raise DatabaseNotReady(f"{path} does not exist; run `adscout db upgrade` first")
    connection = connect(path)
    try:
        yield connection
    finally:
        connection.close()


def db_upgrade(args: argparse.Namespace) -> int:
    path = resolve_db_path(args.db)
    try:
        names = upgrade(path)
    except MigrationError as error:
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
    except (ConfigError, DatabaseNotReady, RunInProgress, RunFailed, OSError) as error:
        return fail("run", error)


def approve(args: argparse.Namespace) -> int:
    if not args.stub:
        return fail("approve", "Phase 1 has only the stub approver; pass --stub")
    try:
        files = SegmentFiles.load(args.config_dir, args.segment)
        with database(args) as connection:
            return report(run_stub_approval(connection, files), "approval")
    except (ConfigError, DatabaseNotReady, RunInProgress, RunFailed, OSError) as error:
        return fail("approve", error)


def sync(args: argparse.Namespace) -> int:
    try:
        segment = load_segment(args.config_dir / "segments" / f"{args.segment}.yaml")
        with database(args) as connection:
            return report(run_crm_sync(connection, segment), "CRM sync")
    except (ConfigError, DatabaseNotReady, RunInProgress, RunFailed, OSError) as error:
        return fail("sync", error)


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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)
