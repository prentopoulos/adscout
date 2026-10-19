"""Draw the agent flow from the registry: `docs/architecture/agents.md` and `agent-flow.html`.

    uv run --locked python scripts/diagrams.py write          # regenerate both files
    uv run --locked python scripts/diagrams.py check          # what the gate's test runs
    uv run --locked python scripts/diagrams.py artifact OUT   # the page without its document
                                                              # wrapper, for publishing

Everything comes from `src/adscout/pipeline/registry.py` (its nodes and `FLOWS`) and the
pipeline's step order. Nothing reaches the network and nothing depends on the date, so the
gate can compare the committed files with a fresh generation. After `write`, re-stamp with
`scripts/architecture.py stamp`, since the export stamp covers both files.
"""

import html
import itertools
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from adscout.pipeline import registry
from adscout.pipeline.contracts import PIPELINE_STEPS
from adscout.pipeline.registry import Caps, Node

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "docs" / "architecture"
AGENTS_MD = "agents.md"
AGENT_FLOW = "agent-flow.html"
REGENERATE = "run `uv run --locked python scripts/diagrams.py write`, then re-stamp"

DASH = chr(0x2013)  # an en dash, by code point
# pattern: (name, CSS token, Mermaid fill, Mermaid stroke)
PATTERNS = {
    "sequential": ("Sequential", "seq", "#e9edfb", "#3651c9"),
    "router": ("Router", "router", "#f8eedc", "#a3620a"),
    "orchestrator_workers": ("Orchestrator" + DASH + "workers", "orch", "#e1f2ef", "#0d7a6f"),
    "evaluator_optimizer": ("Evaluator" + DASH + "optimizer", "evalopt", "#efe8f8", "#7a45b8"),
    "single_call": ("Single call", "single", "#e9f1e0", "#4a7a1f"),
    "tool_loop": ("Tool loop", "loop", "#f6e3e0", "#b03a2e"),
    "code": ("Plain code", "code", "#eceef2", "#5b6578"),
    "human": ("Person", "human", "#f8e4ed", "#b5346a"),
}
# zone: (name, CSS token, badge)
ZONES = {
    "untrusted_content": ("Reads untrusted content", "web", "WEB"),
    "no_tools": ("Model with no tools", "tools", "NO TOOLS"),
    "code_only": ("Code only, no model", "code", "CODE"),
    "human": ("A person decides", "human", "PERSON"),
}

# Drawing sizes, in SVG units.
CARD_W = 230
COL = CARD_W + 24  # one member position
HEAD_GAP = 56  # between a step's card and its members
RANK_GAP = 56  # between member ranks; edges turn halfway
ENTRY_H = 34  # channel above the first rank, for edges from the step
BAND_GAP = 58  # between steps; the step-to-step edge and its label
LINE = 15
WRAP = 31  # characters per small line on a card
LEFT = 24
TOP = 24


def model_name(model_id: str) -> str:
    family, major, minor = model_id.removeprefix("claude-").split("-")
    return f"{family.title()} {major}.{minor}"


def caps_text(caps: Caps) -> str:
    return "≤ " + " · ".join(caps_parts(caps))


def caps_parts(caps: Caps) -> list[str]:
    parts = []
    for count, one, many in (
        (caps.calls, "call", "calls"),
        (caps.searches, "search", "searches"),
        (caps.pages, "page", "pages"),
    ):
        if count is not None:
            parts.append(f"{count} {one if count == 1 else many}")
    if caps.seconds is not None:
        parts.append(f"{caps.seconds:g} s")
    parts += [f"${usd} {model_name(model)}" for model, usd in sorted(caps.cost_usd.items())]
    return parts


def model_text(item: Node) -> str:
    return " · ".join(model_parts(item))


def model_parts(item: Node) -> list[str]:
    if item.model is None:
        return []
    parts = [model_name(item.model)]
    if item.effort:
        parts.append(f"{item.effort} effort")
    if item.fallback:
        parts.append(f"falls back to {model_name(item.fallback)}")
    return parts


def wrap(text: str, width: int = WRAP) -> list[str]:
    lines: list[str] = []
    for word in text.split(" "):
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


