"""Check that every branch commit since main follows Conventional Commits 1.0.0."""

import re
from pathlib import Path

from checks.common import git

SUBJECT = re.compile(
    r"^(?:feat|fix|docs|chore|refactor|test|build|ci|perf|style|revert)"
    r"(?:\([a-z0-9][a-z0-9._/-]*\))?!?: \S"
)


def base_ref(root: Path) -> str | None:
    for ref in ("main", "origin/main"):
        if git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False).stdout:
            return ref
    return None


def check(root: Path) -> list[str]:
    ref = base_ref(root)
    if ref is None:
        return ["no main or origin/main branch to compare commits against"]
    base = git(root, "merge-base", ref, "HEAD").stdout.strip()
    log = git(root, "log", "--no-merges", "--format=%h%x00%s", f"{base}..HEAD").stdout
    problems: list[str] = []
    for entry in log.splitlines():
        short_hash, subject = entry.split("\0", 1)
        if not SUBJECT.match(subject):
            problems.append(f"{short_hash}: subject {subject!r} is not a Conventional Commit")
    return problems
