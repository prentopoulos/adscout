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


LITERAL = "q8W" * 8


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("config.py", f'API_TOKEN = "{LITERAL}"'),
        ("config.py", f'SECRET_KEY_BASE="{LITERAL}"'),
        ("config.py", f'DB_PASSWORD_PROD = "{LITERAL}"'),
        ("config.py", f'client_secret_value = "{LITERAL}"'),
        ("config.json", f'{{"password": "{LITERAL}"}}'),
        ("settings.env", f"SERVICE_SECRET={LITERAL}"),
        ("settings.env", f"export api_key={LITERAL}"),
        ("setup.cmd", f"set OPENAI_API_KEY={LITERAL}"),
        ("config.yaml", f"  password: {LITERAL}"),
    ],
)
def test_long_literal_assignment_found(repo: Path, name: str, line: str) -> None:
    plant(repo, name, line)
    assert secrets.check(repo) == [
        f"{name}:1: possible long literal assigned to a secret-like name "
        f"(value not shown; line hash {secrets.line_hash(line)})"
    ]


def test_unquoted_python_names_pass(repo: Path) -> None:
    plant(repo, "config.py", "api_key = settings.anthropic_api_key_value")
    assert secrets.check(repo) == []


def test_placeholder_values_pass(repo: Path) -> None:
    plant(repo, ".env.example", "ANTHROPIC_API_KEY=<your-anthropic-api-key-here>")
    assert secrets.check(repo) == []


def test_ignored_and_binary_files_are_not_scanned(repo: Path) -> None:
    plant(repo, ".env", "ANTHROPIC_API_KEY=" + FAKE_KEYS["Anthropic API key"])
    (repo / "image.bin").write_bytes(b"\0\1" + FAKE_KEYS["AWS access key ID"].encode())
    assert secrets.check(repo) == []


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"])
def test_utf16_and_utf32_files_are_scanned(repo: Path, encoding: str) -> None:
    # These codecs write no byte-order mark, so the leading U+FEFF becomes it.
    text = "﻿ANTHROPIC_API_KEY=" + FAKE_KEYS["Anthropic API key"] + "\n"
    (repo / "notes.txt").write_text(text, encoding=encoding)
    (problem,) = secrets.check(repo)
    assert problem.startswith("notes.txt:1: possible Anthropic API key")


def test_line_numbers_count_newlines_only(repo: Path) -> None:
    (repo / "notes.txt").write_text(
        "title = 'one" + chr(0x2028) + "line'\nvalue = " + FAKE_KEYS["AWS access key ID"] + "\n",
        encoding="utf-8",
    )
    (problem,) = secrets.check(repo)
    assert problem.startswith("notes.txt:2: possible AWS access key ID")


def test_staged_secret_is_found_after_working_copy_is_cleaned(repo: Path) -> None:
    line = plant(repo, "config.txt", "value = " + FAKE_KEYS["Anthropic API key"])
    plant(repo, "removed.txt", "value = " + FAKE_KEYS["GitHub token"])
    run_git(repo, "add", "config.txt", "removed.txt")
    plant(repo, "config.txt", "value = read from .env")
    (repo / "removed.txt").unlink()
    problems = secrets.check(repo)
    assert problems[0] == (
        f"config.txt (staged):1: possible Anthropic API key (value not shown; "
        f"line hash {secrets.line_hash(line)})"
    )
    assert problems[1].startswith("removed.txt (staged):1: possible GitHub token")
    assert len(problems) == 2


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