def wrap_parts(parts: list[str], first: str = "", width: int = WRAP) -> list[str]:
    """Join phrases with ' · ', breaking lines only between phrases."""
    lines: list[str] = []
    for part in parts:
        if lines and len(lines[-1]) + 3 + len(part) <= width:
            lines[-1] += " · " + part
        else:
            lines.append((first if not lines else "") + part)
    return lines


def card_lines(item: Node) -> list[tuple[str, str]]:
    """The small lines under a card's title, as (CSS class, text)."""
    lines = [("id", item.id)]
    if item.model:
        lines += [("sub", line) for line in wrap_parts(model_parts(item))]
    if item.tools:
        lines += [("mono", line) for line in wrap("tools: " + ", ".join(sorted(item.tools)))]
    if item.caps:
        lines += [("sub", line) for line in wrap_parts(caps_parts(item.caps), "≤ ")]
    lines += [("io", line) for line in wrap(f"{item.input_type} → {item.output_type}")]
    if item.exits:
        lines += [("exit", line) for line in wrap("exits: " + ", ".join(item.exits))]
    return lines


@dataclass
class Band:
    """One pipeline step (or the person at the end) with its member nodes in ranks."""

    head: Node
    ranks: list[list[Node | None]] = field(default_factory=list)  # positions; None is a gap
    edges: list[tuple[str, str, str]] = field(default_factory=list)
    back: set[tuple[str, str]] = field(default_factory=set)
    rank_of: dict[str, int] = field(default_factory=dict)
    pos_of: dict[str, int] = field(default_factory=dict)


def bands() -> list[Band]:
    nodes = registry.REGISTRY
    heads = [registry.node(step) for step in PIPELINE_STEPS]
    heads += [item for item in nodes if item.kind == "person"]
    result = []
    for head in heads:
        members = [item for item in nodes if item.step == head.step and item is not head]
        ids = {head.id, *(item.id for item in members)}
        band = Band(head, edges=[f for f in registry.FLOWS if f[0] in ids and f[1] in ids])
        place(band, members)
        result.append(band)
    return result


def place(band: Band, members: list[Node]) -> None:
    """Rank members by longest path from the step, ignoring loop-back edges."""
    after: dict[str, list[str]] = defaultdict(list)
    for source, target, _ in band.edges:
        after[source].append(target)
    state: dict[str, str] = {}

    def visit(name: str) -> None:
        state[name] = "open"
        for target in after[name]:
            if state.get(target) == "open":
                band.back.add((name, target))
            elif target not in state:
                visit(target)
        state[name] = "done"

    visit(band.head.id)
    rank = {band.head.id: -1}
    for _ in members:  # at most one pass per member settles the longest paths
        for source, target, _ in band.edges:
            if (source, target) not in band.back and source in rank:
                rank[target] = max(rank.get(target, -1), rank[source] + 1)
    for item in members:
        rank.setdefault(item.id, 0)
    count = max((rank[item.id] for item in members), default=-1) + 1
    band.ranks = [[] for _ in range(count)]
    skipping = []
    for item in members:  # registry order, so the drawing is stable
        spans = [rank[t] - rank[item.id] for s, t, _ in band.edges if s == item.id]
        if any(span > 1 for span in spans):
            skipping.append(item)
        else:
            band.ranks[rank[item.id]].append(item)
    for skipper in skipping:  # beside the ranks its edge passes, so the edge runs clear
        own = rank[skipper.id]
        ahead = max(rank[t] for s, t, _ in band.edges if s == skipper.id)
        width = max(len(band.ranks[r]) for r in range(own + 1, ahead))
        row = band.ranks[own]
        row.extend([None] * max(0, width - len(row)))
        row.append(skipper)
    band.rank_of = {member.id: rank[member.id] for member in members}
    for row in band.ranks:
        for position, placed in enumerate(row):
            if placed is not None:
                band.pos_of[placed.id] = position


# --- Mermaid ------------------------------------------------------------------------------


def mermaid_label(item: Node) -> str:
    detail = PATTERNS[item.pattern][0] + (f" · {model_name(item.model)}" if item.model else "")
    return f"{item.label}<br/>{detail}".replace('"', "#quot;")


