"""Scan the repository for secrets, and check that `.env` stays ignored and untracked.

Scans tracked files plus untracked files that are not ignored. A finding names the file and
line, never the matched value. A committed `.secrets-allowlist` can accept a known finding:
one entry per line, `<path> <line-hash> <reason>`, where the line hash is the first 16 hex
digits of the SHA-256 of the stripped line, as printed with the finding.
"""

import hashlib
import re
from pathlib import Path

from checks.common import git, read_text, repo_files

ALLOWLIST = ".secrets-allowlist"

# Prefixes of the key formats this stack uses; confirm each when its account is created.
KNOWN_FORMATS: list[tuple[str, re.Pattern[str]]] = [
    ("Anthropic API key", re.compile(r"(?<![\w-])sk-ant-[A-Za-z0-9_-]{20,}")),
    ("Langfuse secret key", re.compile(r"(?<![\w-])sk-lf-[A-Za-z0-9-]{20,}")),
    ("Langfuse public key", re.compile(r"(?<![\w-])pk-lf-[A-Za-z0-9-]{20,}")),
    ("OpenAI API key", re.compile(r"(?<![\w-])sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}")),
    ("HubSpot private app token", re.compile(r"(?<![\w-])pat-(?:na|eu)\d+-[0-9a-f-]{20,}")),
    ("AWS access key ID", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
# A long literal assigned to a name ending in KEY, TOKEN, SECRET or PASSWORD.
QUOTED_ASSIGNMENT = re.compile(
    r"(?i)\b\w*(?:key|token|secret|password|passwd)\b[\"']?\s*[:=]\s*[\"']([^\"'\s]{20,})[\"']"
)
ENV_ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+)?[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*=\s*([^\s\"'#]{20,})"
)
PLACEHOLDER = re.compile(r"(?i)[<>{}$]|\.\.\.|xxx|your|example|changeme|placeholder|dummy")


def line_hash(line: str) -> str:
    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()[:16]


def finding(line: str) -> str | None:
    """The kind of secret the line seems to hold, or None."""
    for kind, pattern in KNOWN_FORMATS:
        if pattern.search(line):
            return kind
    for pattern in (QUOTED_ASSIGNMENT, ENV_ASSIGNMENT):
        match = pattern.search(line)
        if match and not PLACEHOLDER.search(match.group(1)):
            return "long literal assigned to a secret-like name"
    return None


def load_allowlist(root: Path) -> tuple[set[tuple[str, str]], list[str]]:
    path = root / ALLOWLIST
    if not path.is_file():
        return set(), []
    allowed: set[tuple[str, str]] = set()
    problems: list[str] = []
    for number, raw in enumerate(read_text(path).splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=2)
        if len(parts) < 3:
            problems.append(f"{ALLOWLIST}:{number}: entry needs a path, a line hash and a reason")
            continue
        allowed.add((parts[0], parts[1]))
    return allowed, problems


def scan_file(root: Path, relative: str, allowed: set[tuple[str, str]]) -> list[str]:
    data = (root / relative).read_bytes()
    if b"\0" in data[:8192]:
        return []
    problems: list[str] = []
    for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
        kind = finding(line)
        if kind and (relative, line_hash(line)) not in allowed:
            problems.append(
                f"{relative}:{number}: possible {kind} (value not shown; "
                f"line hash {line_hash(line)})"
            )
    return problems


def check(root: Path) -> list[str]:
    allowed, problems = load_allowlist(root)
    for relative in repo_files(root):
        if relative != ALLOWLIST:
            problems += scan_file(root, relative, allowed)
    if git(root, "check-ignore", "-q", "--no-index", ".env", check=False).returncode != 0:
        problems.append(".env: not matched by .gitignore")
    if git(root, "ls-files", "--error-unmatch", ".env", check=False).returncode == 0:
        problems.append(".env: tracked by Git; untrack it with `git rm --cached .env`")
    return problems
