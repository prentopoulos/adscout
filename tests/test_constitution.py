"""The copy check catches drift between PROJECT.md §5 and its two verbatim copies."""

import shutil
from pathlib import Path

import pytest
from checks import constitution
from conftest import ROOT

COPIES = ("PROJECT.md", "AGENTS.md", "openspec/config.yaml")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for relative in COPIES:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return tmp_path


def current_version_and_date() -> tuple[str, str]:
    lines = (ROOT / "PROJECT.md").read_text(encoding="utf-8").splitlines()
    found = constitution.find_after(
        lines, constitution.PROJECT_SECTION, constitution.PROJECT_VERSION
    )
    assert found is not None
    version, _, last_amended = found[1].groups()
    return version, last_amended


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture text not found in {path.name}; update this test"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_current_copies_match(project: Path) -> None:
    assert constitution.check(project) == []


def test_line_wrapping_is_ignored(project: Path) -> None:
    edit(
        project / "AGENTS.md",
        "- Operator resolves all ⛔ gates. The agent never satisfies or waives one itself.",
        "- Operator resolves all ⛔ gates. The agent never satisfies\n  or waives one itself.",
    )
    assert constitution.check(project) == []


def test_edited_rule_fails(project: Path) -> None:
    edit(project / "AGENTS.md", "Preserve failed runs.", "Keep failed runs.")
    assert constitution.check(project) == ["AGENTS.md: rule 2 differs from PROJECT.md §5"]


def test_missing_rule_fails(project: Path) -> None:
    edit(
        project / "openspec/config.yaml",
        "  - Revenue data is simulated and labelled as simulated wherever it is shown.\n",
        "",
    )
    assert "openspec/config.yaml: has 9 rules; PROJECT.md §5 has 10" in constitution.check(project)


def test_reordered_rules_fail(project: Path) -> None:
    path = project / "openspec/config.yaml"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    ninth = next(i for i, line in enumerate(lines) if line.startswith("  - Every lead gets an ID"))
    lines[ninth], lines[ninth + 1] = lines[ninth + 1], lines[ninth]
    path.write_text("".join(lines), encoding="utf-8")
    assert constitution.check(project) == [
        "openspec/config.yaml: rule 9 differs from PROJECT.md §5",
        "openspec/config.yaml: rule 10 differs from PROJECT.md §5",
    ]


def test_copy_version_drift_fails(project: Path) -> None:
    version, _ = current_version_and_date()
    edit(project / "AGENTS.md", f"**Version {version}**", "**Version 9.9.9**")
    assert constitution.check(project) == [
        f"AGENTS.md: version 9.9.9 differs from PROJECT.md ({version})"
    ]


def test_last_amended_mismatch_fails(project: Path) -> None:
    _, last_amended = current_version_and_date()
    edit(project / "PROJECT.md", f"Last amended {last_amended}", "Last amended 1999-01-01")
    assert constitution.check(project) == [
        "PROJECT.md: Last amended 1999-01-01 differs from the newest amendment-log row "
        f"({last_amended})"
    ]