def mermaid_flow() -> str:
    lines = ["flowchart TB"]
    for pattern, (_, _, fill, stroke) in PATTERNS.items():
        lines.append(f"    classDef {pattern} fill:{fill},stroke:{stroke},color:#172030")
    for zone, (name, _, _) in ZONES.items():
        members = [item for item in registry.REGISTRY if item.trust_zone == zone]
        if not members:
            continue
        lines.append(f'    subgraph zone_{zone}["{name}"]')
        for item in members:
            label = mermaid_label(item)
            shape = {"agent": f'("{label}")', "person": f'(["{label}"])'}.get(
                item.kind, f'["{label}"]'
            )
            lines.append(f"        {item.id}{shape}")
        lines.append("    end")
    heads = [registry.node(step) for step in PIPELINE_STEPS]
    for earlier, later in itertools.pairwise(heads):
        lines.append(f'    {earlier.id} -->|"{later.input_type}"| {later.id}')
    back = {pair for band in bands() for pair in band.back}
    for source, target, handoff in registry.FLOWS:
        arrow = "-.->" if (source, target) in back else "-->"
        lines.append(f'    {source} {arrow}|"{handoff}"| {target}')
    for pattern in PATTERNS:
        ids = [item.id for item in registry.REGISTRY if item.pattern == pattern]
        if ids:
            lines.append(f"    class {','.join(ids)} {pattern}")
    return "\n".join(lines)


def compiled_mermaid() -> str:
    """The pipeline graph as LangGraph compiles it, from the same registry."""
    from adscout.pipeline.real import pipeline_graph

    def noop(self: object, state: object) -> dict[str, Any]:
        return {}

    steps = type("Steps", (), {name: noop for name in PIPELINE_STEPS})()
    return pipeline_graph(steps).get_graph().draw_mermaid().rstrip()


def agents_md() -> str:
    key = "\n".join(f"| {name} | `{pattern}` |" for pattern, (name, _, _, _) in PATTERNS.items())
    zones = "\n".join(f"| {name} | `{zone}` |" for zone, (name, _, _) in ZONES.items())
    inventory = "\n".join(
        f"| {item.id} | {model_text(item) or 'Code'} | "
        f"{', '.join(sorted(item.tools)) or 'None'} | "
        f"{caps_text(item.caps) if item.caps else 'See step/run limits'} |"
        for item in registry.REGISTRY
    )
    return f"""# Agent flow

Generated by `scripts/diagrams.py` from the agent registry
(`src/adscout/pipeline/registry.py`); do not edit by hand. To change it, change the
registry, then run `uv run --locked python scripts/diagrams.py write` and
`scripts/architecture.py stamp`. The gate fails when this file or `agent-flow.html`
differs from a fresh generation. [`agent-flow.html`](agent-flow.html) draws the same flow
with each node's model, tools, caps and typed handoffs.

## Registry flow

Groups are trust zones; colours are patterns; edge labels name the handoff types. The
dashed edge is the draft loop's rewrite.

```mermaid
{mermaid_flow()}
```

| Pattern | Registry name |
|---|---|
{key}

| Trust zone | Registry name |
|---|---|
{zones}

## Node limits

| Node | Model | Tools | Caps |
|---|---|---|---|
{inventory}

## Compiled pipeline graph

The step chain as LangGraph compiles it from the registry's steps (`draw_mermaid()`).

```mermaid
{compiled_mermaid()}
```
"""


# --- SVG ----------------------------------------------------------------------------------


@dataclass
class Box:
    x: int
    y: int
    h: int

    @property
    def cx(self) -> int:
        return self.x + CARD_W // 2


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def card_height(item: Node) -> int:
    return 16 + 14 + 20 + LINE * len(card_lines(item)) + 12


