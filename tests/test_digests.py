"""The digest check catches any change to a verbatim skill copy."""

import json
import shutil
from pathlib import Path

import pytest
from checks import digests
from conftest import ROOT


@pytest.fixture
def copies(tmp_path: Path) -> tuple[Path, list[str]]:
    manifest = json.loads((ROOT / digests.MANIFEST).read_text(encoding="utf-8"))
    files = [entry["copy"] for entry in manifest["files"]]
    for relative in [digests.MANIFEST, *files]:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return tmp_path, files


def test_current_copies_match(copies: tuple[Path, list[str]]) -> None:
    root, files = copies
    assert len(files) == 26
    assert digests.check(root) == []


def test_changed_byte_fails(copies: tuple[Path, list[str]]) -> None:
    root, files = copies
    path = root / files[0]
    data = bytearray(path.read_bytes())
    data[0] ^= 1
    path.write_bytes(bytes(data))
    assert digests.check(root) == [f"{files[0]}: SHA-256 differs from the source manifest"]


def test_missing_file_fails(copies: tuple[Path, list[str]]) -> None:
    root, files = copies
    (root / files[-1]).unlink()
    assert digests.check(root) == [f"{files[-1]}: missing"]
