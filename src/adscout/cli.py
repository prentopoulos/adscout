"""Command-line entry point for AdScout."""

import argparse
import sys
from collections.abc import Callable
from importlib.metadata import version

from adscout.db.connection import resolve_db_path
from adscout.db.migrate import MigrationError, upgrade

Handler = Callable[[argparse.Namespace], int]


def db_upgrade(args: argparse.Namespace) -> int:
    path = resolve_db_path(args.db)
    try:
        names = upgrade(path)
    except MigrationError as error:
        print(f"adscout db upgrade: {error}", file=sys.stderr)
        return 1
    if names:
        print(f"{path}: applied {', '.join(names)}")
    else:
        print(f"{path}: up to date")
    return 0


def add_db_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", help="database file (default: $ADSCOUT_DB, else data/adscout.db)")


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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)