def card(item: Node, box: Box) -> list[str]:
    _, pattern, _, _ = PATTERNS[item.pattern]
    _, zone, badge = ZONES[item.trust_zone]
    tag = PATTERNS[item.pattern][0].upper()
    out = [
        f'<g class="card p-{pattern} z-{zone}">',
        f'<rect x="{box.x}" y="{box.y}" width="{CARD_W}" height="{box.h}" rx="10"/>',
        f'<text class="tag" x="{box.x + 14}" y="{box.y + 20}">{esc(tag)}</text>',
        f'<text class="badge" x="{box.x + CARD_W - 12}" y="{box.y + 20}" '
        f'text-anchor="end">{badge}</text>',
        f'<text class="ttl" x="{box.x + 14}" y="{box.y + 40}">{esc(item.label)}</text>',
    ]
    for index, (kind, text) in enumerate(card_lines(item)):
        y = box.y + 58 + index * LINE
        out.append(f'<text class="{kind}" x="{box.x + 14}" y="{y}">{esc(text)}</text>')
    out.append("</g>")
    return out


def label(x: int, y: int, text: str, anchor: str = "start") -> str:
    return f'<text class="elabel" x="{x}" y="{y}" text-anchor="{anchor}">{esc(text)}</text>'


def svg() -> str:
    parts: list[str] = []
    boxes: dict[str, Box] = {}
    members_x = LEFT + CARD_W + HEAD_GAP
    y = TOP
    width = 0
    previous: Band | None = None
    for band in bands():
        entry = any(source == band.head.id for source, _, _ in band.edges)
        items = [band.head, *(i for row in band.ranks for i in row if i is not None)]
        top = y + (ENTRY_H if entry else 0)
        boxes[band.head.id] = Box(LEFT, top, card_height(band.head))
        bottom = top + card_height(band.head)
        rank_top = top
        for row in band.ranks:  # siblings in a rank share a height
            height = max(card_height(item) for item in row if item is not None)
            for position, item in enumerate(row):
                if item is not None:
                    boxes[item.id] = Box(members_x + position * COL, rank_top, height)
            bottom = max(bottom, rank_top + height)
            rank_top += height + RANK_GAP
        loops = bool(band.back)
        right = max(box.x + CARD_W for name, box in boxes.items() if name in {i.id for i in items})
        width = max(width, right + (110 if loops else 24))
        parts.insert(
            0,
            f'<rect class="band" x="8" y="{y - 12}" width="{{WIDTH}}" '
            f'height="{bottom - y + 24}" rx="14"/>',
        )
        if previous is not None:  # the step chain, down the left column
            above, below = boxes[previous.head.id], boxes[band.head.id]
            handoff = band.head.input_type
            mid = (above.y + above.h + below.y) // 2
            parts.append(
                f'<path class="edge" d="M{above.cx} {above.y + above.h} V{below.y - 2}" '
                f'marker-end="url(#arrow)"/>'
            )
            parts.append(label(above.cx + 10, mid + 4, handoff))
        parts += edges(band, boxes)
        y = bottom + BAND_GAP
        previous = band
    for item in registry.REGISTRY:
        if item.id in boxes:
            parts += card(item, boxes[item.id])
    total_w, total_h = width, y - BAND_GAP + 24
    body = "\n".join(parts).replace("{WIDTH}", str(total_w - 16))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {total_h}" '
        f'width="{total_w}" height="{total_h}" role="img" aria-labelledby="flow-title">\n'
        '<title id="flow-title">AdScout agent flow: each pipeline step with its agents, '
        "patterns, models, tools, caps, trust zones and typed handoffs</title>\n"
        "<defs>"
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse"><path class="ah" d="M0,0 L10,5 L0,10 z"/>'
        "</marker>"
        '<marker id="arrow-loop" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse"><path class="ah-loop" '
        'd="M0,0 L10,5 L0,10 z"/></marker>'
        "</defs>\n"
        f"{body}\n</svg>"
    )


