"""`adscout trace`: each lead's span tree, read from the database alone.

A lead's trace holds one `step` span per step that did work for it; agent spans nest under
their step, and model calls (`chat`) and source calls (`execute_tool`) under the span that
made them. Nothing here reads the replay cache or a page, so the tree survives both.
"""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Node:
    span_id: str
    parent: str | None
    # Start, end, then write order: times have millisecond resolution, so fast calls tie.
    order: tuple[str, str, int]
    text: str
    children: list["Node"] = field(default_factory=list)


def millis(started_at: str, ended_at: str) -> int:
    started = datetime.fromisoformat(started_at)
    return round((datetime.fromisoformat(ended_at) - started).total_seconds() * 1000)


def span_text(row: sqlite3.Row) -> str:
    took = f"{millis(row['started_at'], row['ended_at'])} ms"
    failed = "" if row["status"] == "succeeded" else f" [{row['status']}]"
    if row["operation"] == "step":
        return f"{row['step']} step, {took}: {row['detail']}{failed}"
    version = f" {row['role_version']}" if row["role_version"] else ""
    return f"invoke_agent {row['agent_name']}{version}, {took}{failed}"


def chat_text(row: sqlite3.Row) -> str:
    cached = (row["cache_read_tokens"] or 0) + (row["cache_write_tokens"] or 0)
    tokens = (
        f"in {row['input_tokens']} (+{cached} cached), out {row['output_tokens']}"
        if row["input_tokens"] is not None
        else "no tokens"
    )
    searches = f", {row['web_search_requests']} searches" if row["web_search_requests"] else ""
    took = f"{row['latency_ms']} ms" if row["latency_ms"] is not None else "no latency"
    outcome = row["stop_reason"] or row["error_category"] or row["status"]
    extra = "" if row["call_role"] == "primary" else f" ({row['call_role']})"
    return (
        f"chat {row['model']}{extra} [{row['agent_name']}], {tokens}{searches}, "
        f"${row['cost_usd']:.6f}, {took}, {outcome}"
    )


def tool_text(row: sqlite3.Row) -> str:
    status = f"HTTP {row['http_status']}" if row["http_status"] else row["status"]
    return (
        f"execute_tool {row['kind']} {row['target']}, {status}, "
        f"{millis(row['started_at'], row['ended_at'])} ms"
    )


def order(row: sqlite3.Row, nodes: list[Node]) -> tuple[str, str, int]:
    return (row["started_at"], row["ended_at"], len(nodes))


def lead_nodes(connection: sqlite3.Connection, run_id: str, lead_id: str) -> list[Node]:
    """The lead's step spans, each with its subtree, in time order."""
    nodes: list[Node] = []
    for row in connection.execute(
        "SELECT s.*, (SELECT min(m.prompt_version) FROM model_calls AS m "
        "WHERE m.parent_span_id = s.span_id) AS role_version "
        "FROM spans AS s WHERE s.run_id = ? AND s.lead_id = ? ORDER BY s.rowid",
        (run_id, lead_id),
    ):
        nodes.append(Node(row["span_id"], row["parent_span_id"], order(row, nodes), span_text(row)))
    for row in connection.execute(
        "SELECT * FROM model_calls WHERE run_id = ? AND lead_id = ? ORDER BY rowid",
        (run_id, lead_id),
    ):
        nodes.append(Node(row["span_id"], row["parent_span_id"], order(row, nodes), chat_text(row)))
    for row in connection.execute(
        "SELECT * FROM source_calls WHERE run_id = ? AND lead_id = ? ORDER BY rowid",
        (run_id, lead_id),
    ):
        nodes.append(Node(row["span_id"], row["parent_span_id"], order(row, nodes), tool_text(row)))
    by_id = {node.span_id: node for node in nodes}
    children: dict[str | None, list[Node]] = defaultdict(list)
    for node in nodes:
        # A parent missing from the run would hide its subtree; show it at the top instead
        # (`adscout check` reports it).
        children[node.parent if node.parent in by_id else None].append(node)
    for node in nodes:
        node.children = sorted(children[node.span_id], key=lambda n: n.order)
    return sorted(children[None], key=lambda n: n.order)


def render(nodes: list[Node], prefix: str = "") -> list[str]:
    lines = []
    for index, node in enumerate(nodes):
        last = index == len(nodes) - 1
        lines.append(f"{prefix}{'└─ ' if last else '├─ '}{node.text}")
        lines += render(node.children, prefix + ("   " if last else "│  "))
    return lines


def trace_text(connection: sqlite3.Connection, run_id: str, domain: str | None = None) -> str:
    if connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone() is None:
        raise LookupError(f"no run {run_id}")
    leads = connection.execute(
        "SELECT o.lead_id, c.domain, min(o.outcome_id) AS first FROM lead_step_outcomes AS o "
        "JOIN leads AS l ON l.lead_id = o.lead_id "
        "JOIN companies AS c ON c.company_id = l.company_id "
        "WHERE o.run_id = ? AND (? IS NULL OR c.domain = ?) "
        "GROUP BY o.lead_id, c.domain ORDER BY first",
        (run_id, domain, domain),
    ).fetchall()
    if not leads:
        raise LookupError(
            f"no lead {domain} in run {run_id}" if domain else f"no leads in {run_id}"
        )
    blocks = []
    for lead in leads:
        last = connection.execute(
            "SELECT step, outcome, coalesce(reason, flag, '') AS code, detail "
            "FROM lead_step_outcomes WHERE run_id = ? AND lead_id = ? "
            "ORDER BY outcome_id DESC LIMIT 1",
            (run_id, lead["lead_id"]),
        ).fetchone()
        code = f" {last['code']}" if last["code"] else ""
        header = (
            f"{lead['domain']} (lead {lead['lead_id']}, trace {lead['lead_id'].replace('-', '')})"
            f"\n  last outcome: {last['step']} {last['outcome']}{code}: {last['detail']}"
        )
        nodes = lead_nodes(connection, run_id, lead["lead_id"])
        tree = render(nodes, "  ") if nodes else ["  no spans: no model or source call"]
        blocks.append("\n".join([header, *tree]))
    return "\n\n".join(blocks)
