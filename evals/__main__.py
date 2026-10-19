"""`python -m evals export-schemas | score-compare`.

`export-schemas` rewrites the committed JSON Schema files; `score-compare` runs the scoring
tier evaluation (evals/score_compare.py).
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from adscout.config import ConfigError, load_segment
from adscout.db.connection import connect, resolve_db_path
from adscout.llm.adapter import LiveModeRefused
from adscout.pipeline.models import ModelChoice, ModelsNotChosen
from adscout.pipeline.run import DatabaseNotReady
from evals.models import SCHEMA_FILES, schema_text
from evals.runner import SCHEMAS
from evals.score_check import load_labels
from evals.score_compare import score_compare, write_report


def export_schemas() -> int:
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMA_FILES.items():
        (SCHEMAS / filename).write_text(schema_text(model), encoding="utf-8", newline="\n")
        print(f"wrote evals/schemas/{filename}")
    return 0


def compare(args: argparse.Namespace) -> int:
    cap = Decimal(args.max_spend_usd) if args.max_spend_usd is not None else None
    choices = {
        arm: ModelChoice(
            live=args.live, cap_usd=cap, replay_run_id=replay, scripted=args.fixture_models
        )
        for arm, replay in (("haiku", args.replay_haiku), ("sonnet", args.replay_sonnet))
    }
    try:
        segment = load_segment(args.config_dir / "segments" / f"{args.segment}.yaml")
        labels = load_labels(args.labels)
        for choice in choices.values():
            choice.check()
        path = resolve_db_path(args.db)
        if not path.exists():
            raise DatabaseNotReady(f"{path} does not exist; run `adscout db upgrade` first")
        connection = connect(path)
        try:
            result = score_compare(
                connection, segment, labels, choices, repeats=args.repeats, cap_usd=cap
            )
        finally:
            connection.close()
    except (
        ConfigError,
        ModelsNotChosen,
        LiveModeRefused,
        DatabaseNotReady,
        LookupError,
        OSError,
    ) as error:
        print(f"score-compare: {error}", file=sys.stderr)
        return 1
    out = write_report(result)
    decision = result["decision"]
    print(f"wrote {out}")
    print(
        f"tier rule: {decision['model']} scores; "
        + ("; ".join(decision["reasons_against_sonnet"]) or "Sonnet meets every condition")
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("export-schemas", help="rewrite the committed JSON Schema files")
    sub = commands.add_parser("score-compare", help="score stored enrichments on Haiku and Sonnet")
    sub.add_argument("--segment", required=True)
    sub.add_argument("--labels", type=Path, required=True, help="the owner's labels CSV")
    sub.add_argument("--config-dir", type=Path, default=Path("config"))
    sub.add_argument("--db")
    sub.add_argument("--repeats", type=int, default=3)
    sub.add_argument("--live", action="store_true")
    sub.add_argument("--max-spend-usd")
    sub.add_argument("--fixture-models", type=Path)
    sub.add_argument("--replay-haiku", metavar="RUN_ID")
    sub.add_argument("--replay-sonnet", metavar="RUN_ID")
    args = parser.parse_args(argv)
    if args.command == "export-schemas":
        return export_schemas()
    return compare(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
