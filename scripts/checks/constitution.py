"""Check that the constitution's verbatim copies match PROJECT.md §5.

PROJECT.md §5 holds the rules. AGENTS.md and the `context` of openspec/config.yaml carry
copies. The copies must list the same rules in the same order with the same words; only line
wrapping and repeated whitespace may differ. Every version line, and PROJECT.md's "Last
amended" date, must match the newest row of the amendment log.
"""

import re
from pathlib import Path

import yaml

from checks.common import read_text

PROJECT_SECTION = re.compile(r"^## 5\. ")
PROJECT_VERSION = re.compile(r"^\*\*Version (\S+)\*\* · Ratified (\S+) · Last amended (\S+)$")
AGENTS_SECTION = re.compile(r"^## Non-negotiables")
AGENTS_VERSION = re.compile(r"^\*\*Version (\S+)\*\*$")
CONFIG_VERSION = re.compile(r"^Version (\S+)$")
LOG_HEADER = re.compile(r"^\| Version \| Date \|")


def normalize(text: str) -> str:
    return " ".join(text.split())


def find(
    lines: list[str], pattern: re.Pattern[str], start: int = 0
) -> tuple[int, re.Match[str]] | None:
    """The first line at or after `start` matching `pattern`, with its match."""
    for index in range(start, len(lines)):
        match = pattern.match(lines[index])
        if match:
            return index, match
    return None


def find_after(
    lines: list[str], section: re.Pattern[str], pattern: re.Pattern[str]
) -> tuple[int, re.Match[str]] | None:
    heading = find(lines, section)
    return find(lines, pattern, heading[0]) if heading else None


def bullets_after(lines: list[str], start: int) -> list[str]:
    """The first Markdown bullet list after lines[start], with wrapped lines joined."""
    rules: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("- "):
            rules.append(line[2:])
        elif rules and line.startswith("  ") and line.strip():
            rules[-1] += " " + line.strip()
        elif rules or line.strip():
            break
    return [normalize(rule) for rule in rules]


def newest_log_row(lines: list[str], start: int) -> tuple[str, str] | None:
    """Version and date of the last row in the amendment-log table after lines[start]."""
    header = find(lines, LOG_HEADER, start)
    if header is None:
        return None
    rows: list[list[str]] = []
    for line in lines[header[0] + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    if not rows or len(rows[-1]) < 2:
        return None
    return rows[-1][0], rows[-1][1]


def compare_rules(name: str, copy: list[str], source: list[str]) -> list[str]:
    problems: list[str] = []
    if len(copy) != len(source):
        problems.append(f"{name}: has {len(copy)} rules; PROJECT.md §5 has {len(source)}")
    for index, (ours, theirs) in enumerate(zip(copy, source, strict=False), start=1):
        if ours != theirs:
            problems.append(f"{name}: rule {index} differs from PROJECT.md §5")
    return problems


def check_copy(
    name: str,
    lines: list[str],
    found: tuple[int, re.Match[str]] | None,
    version: str,
    source: list[str],
) -> list[str]:
    if found is None:
        return [f"{name}: no version line before its copy of the rules"]
    problems: list[str] = []
    index, match = found
    if match.group(1) != version:
        problems.append(f"{name}: version {match.group(1)} differs from PROJECT.md ({version})")
    return problems + compare_rules(name, bullets_after(lines, index), source)


def check(root: Path) -> list[str]:
    project = read_text(root / "PROJECT.md").splitlines()
    found = find_after(project, PROJECT_SECTION, PROJECT_VERSION)
    if found is None:
        return ["PROJECT.md: no '**Version …** · Ratified … · Last amended …' line in §5"]
    index, match = found
    version, _, last_amended = match.groups()
    source = bullets_after(project, index)

    problems: list[str] = []
    if not source:
        problems.append("PROJECT.md: no rules found under the §5 version line")
    newest = newest_log_row(project, index)
    if newest is None:
        problems.append("PROJECT.md: no amendment-log table found in §5")
    else:
        log_version, log_date = newest
        if version != log_version:
            problems.append(
                f"PROJECT.md: version {version} differs from the newest amendment-log row "
                f"({log_version})"
            )
        if last_amended != log_date:
            problems.append(
                f"PROJECT.md: Last amended {last_amended} differs from the newest "
                f"amendment-log row ({log_date})"
            )

    agents = read_text(root / "AGENTS.md").splitlines()
    problems += check_copy(
        "AGENTS.md", agents, find_after(agents, AGENTS_SECTION, AGENTS_VERSION), version, source
    )

    config = yaml.safe_load(read_text(root / "openspec" / "config.yaml"))
    context = str(config.get("context", "")) if isinstance(config, dict) else ""
    context_lines = context.splitlines()
    problems += check_copy(
        "openspec/config.yaml",
        context_lines,
        find(context_lines, CONFIG_VERSION),
        version,
        source,
    )
    return problems
