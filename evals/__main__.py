"""`python -m evals export-schemas` rewrites the committed JSON Schema files."""

import sys

from evals.models import SCHEMA_FILES, schema_text
from evals.runner import SCHEMAS


def main(argv: list[str]) -> int:
    if argv != ["export-schemas"]:
        print("usage: python -m evals export-schemas")
        return 2
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMA_FILES.items():
        (SCHEMAS / filename).write_text(schema_text(model), encoding="utf-8", newline="\n")
        print(f"wrote evals/schemas/{filename}")
    return 0


sys.exit(main(sys.argv[1:]))
