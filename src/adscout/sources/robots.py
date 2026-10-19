"""robots.txt per RFC 9309: groups by user-agent, longest match, Allow wins a tie.

The fetcher's product token is `AdScoutBot`; a group naming it applies, else the `*` group,
else everything is allowed. `*` matches any run of characters and a trailing `$` anchors the
end of the path. `Crawl-delay` is not in the RFC but is honoured when a site sets it.
How a robots.txt fetch result maps to rules (5xx disallows all, 401 and 403 too, other 4xx
allow all) is the fetcher's decision 10, applied in `rules_for_status`.
"""

import contextlib
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

PRODUCT_TOKEN = "adscoutbot"  # noqa: S105 - a robots.txt user-agent, not a secret


@dataclass(frozen=True)
class Rule:
    allow: bool
    pattern: str

    def matches(self, path: str) -> bool:
        return bool(_compile(self.pattern).match(path))

    @property
    def length(self) -> int:
        return len(self.pattern)


@dataclass(frozen=True)
class RobotsRules:
    rules: tuple[Rule, ...] = ()
    crawl_delay: float | None = None
    disallow_all: bool = False
    note: str = ""

    def allowed(self, path: str) -> bool:
        if self.disallow_all:
            return False
        target = _normalize(path or "/")
        best: Rule | None = None
        for rule in self.rules:
            if not rule.pattern or not rule.matches(target):
                continue
            if (
                best is None
                or rule.length > best.length
                or (rule.length == best.length and rule.allow and not best.allow)
            ):
                best = rule
        return best is None or best.allow


ALLOW_ALL = RobotsRules(note="no robots.txt rules apply")
DISALLOW_ALL = RobotsRules(disallow_all=True, note="robots.txt unreachable or refused")


def rules_for_status(status: int, text: str) -> RobotsRules:
    """Decision 10: a 2xx is parsed; 401 and 403 and any 5xx disallow all; other 4xx allow."""
    if 200 <= status < 300:
        return parse(text)
    if status in (401, 403) or status >= 500:
        return RobotsRules(disallow_all=True, note=f"robots.txt answered HTTP {status}")
    return RobotsRules(note=f"robots.txt answered HTTP {status}: no rules")


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None


def parse(text: str, token: str = PRODUCT_TOKEN) -> RobotsRules:
    groups: list[_Group] = []
    current: _Group | None = None
    collecting_agents = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if current is None or not collecting_agents:
                current = _Group()
                groups.append(current)
            current.agents.append(value.lower())
            collecting_agents = True
            continue
        collecting_agents = False
        if current is None:
            continue
        if key in ("allow", "disallow"):
            current.rules.append(Rule(allow=key == "allow", pattern=_normalize(value)))
        elif key == "crawl-delay":
            with contextlib.suppress(ValueError):
                current.crawl_delay = float(value)
    chosen = [group for group in groups if any(_names(token, agent) for agent in group.agents)]
    if not chosen:
        chosen = [group for group in groups if "*" in group.agents]
    if not chosen:
        return ALLOW_ALL
    delays = [group.crawl_delay for group in chosen if group.crawl_delay is not None]
    return RobotsRules(
        rules=tuple(rule for group in chosen for rule in group.rules),
        crawl_delay=max(delays) if delays else None,
    )


def _names(token: str, agent: str) -> bool:
    # RFC 9309 §2.2.1: the product token is matched case-insensitively.
    return agent != "*" and agent.split("/", 1)[0] == token


def _normalize(path: str) -> str:
    """Percent-decoding of unreserved characters only, so encodings compare equal."""
    return re.sub(
        r"%([0-9A-Fa-f]{2})",
        lambda match: (
            unquote(match.group(0))
            if re.fullmatch(r"[A-Za-z0-9._~-]", unquote(match.group(0)))
            else match.group(0).upper()
        ),
        path,
    )


_compiled: dict[str, re.Pattern[str]] = {}


def _compile(pattern: str) -> re.Pattern[str]:
    if pattern not in _compiled:
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        regex = ".*".join(re.escape(part) for part in body.split("*"))
        _compiled[pattern] = re.compile(regex + ("$" if anchored else ""))
    return _compiled[pattern]
