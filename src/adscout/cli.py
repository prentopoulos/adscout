"""Command-line entry point for AdScout."""

import argparse
from importlib.metadata import version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adscout",
        description="Advertiser prospecting and qualification agent (portfolio project).",
    )
    # The version comes from the installed package metadata, set once in pyproject.toml.
    parser.add_argument("--version", action="version", version=f"adscout {version('adscout')}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
