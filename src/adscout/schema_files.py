"""Committed JSON Schema files exported from AdScout's models.

`uv run python -m adscout.schema_files` rewrites them; a test fails when one is stale.
"""

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from adscout.config import SeedRow, SegmentConfig
from adscout.export import ExportLine
from adscout.pipeline.stubs import StubScript

ROOT = Path(__file__).resolve().parents[2]
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def schema_text(model: type[BaseModel]) -> str:
    schema = {"$schema": JSON_SCHEMA_DIALECT, **model.model_json_schema(by_alias=True)}
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def schema_files() -> dict[str, type[BaseModel]]:
    """Repository-relative path of each committed schema, and the model it comes from."""
    return {
        "config/schemas/segment.schema.json": SegmentConfig,
        "config/schemas/seed-row.schema.json": SeedRow,
        "config/schemas/stub-script.schema.json": StubScript,
        "src/adscout/schemas/run-export.schema.json": ExportLine,
    }


def main(argv: list[str]) -> int:
    if argv:
        print("usage: python -m adscout.schema_files")
        return 2
    for relative, model in schema_files().items():
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(schema_text(model), encoding="utf-8", newline="\n")
        print(f"wrote {relative}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
