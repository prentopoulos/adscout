"""Lead and run IDs, and the code and agent versions every lead and run records."""

import os
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_lock = threading.Lock()
_last_ms = -1
_counter = 0


def uuid7() -> uuid.UUID:
    """A version-7 UUID (RFC 9562): a millisecond timestamp, then a counter, then randomness.

    The 12-bit counter (RFC 9562 §6.2, method 1) keeps IDs made in the same millisecond in
    order. Python 3.14's `uuid.uuid7()` replaces this.
    """
    global _last_ms, _counter
    with _lock:
        now_ms = time.time_ns() // 1_000_000
        if now_ms > _last_ms:
            _last_ms, _counter = now_ms, int.from_bytes(os.urandom(2)) & 0x3FF
        else:
            _counter += 1
            if _counter > 0xFFF:  # counter exhausted: borrow the next millisecond
                _last_ms, _counter = _last_ms + 1, 0
        ms, counter = _last_ms, _counter
    random_bits = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | counter << 64 | 0b10 << 62 | random_bits
    return uuid.UUID(int=value)


def new_run_id() -> str:
    """The evaluation harness's run ID format: UTC time plus six random hex digits."""
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def code_version(root: Path = ROOT) -> tuple[str, bool]:
    """The checked-out commit, and whether the tree has uncommitted or untracked changes."""

    def git(*args: str) -> str:
        # Fixed git arguments only; never user input.
        return subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()

    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


def agent_version(revision: str, dirty: bool, package_version: str | None = None) -> str:
    """PEP 440 local version: `0.2.0+g1a2b3c4d5e6f`, with `.dirty` for uncommitted code."""
    package = package_version or version("adscout")
    return f"{package}+g{revision[:12]}" + (".dirty" if dirty else "")


def current_agent_version(root: Path = ROOT) -> str:
    revision, dirty = code_version(root)
    return agent_version(revision, dirty)