def edges(band: Band, boxes: dict[str, Box]) -> list[str]:
    out: list[str] = []
    head = boxes[band.head.id]
    labelled: set[tuple[int, str]] = set()
    for source, target, handoff in band.edges:
        if source == band.head.id and target not in band.rank_of:
            continue  # to the next band: drawn as the step chain
        to = boxes[target]
        if source == band.head.id:  # from the step, through the channel above the members
            channel = to.y - ENTRY_H // 2
            path = (
                f"M{head.x + CARD_W} {head.y + 22} H{head.x + CARD_W + 16} V{channel} "
                f"H{to.cx} V{to.y - 2}"
            )
            out.append(f'<path class="edge" d="{path}" marker-end="url(#arrow)"/>')
            out.append(label(to.cx + 8, channel - 6, handoff))
            continue
        start = boxes[source]
        if (source, target) in band.back:  # the rewrite loop, up the right side
            x = max(start.x, to.x) + CARD_W + 26
            path = (
                f"M{start.x + CARD_W} {start.y + start.h // 2} H{x} V{to.y + to.h // 2} "
                f"H{to.x + CARD_W + 2}"
            )
            out.append(f'<path class="edge loop" d="{path}" marker-end="url(#arrow-loop)"/>')
            out.append(label(x + 8, (start.y + to.y + to.h) // 2, handoff))
            continue
        channel = to.y - RANK_GAP // 2
        path = f"M{start.cx} {start.y + start.h} V{channel} H{to.cx} V{to.y - 2}"
        out.append(f'<path class="edge" d="{path}" marker-end="url(#arrow)"/>')
        if (channel, handoff) not in labelled:
            labelled.add((channel, handoff))
            out.append(label(min(start.cx, to.cx) + 8, channel - 6, handoff))
    return out


# --- the page -----------------------------------------------------------------------------

STYLE = """
/* Layout: a reading column for text; the diagram and the table run wider in their own
   scrolling frames. Colours: one token per pattern (card outline and tag), one tint per
   trust zone (card fill and badge). */
:root {
  --sans: "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "Cascadia Mono", "SF Mono", Consolas, "Liberation Mono", monospace;
  --bg: #f3f5f8; --surface: #ffffff; --band: #e9edf3; --fg: #172030; --muted: #556074;
  --line: #ccd3de; --edge: #6f7a8e;
  --seq: #3651c9; --router: #a3620a; --orch: #0d7a6f; --evalopt: #7a45b8;
  --single: #4a7a1f; --loop: #b03a2e; --code: #5b6578; --human: #b5346a;
  --z-web: #fbf1e6; --z-tools: #eef3fb; --z-code: #f2f4f7; --z-human: #fbeaf1;
  --b-web: #b45f10; --b-tools: #3651c9; --b-code: #5b6578; --b-human: #b5346a;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0e1219; --surface: #161c26; --band: #121821; --fg: #e5e9f0; --muted: #9aa4b5;
    --line: #2c3442; --edge: #8a94a6;
    --seq: #8ea3ff; --router: #e2a64a; --orch: #46c4b4; --evalopt: #b495f2;
    --single: #9ccc6a; --loop: #f08a7c; --code: #a3adbd; --human: #f17da9;
    --z-web: #241b12; --z-tools: #141d2c; --z-code: #181d26; --z-human: #2a1822;
    --b-web: #f2a25a; --b-tools: #8ea3ff; --b-code: #a3adbd; --b-human: #f17da9;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0e1219; --surface: #161c26; --band: #121821; --fg: #e5e9f0; --muted: #9aa4b5;
  --line: #2c3442; --edge: #8a94a6;
  --seq: #8ea3ff; --router: #e2a64a; --orch: #46c4b4; --evalopt: #b495f2;
  --single: #9ccc6a; --loop: #f08a7c; --code: #a3adbd; --human: #f17da9;
  --z-web: #241b12; --z-tools: #141d2c; --z-code: #181d26; --z-human: #2a1822;
  --b-web: #f2a25a; --b-tools: #8ea3ff; --b-code: #a3adbd; --b-human: #f17da9;
  color-scheme: dark;
}
body {
  background: var(--bg); color: var(--fg); font: 15px/1.6 var(--sans);
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
}
.wrap { max-width: 1400px; margin: 0 auto; padding-block: 40px 64px; display: grid; gap: 32px; }
header, section { display: grid; gap: 12px; min-width: 0; }
.eyebrow { font: 500 12px var(--mono); letter-spacing: .08em; text-transform: uppercase;
  color: var(--muted); }
h1 { font-size: clamp(28px, 5vw, 40px); line-height: 1.15; margin: 0; text-wrap: balance; }
h2 { font-size: 21px; line-height: 1.3; margin: 0; text-wrap: balance; }
p { margin: 0; max-width: 72ch; }
.lede { color: var(--muted); font-size: 16px; }
code { font: 13px var(--mono); }
.key { display: flex; flex-wrap: wrap; gap: 8px 20px; font: 12px var(--mono); color: var(--muted); }
.key span { display: inline-flex; align-items: center; gap: 8px; }
.sw { width: 14px; height: 14px; border-radius: 4px; border: 2px solid; flex: none; }
.figure, .table-wrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--line);
  border-radius: 12px; }
.figure { width: fit-content; max-width: 100%; }
.figure svg { display: block; max-width: none; height: auto; }
svg text { font-family: var(--sans); }
.band { fill: var(--band); }
.card rect { stroke-width: 1.6; }
.tag { font: 600 10px var(--mono); letter-spacing: .06em; }
.badge { font: 600 9px var(--mono); letter-spacing: .08em; }
.ttl { font-size: 15px; font-weight: 600; fill: var(--fg); }
.id, .mono { font: 11px var(--mono); fill: var(--muted); }
.sub { font-size: 12px; fill: var(--muted); }
.io { font: 11px var(--mono); fill: var(--fg); }
.exit { font: 11px var(--mono); fill: var(--human); }
.edge { fill: none; stroke: var(--edge); stroke-width: 1.5; }
.edge.loop { stroke: var(--evalopt); stroke-dasharray: 5 4; }
.ah { fill: var(--edge); }
.ah-loop { fill: var(--evalopt); }
.elabel { font: 11px var(--mono); fill: var(--muted); }
.p-seq rect { stroke: var(--seq); } .p-seq .tag { fill: var(--seq); }
.p-router rect { stroke: var(--router); } .p-router .tag { fill: var(--router); }
.p-orch rect { stroke: var(--orch); } .p-orch .tag { fill: var(--orch); }
.p-evalopt rect { stroke: var(--evalopt); } .p-evalopt .tag { fill: var(--evalopt); }
.p-single rect { stroke: var(--single); } .p-single .tag { fill: var(--single); }
.p-loop rect { stroke: var(--loop); } .p-loop .tag { fill: var(--loop); }
.p-code rect { stroke: var(--code); } .p-code .tag { fill: var(--code); }
.p-human rect { stroke: var(--human); } .p-human .tag { fill: var(--human); }
.z-web rect { fill: var(--z-web); } .z-web .badge { fill: var(--b-web); }
.z-tools rect { fill: var(--z-tools); } .z-tools .badge { fill: var(--b-tools); }
.z-code rect { fill: var(--z-code); } .z-code .badge { fill: var(--b-code); }
.z-human rect { fill: var(--z-human); } .z-human .badge { fill: var(--b-human); }
table { border-collapse: collapse; width: 100%; min-width: 980px; font-size: 13px; }
th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--line);
  vertical-align: top; }
th { font: 600 11px var(--mono); letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); }
td { font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: 0; }
.note { font-size: 13px; color: var(--muted); }
@media (max-width: 520px) { .wrap { padding-block: 24px 48px; gap: 28px; } }
""".strip()


def key() -> str:
    patterns = "".join(
        f'<span><i class="sw" style="border-color:var(--{token})"></i>{esc(name)}</span>'
        for name, token, _, _ in PATTERNS.values()
    )
    zones = "".join(
        f'<span><i class="sw" style="border-color:var(--b-{token});background:var(--z-{token})">'
        f"</i>{badge} · {esc(name)}</span>"
        for name, token, badge in ZONES.values()
    )
    return (
        f'<div class="key" aria-label="Patterns">{patterns}</div>\n'
        f'<div class="key" aria-label="Trust zones">{zones}</div>'
    )


def table() -> str:
    rows = []
    for item in registry.REGISTRY:
        cells = [
            f"<strong>{esc(item.label)}</strong><br><code>{esc(item.id)}</code>",
            esc(item.step),
            esc(PATTERNS[item.pattern][0]),
            esc(model_text(item)) or "—",
            ", ".join(f"<code>{esc(tool)}</code>" for tool in sorted(item.tools)) or "—",
            esc(caps_text(item.caps)) if item.caps else "—",
            esc(ZONES[item.trust_zone][0]),
            f"<code>{esc(item.input_type)}</code> → <code>{esc(item.output_type)}</code>",
            esc(", ".join(item.exits)) or "—",
        ]
        rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    head = "".join(
        f"<th>{name}</th>"
        for name in (
            "Node",
            "Step",
            "Pattern",
            "Model",
            "Tools",
            "Caps",
            "Trust zone",
            "Handoff in → out",
            "Exits",
        )
    )
    return (
        '<div class="table-wrap"><table>\n'
        f"<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody></table></div>"
    )


def page_body() -> str:
    agents = [item for item in registry.REGISTRY if item.kind == "agent"]
    reading = [item for item in agents if item.trust_zone == "untrusted_content"]
    tooled = [item for item in agents if item.tools]
    return f"""<div class="wrap">
<header>
<div class="eyebrow">Generated from the agent registry · Phase 2 as built</div>
<h1>AdScout Agent Architecture</h1>
<p class="lede">Every step AdScout runs for a company, the {len(agents)} agents inside them,
and what each one may do: its pattern, model, tools, caps and trust zone, and the typed
handoff it passes on. Code chooses every route; no model decides what runs next.</p>
{key()}
</header>
<section aria-labelledby="h-flow">
<h2 id="h-flow">The flow</h2>
<p>Steps run top to bottom for each company. Inside a step, arrows carry the handoff type
they are labelled with; the dashed arrow is the draft loop's rewrite. Card outlines name the
pattern, fills and badges the trust zone. Exits are recorded with their reason.</p>
<div class="figure">
{svg()}
</div>
</section>
<section aria-labelledby="h-nodes">
<h2 id="h-nodes">Every node</h2>
<p>The registry as a table. The model adapter refuses any request whose tools differ from
its role's entry here, and no node holds a tool that sends, writes to the CRM or writes
files.</p>
{table()}
<p class="note">{len(reading)} of {len(agents)} agents read untrusted content and so see no
private data; {len(tooled)} hold tools, all of them read-only. Generated by
<code>scripts/diagrams.py</code> from <code>src/adscout/pipeline/registry.py</code>; the
gate fails when this page differs from a fresh generation.</p>
</section>
</div>"""


def page_head() -> str:
    return (
        "<title>AdScout Agent Architecture</title>\n"
        '<meta name="claude:viewport-fit-sides" content="cover">\n'
        f"<style>\n{STYLE}\n</style>"
    )


def artifact_page() -> str:
    """The page as the artifact service takes it: it adds the document wrapper itself."""
    return f"{page_head()}\n{page_body()}\n"


def agent_flow_html() -> str:
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f"{page_head()}\n</head>\n<body>\n{page_body()}\n</body>\n</html>\n"
    )


def generated() -> dict[str, str]:
    return {AGENTS_MD: agents_md(), AGENT_FLOW: agent_flow_html()}


def check(folder: Path = FOLDER) -> list[str]:
    """Files that differ from a fresh generation; empty when both match."""
    problems = []
    for name, text in generated().items():
        path = folder / name
        if not path.exists():
            problems.append(f"{name} is missing; {REGENERATE}")
        elif path.read_bytes().replace(b"\r\n", b"\n") != text.encode("utf-8"):
            problems.append(f"{name} is stale; {REGENERATE}")
    return problems


def main(argv: list[str]) -> int:
    if argv == ["write"]:
        for name, text in generated().items():
            (FOLDER / name).write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {(FOLDER / name).relative_to(ROOT)}")
        return 0
    if argv == ["check"]:
        problems = check()
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    if len(argv) == 2 and argv[0] == "artifact":
        Path(argv[1]).write_text(artifact_page(), encoding="utf-8", newline="\n")
        print(f"wrote {argv[1]}")
        return 0
    print("usage: python scripts/diagrams.py write|check|artifact OUT")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
