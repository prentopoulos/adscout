"""Smoke checks: the package installs, imports and reports its version."""

import socket
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

import pytest
from pytest_socket import SocketBlockedError

ROOT = Path(__file__).resolve().parent.parent


def pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_package_imports() -> None:
    import adscout

    assert adscout.__doc__


def test_version_command_prints_metadata_version() -> None:
    script = Path(sys.executable).parent / ("adscout.exe" if sys.platform == "win32" else "adscout")
    result = subprocess.run(
        [str(script), "--version"], capture_output=True, text=True, check=True, timeout=60
    )
    assert result.stdout.strip() == f"adscout {pyproject_version()}"
    assert metadata.version("adscout") == pyproject_version()


def test_metadata_guards_against_upload() -> None:
    meta = metadata.metadata("adscout")
    assert "Private :: Do Not Upload" in (meta.get_all("Classifier") or [])
    assert meta.get("License") is None
    assert meta.get("License-Expression") is None


def test_tests_cannot_open_sockets() -> None:
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
