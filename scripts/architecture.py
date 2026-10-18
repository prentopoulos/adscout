"""Keep the exported C4 diagrams in step with `docs/architecture/workspace.dsl`.

    uv run --locked python scripts/architecture.py stamp   # after exporting with Structurizr
    uv run --locked python scripts/architecture.py check   # what the gate's test runs

The stamp records the SHA-256 of the model and of every exported file, so the check needs no
Java: it fails when the model changed without a re-export, or an export is missing or edited.
Hashes ignore line endings, so a clone with any `core.autocrlf` setting agrees.
"""

import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "docs" / "architecture"
WORKSPACE = FOLDER / "workspace.dsl"
STAMP = FOLDER / "export-stamp.json"
EXPORTED_WITH = "structurizr-2026.09.19-playwright.war on Microsoft OpenJDK 21.0.12.1"
VIEW = re.compile(r"^\s*(?:systemContext|container)\s+\S+\s+\"(\w+)\"", re.MULTILINE)


def text_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def view_keys(workspace: Path = WORKSPACE) -> list[str]:
    return VIEW.findall(workspace.read_text(encoding="utf-8"))


def expected_files(folder: Path = FOLDER) -> list[str]:
    files = []
    for key in view_keys(folder / "workspace.dsl"):
        files += [f"svg/{key}.svg", f"svg/{key}-key.svg", f"mermaid/structurizr-{key}.mmd"]
    return files


def stamp(folder: Path = FOLDER) -> dict[str, object]:
    # File names go in values, not keys: a name such as `Context-key.svg` next to a long hash
    # would look like an assigned secret to the secrets scan.
    record: dict[str, object] = {
        "workspace_sha256": text_hash(folder / "workspace.dsl"),
        "exported_with": EXPORTED_WITH,
        "exported_on": datetime.now(UTC).date().isoformat(),
        "files": [
            {"path": name, "sha256": text_hash(folder / name)} for name in expected_files(folder)
        ],
    }
    (folder / "export-stamp.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return record


def check(folder: Path = FOLDER) -> list[str]:
    """Problems with the exports; empty when they match the model."""
    stamp_path = folder / "export-stamp.json"
    if not stamp_path.exists():
        return ["no export stamp; export the views and run `scripts/architecture.py stamp`"]
    record = json.loads(stamp_path.read_text(encoding="utf-8"))
    problems = []
    if record.get("workspace_sha256") != text_hash(folder / "workspace.dsl"):
        problems.append("workspace.dsl changed since the last export; re-export and re-stamp")
    files = {item["path"]: item["sha256"] for item in record.get("files", [])}
    for name in expected_files(folder):
        path = folder / name
        if not path.exists():
            problems.append(f"{name} is missing; re-export")
        elif files.get(name) != text_hash(path):
            problems.append(f"{name} differs from the stamped export; re-export and re-stamp")
    return problems


def main(argv: list[str]) -> int:
    if argv == ["stamp"]:
        missing = [name for name in expected_files() if not (FOLDER / name).exists()]
        if missing:
            print("export these first: " + ", ".join(missing))
            return 1
        stamp()
        print(f"wrote {STAMP.relative_to(ROOT)}")
        return 0
    if argv == ["check"]:
        problems = check()
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    print("usage: python scripts/architecture.py stamp|check")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
