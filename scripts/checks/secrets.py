"""Scan the repository for secrets, and check that `.env` stays ignored and untracked.

Scans tracked files plus untracked files that are not ignored, and the staged copy of each
tracked file whose working copy differs from it, since the staged copy is what the next commit
takes. A finding names the file and line, never the matched value. A committed
`.secrets-allowlist` can accept a known finding: one entry per line,
`<path> <line-hash> <reason>`, where the line hash is the first 16 hex digits of the SHA-256
of the stripped line, as printed with the finding.
"""

import codecs
import hashlib
import re
import subprocess
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
# A long literal assigned to a name containing KEY, TOKEN, SECRET or PASSWORD.
SENSITIVE_NAME = r"[\w.-]*(?:key|token|secret|password|passwd)[\w.-]*"
QUOTED_ASSIGNMENT = re.compile(
    rf"(?i)\b{SENSITIVE_NAME}[\"']?\s*[:=]\s*[\"']([^\"'\s]{{20,}})[\"']"
)
# Unquoted values, as in .env files, shell `export`, Windows `set` and YAML. Not applied to
# Python, where an unquoted value is a name; quoted Python literals are caught above.
UNQUOTED_ASSIGNMENT = re.compile(
    rf"(?i)^\s*(?:export\s+|set\s+)?[\"']?{SENSITIVE_NAME}[\"']?\s*[:=]\s*([^\s\"'#]{{20,}})"
)
PLACEHOLDER = re.compile(r"(?i)[<>{}$]|\.\.\.|xxx|your|example|changeme|placeholder|dummy")
# Windows PowerShell 5.1 writes UTF-16 with a byte-order mark by default. UTF-32 comes first:
# its little-endian mark starts with the UTF-16 one.
BYTE_ORDER_MARKS = [
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
]


def line_hash(line: str) -> str:
    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()[:16]


def finding(line: str, unquoted: bool = True) -> str | None:
    """The kind of secret the line seems to hold, or None."""
    for kind, pattern in KNOWN_FORMATS:
        if pattern.search(line):
            return kind
    for pattern in (QUOTED_ASSIGNMENT, UNQUOTED_ASSIGNMENT) if unquoted else (QUOTED_ASSIGNMENT,):
        match = pattern.search(line)
        if match and not PLACEHOLDER.search(match.group(1)):
            return "long literal assigned to a secret-like name"
    return None


def decode(data: bytes) -> str | None:
    """The file's text, or None for a binary file."""
    for mark, encoding in BYTE_ORDER_MARKS:
        if data.startswith(mark):
            return data.decode(encoding, errors="replace")
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


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


def scan(label: str, relative: str, data: bytes, allowed: set[tuple[str, str]]) -> list[str]:
    text = decode(data)
    if text is None:
        return []
    unquoted = not relative.endswith(".py")
    problems: list[str] = []
    # Split on newlines only, as Git and editors count lines; str.splitlines also breaks on
    # characters such as U+2028 that may sit inside a line.
    for number, line in enumerate(text.split("\n"), 1):
        kind = finding(line, unquoted)
        if kind and (relative, line_hash(line)) not in allowed:
            problems.append(
                f"{label}:{number}: possible {kind} (value not shown; line hash {line_hash(line)})"
            )
    return problems


def staged_differences(root: Path) -> list[str]:
    """Tracked paths whose staged copy differs from the working copy or has no working copy."""
    listing = git(root, "diff", "--name-only", "-z").stdout
    return sorted(path for path in listing.split("\0") if path)


def staged_bytes(root: Path, relative: str) -> bytes | None:
    """The staged copy of a file, or None when there is none (as during a merge conflict)."""
    blob = subprocess.run(
        ["git", "cat-file", "blob", f":{relative}"], cwd=root, capture_output=True, check=False
    )
    return blob.stdout if blob.returncode == 0 else None


def check(root: Path) -> list[str]:
    allowed, problems = load_allowlist(root)
    for relative in repo_files(root):
        if relative != ALLOWLIST:
            problems += scan(relative, relative, (root / relative).read_bytes(), allowed)
    for relative in staged_differences(root):
        data = staged_bytes(root, relative)
        if relative != ALLOWLIST and data is not None:
            problems += scan(f"{relative} (staged)", relative, data, allowed)
    if git(root, "check-ignore", "-q", "--no-index", ".env", check=False).returncode != 0:
        problems.append(".env: not matched by .gitignore")
    if git(root, "ls-files", "--error-unmatch", ".env", check=False).returncode == 0:
        problems.append(".env: tracked by Git; untrack it with `git rm --cached .env`")
    return problems
