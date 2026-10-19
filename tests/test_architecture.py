"""The C4 model, its exported views and the generated ERD stay in step with the code."""

import re
import shutil
import sqlite3
from pathlib import Path

import architecture
import erd

FOLDER = architecture.FOLDER
PLANNED = {
    "CRM sandbox": 3,
    "Sandbox inbox": 3,
    "Tracing service": 3,
}
BUILT = (
    "Command-line pipeline",
    "Pipeline database",
    "Local fake CRM",
    "Config files",
    "Local workspace",
    "Model provider",
    "Public data APIs",
    "Web search",
    "Company websites",
)


def copy_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "architecture"
    shutil.copytree(FOLDER, folder)
    return folder


def test_exports_match_the_stamped_model() -> None:
    assert architecture.check() == []


def test_model_edited_without_re_export_fails(tmp_path: Path) -> None:
    folder = copy_folder(tmp_path)
    workspace = folder / "workspace.dsl"
    workspace.write_text(workspace.read_text("utf-8").replace("Works at", "Sits at"), "utf-8")
    assert architecture.check(folder) == [
        "workspace.dsl changed since the last export; re-export and re-stamp"
    ]


def test_missing_or_edited_export_fails(tmp_path: Path) -> None:
    folder = copy_folder(tmp_path)
    (folder / "svg" / "Context.svg").unlink()
    edited = folder / "mermaid" / "structurizr-ContainersBuilt.mmd"
    edited.write_text(edited.read_text("utf-8") + "\n%% edited\n", "utf-8")
    problems = architecture.check(folder)
    assert "svg/Context.svg is missing; re-export" in problems
    assert any(
        problem.startswith("mermaid/structurizr-ContainersBuilt.mmd") for problem in problems
    )


def test_missing_stamp_fails(tmp_path: Path) -> None:
    folder = copy_folder(tmp_path)
    (folder / "export-stamp.json").unlink()
    assert architecture.check(folder)[0].startswith("no export stamp")


def test_stamp_ignores_line_endings(tmp_path: Path) -> None:
    folder = copy_folder(tmp_path)
    workspace = folder / "workspace.dsl"
    workspace.write_bytes(workspace.read_bytes().replace(b"\n", b"\r\n"))
    assert architecture.check(folder) == []


def test_views_are_context_built_and_target() -> None:
    assert architecture.view_keys() == [
        "Context",
        "ContainersBuilt",
        "ContainersTarget",
        "ResearchTeam",
    ]


def test_planned_elements_are_tagged_with_their_phase() -> None:
    lines = (FOLDER / "workspace.dsl").read_text(encoding="utf-8").splitlines()
    for name, phase in PLANNED.items():
        (line,) = [line for line in lines if f'"{name}"' in line]
        assert f"(planned, Phase {phase})" in line and "Planned" in line.rsplit('"', 2)[-2]


def element_names(view: str) -> set[str]:
    """The element names a Mermaid export draws (each in a bold div)."""
    text = (FOLDER / "mermaid" / f"structurizr-{view}.mmd").read_text(encoding="utf-8")
    return set(re.findall(r"<div style='font-weight: bold'>([^<]+)</div>", text))


def test_built_view_shows_only_what_exists() -> None:
    built = element_names("ContainersBuilt")
    assert built == {"Ad sales researcher", *BUILT}
    assert element_names("ContainersTarget") == {"Ad sales researcher", *BUILT, *PLANNED}


def test_exported_svgs_carry_no_scripts() -> None:
    for svg in (FOLDER / "svg").glob("*.svg"):
        text = svg.read_text(encoding="utf-8")
        assert text.startswith("<svg") and "<script" not in text


def test_erd_matches_a_fresh_generation() -> None:
    assert erd.ERD.read_text(encoding="utf-8") == erd.document(), (
        "erd.md is stale; run `uv run --locked python scripts/erd.py`"
    )


def test_erd_changes_when_the_schema_does(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY) STRICT")
    connection.execute(
        "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent (id)) "
        "STRICT"
    )
    diagram = erd.mermaid(connection)
    connection.close()
    assert "INTEGER parent_id FK" in diagram
    assert 'child }o--|| parent : "parent_id"' in diagram
    assert diagram not in erd.ERD.read_text(encoding="utf-8")
