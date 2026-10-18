"""The secrets scan finds planted fake keys without printing them.

Fake keys are assembled at runtime so this file never contains one.
"""

from pathlib import Path

import pytest

from checks import secrets
from conftest import run_git

FAKE_KEYS = {
    "Anthropic API key": "sk-" + "ant-api03-" + "A1b2" * 10,
    "Langfuse secret key": "sk-" + "lf-" + "1a2b3c4d-" * 4,
    "Langfuse public key": "pk-" + "lf-" + "1a2b3c4d-" * 4,
    "OpenAI API key": "sk-" + "proj-" + "Zz9" * 10,
    "HubSpot private app token": "pat-" + "na1-" + "0a1b2c3d-" * 4,
    "AWS access key ID": "AKIA" + "Q7RX2M4N8P3K5T6W",
    "GitHub token": "ghp" + "_" + "a1B2" * 9,
    "private key block": "-----BEGIN " + "RSA PRIVATE KEY-----",
}


@pytest.fixture
def repo(git_repo: Path) -> Path:
    (git_repo / ".gitignore").write_text(".env\n", encoding="utf-8")
    return git_repo


def plant(repo: Path, name: str, line: str) -> str:
    (repo / name).write_text(line + "\n", encoding="utf-8")
    return line


def test_clean_repository_passes(repo: Path) -> None:
    (repo / "notes.md").write_text("Use `sk-ant-` keys from .env only.\n", encoding="utf-8")
    assert secrets.check(repo) == []


@pytest.mark.parametrize("kind", sorted(FAKE_KEYS))
def test_known_key_format_found_without_value(repo: Path, kind: str) -> None:
    line = plant(repo, "leak.txt", f"value = {FAKE_KEYS[kind]}")
    problems = secrets.check(repo)
    assert problems == [
        f"leak.txt:1: possible {kind} (value not shown; line hash {secrets.line_hash(line)})"
    ]
    assert FAKE_KEYS[kind] not in problems[0]


@pytest.mark.parametrize(
    "line",
    [
        'API_TOKEN = "' + "q8W" * 8 + '"',
        "SERVICE_SECRET=" + "q8W" * 8,
        '{"password": "' + "q8W" * 8 + '"}',
    ],
)
def test_long_literal_assignment_found(repo: Path, line: str) -> None:
    plant(repo, "config.py", line)
    assert secrets.check(repo) == [
        "config.py:1: possible long literal assigned to a secret-like name "
        f"(value not shown; line hash {secrets.line_hash(line)})"
    ]


def test_placeholder_values_pass(repo: Path) -> None:
    plant(repo, ".env.example", "ANTHROPIC_API_KEY=<your-anthropic-api-key-here>")
    assert secrets.check(repo) == []


def test_ignored_and_binary_files_are_not_scanned(repo: Path) -> None:
    plant(repo, ".env", "ANTHROPIC_API_KEY=" + FAKE_KEYS["Anthropic API key"])
    (repo / "image.bin").write_bytes(b"\0\1" + FAKE_KEYS["AWS access key ID"].encode())
    assert secrets.check(repo) == []


def test_tracked_env_file_fails(repo: Path) -> None:
    plant(repo, ".env", "DEBUG=1")
    run_git(repo, "add", "-f", ".env")
    assert secrets.check(repo) == [".env: tracked by Git; untrack it with `git rm --cached .env`"]


def test_env_file_not_ignored_fails(git_repo: Path) -> None:
    assert secrets.check(git_repo) == [".env: not matched by .gitignore"]


def test_allowlisted_finding_passes(repo: Path) -> None:
    line = plant(repo, "doc.md", "Example header: " + FAKE_KEYS["private key block"])
    (repo / secrets.ALLOWLIST).write_text(
        f"doc.md {secrets.line_hash(line)} Documentation example; no key material.\n",
        encoding="utf-8",
    )
    assert secrets.check(repo) == []


def test_allowlist_entry_without_reason_fails(repo: Path) -> None:
    line = plant(repo, "doc.md", "Example header: " + FAKE_KEYS["private key block"])
    (repo / secrets.ALLOWLIST).write_text(f"doc.md {secrets.line_hash(line)}\n", encoding="utf-8")
    problems = secrets.check(repo)
    assert f"{secrets.ALLOWLIST}:1: entry needs a path, a line hash and a reason" in problems
    assert any(problem.startswith("doc.md:1: possible private key block") for problem in problems)
