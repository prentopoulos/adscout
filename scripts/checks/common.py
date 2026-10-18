"""Helpers shared by the gate checks."""

import subprocess
from pathlib import Path


def read_text(path: Path) -> str:
    # Explicit UTF-8: the documents contain "·" and "⛔", and Windows defaults to cp1252.
    return path.read_text(encoding="utf-8")


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=check
    )


def repo_files(root: Path) -> list[str]:
    """Tracked files plus untracked files that are not ignored, as POSIX paths."""
    listing = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout
    return sorted({path for path in listing.split("\0") if path and (root / path).is_file()})
