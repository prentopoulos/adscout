"""Check that the verbatim skill copies still match their source manifest digests."""

import hashlib
import json
from pathlib import Path

from checks.common import read_text

MANIFEST = ".agents/skills/adscout-build-safety/references/source-manifest.json"


def check(root: Path) -> list[str]:
    manifest = json.loads(read_text(root / MANIFEST))
    entries = manifest.get("files", [])
    if not entries:
        return [f"{MANIFEST}: lists no files"]
    problems: list[str] = []
    for entry in entries:
        path = root / entry["copy"]
        if not path.is_file():
            problems.append(f"{entry['copy']}: missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            problems.append(f"{entry['copy']}: SHA-256 differs from the source manifest")
    return problems
