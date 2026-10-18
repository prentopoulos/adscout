"""Check Markdown links, Claude skill pointers and skill frontmatter.

- Local Markdown links and reference definitions (outside code and HTML comments) resolve
  from the linking file's folder to a file or folder Git sees: tracked, or untracked and not
  ignored, matched case-sensitively, so a link that works here also works in a fresh clone.
- Each `.claude/skills/<name>/SKILL.md` with a canonical `.agents/skills/<name>/SKILL.md`
  has the same name and description.
- Every skill's frontmatter name matches its folder, and it has a description.
"""

import posixpath
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

import yaml

from checks.common import read_text, repo_files

FENCE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1", re.MULTILINE | re.DOTALL)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")
# A link target: <anything on one line>, or a run without spaces that may hold one level of
# balanced parentheses, as in foo(1).md.
TARGET = r"(?:<([^<>\n]+)>|((?:[^()\s]|\([^()\s]*\))+))"
LINK = re.compile(rf"\]\(\s*{TARGET}")
# A reference definition, `[label]: target`; `[^label]:` starts a footnote instead.
REFERENCE = re.compile(rf"^ {{0,3}}\[(?!\^)[^\]\n]+\]:[ \t]*{TARGET}", re.MULTILINE)
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
SKILL_FOLDERS = (".agents/skills/", ".claude/skills/", ".codex/skills/")


def local_links(text: str) -> list[str]:
    text = INLINE_CODE.sub("", COMMENT.sub("", FENCE.sub("", text)))
    targets: list[str] = []
    for bracketed, bare in LINK.findall(text) + REFERENCE.findall(text):
        target = bracketed or bare
        if SCHEME.match(target) or target.startswith("#"):
            continue
        targets.append(unquote(target.split("#", 1)[0].split("?", 1)[0]))
    return [target for target in targets if target]


def frontmatter(text: str) -> dict[str, object] | None:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            data = yaml.safe_load("\n".join(lines[1:end]))
            return data if isinstance(data, dict) else None
    return None


def check_links(root: Path, files: list[str]) -> list[str]:
    known = set(files) | {str(folder) for file in files for folder in PurePosixPath(file).parents}
    problems: list[str] = []
    for relative in files:
        if not relative.endswith(".md"):
            continue
        folder = PurePosixPath(relative).parent
        for target in local_links(read_text(root / relative)):
            joined = target.lstrip("/") if target.startswith("/") else str(folder / target)
            if posixpath.normpath(joined) not in known:
                problems.append(f"{relative}: broken link to {target}")
    return problems


def check_skills(root: Path, files: list[str]) -> list[str]:
    problems: list[str] = []
    skills: dict[str, dict[str, object]] = {}
    for relative in files:
        parts = relative.split("/")
        if not (relative.startswith(SKILL_FOLDERS) and len(parts) == 4 and parts[3] == "SKILL.md"):
            continue
        try:
            meta = frontmatter(read_text(root / relative))
        except yaml.YAMLError as error:
            problems.append(
                f"{relative}: frontmatter is not valid YAML: {' '.join(str(error).split())}"
            )
            continue
        if meta is None:
            problems.append(f"{relative}: no YAML frontmatter")
            continue
        skills[relative] = meta
        if meta.get("name") != parts[2]:
            problems.append(f"{relative}: name {meta.get('name')!r} does not match its folder")
        if not str(meta.get("description") or "").strip():
            problems.append(f"{relative}: no description")
    for relative, meta in skills.items():
        if not relative.startswith(".claude/skills/"):
            continue
        canonical = skills.get(relative.replace(".claude/", ".agents/", 1))
        if canonical is None:
            continue
        for key in ("name", "description"):
            if meta.get(key) != canonical.get(key):
                problems.append(f"{relative}: {key} differs from its canonical .agents skill")
    return problems


def check(root: Path) -> list[str]:
    files = repo_files(root)
    return check_links(root, files) + check_skills(root, files)
