"""Registry diagrams regenerate offline and cannot drift from changed tools or caps."""

import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import diagrams

from adscout.pipeline import registry


def test_generated_files_match_and_svg_has_every_node() -> None:
    assert diagrams.check() == []
    root = ET.fromstring(diagrams.svg())  # noqa: S314 - our generated SVG, no untrusted XML
    assert root.tag.endswith("svg")
    page = diagrams.agent_flow_html()
    assert "<script" not in page and "https://" not in page
    for node in registry.REGISTRY:
        assert node.id in page and node.label in page
    assert "flowchart" in diagrams.compiled_mermaid()
    assert "<html" not in diagrams.artifact_page()


def test_registry_cap_change_invalidates_both_files(monkeypatch) -> None:
    worker = registry.node("worker_ads")
    changed = replace(worker, caps=replace(worker.caps, pages=1))
    monkeypatch.setattr(
        registry, "REGISTRY", tuple(changed if n.id == worker.id else n for n in registry.REGISTRY)
    )
    monkeypatch.setattr(registry, "BY_ID", {n.id: n for n in registry.REGISTRY})
    assert {p.split(" is stale")[0] for p in diagrams.check()} == {"agents.md", "agent-flow.html"}


def test_generation_commands_and_missing_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagrams, "FOLDER", tmp_path)
    assert diagrams.main(["write"]) == 0
    assert diagrams.check(tmp_path) == []
    (tmp_path / "agents.md").unlink()
    assert "is missing" in diagrams.check(tmp_path)[0]
    assert diagrams.main(["artifact", str(tmp_path / "private.html")]) == 0
    assert diagrams.main(["bad"]) == 2
