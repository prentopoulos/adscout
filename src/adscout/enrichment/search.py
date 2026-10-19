"""At most one server web search per company, for launches its pages did not name (decision 8).

The model gets Claude's server `web_search` tool, pinned to the basic version with direct
callers only (no hidden code execution), one use, the blocked domains and a US location,
and a strict client tool `submit_launches` to hand back what the results state. Each search
gets a `source_calls` audit row with its query and result URLs at $0; its fee is on the
model call. A launch citing a URL that was not among the results is dropped.
"""

import json
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from anthropic.types import MessageParam

from adscout.config import SegmentConfig
from adscout.db.connection import utc_now
from adscout.enrichment.fields import Candidate, Checked, check
from adscout.ids import uuid7
from adscout.llm.adapter import (
    CallContext,
    Effort,
    ModelAdapter,
    ModelRequest,
    ModelResult,
    new_span_id,
)
from adscout.llm.prompts import Prompt, fixed_system, neutralize
from adscout.sources.fetcher import SourceCallRecord
from adscout.sources.urls import BLOCKED_DOMAINS

SEARCH_TOOL = "web_search_20250305"
SUBMIT = "submit_launches"
MAX_TOKENS = 1_500
EFFORT: Effort = "low"


@dataclass(frozen=True)
class SearchOutcome:
    rows: list[Checked]
    note: str


def web_search_tool(max_uses: int) -> dict[str, Any]:
    return {
        "type": SEARCH_TOOL,
        "name": "web_search",
        "max_uses": max_uses,
        "allowed_callers": ["direct"],
        "blocked_domains": list(BLOCKED_DOMAINS),
        "user_location": {"type": "approximate", "country": "US"},
    }


def search_request(prompt: Prompt, name: str, domain: str, model: str) -> ModelRequest:
    submit: dict[str, Any] = {
        "name": SUBMIT,
        "description": "Hand back the launches the search results state, with their URLs.",
        "input_schema": prompt.schema,
        "strict": True,
    }
    company = neutralize(f"{name} ({domain})", "company")
    messages: list[MessageParam] = [{"role": "user", "content": f"<company>{company}</company>"}]
    return ModelRequest(
        model=model,
        max_tokens=MAX_TOKENS,
        system=fixed_system(prompt.text),
        messages=messages,
        tools=[web_search_tool(1), submit],  # type: ignore[list-item]
        effort=EFFORT,
    )


def search_launches(
    adapter: ModelAdapter,
    prompt: Prompt,
    segment: SegmentConfig,
    name: str,
    domain: str,
    context: CallContext,
    today: date,
    model: str,
) -> SearchOutcome:
    request = search_request(prompt, name, domain, model)
    result = adapter.call(request, context)
    if result.message.stop_reason == "pause_turn":
        # The server paused its tool loop; re-send the turn once so it can finish.
        paused: list[MessageParam] = [
            *request.messages,
            {"role": "assistant", "content": [b.model_dump() for b in result.message.content]},  # type: ignore[misc]
        ]
        result = adapter.call(replace(request, messages=paused), context, "retry")
    blocks = [block.model_dump() for block in result.message.content]
    audits = _audit(adapter, context, result, blocks)
    allowed = {url: call_id for call_id, urls in audits for url in urls}
    launches = next(
        (
            block.get("input", {}).get("launches")
            for block in blocks
            if block.get("type") == "tool_use" and block.get("name") == SUBMIT
        ),
        None,
    )
    if not isinstance(launches, list):
        return SearchOutcome([], "the launch search submitted nothing")
    now = utc_now()
    rows: list[Checked] = []
    for url in sorted({str(item.get("source_url")) for item in launches if isinstance(item, dict)}):
        items = [item for item in launches if str(item.get("source_url")) == url]
        candidate = Candidate(
            field="recent_launches",
            value=items,
            source_url=url,
            source_kind="web_search",
            method="extracted",
            retrieved_at=now,
            source_call_id=allowed.get(url),
            model_call_id=result.call_id,
        )
        if url not in allowed:
            rows.append(Checked(candidate, items, "dropped", "not among the search results"))
        else:
            rows.extend(check(candidate, segment.categories, today))
    return SearchOutcome(rows, f"one web search; {len(launches)} launches submitted")


def _audit(
    adapter: ModelAdapter, context: CallContext, result: ModelResult, blocks: list[dict[str, Any]]
) -> list[tuple[str, list[str]]]:
    """One `source_calls` row per search, at $0; returns each row's ID and result URLs."""
    queries = {
        block.get("id"): str(block.get("input", {}).get("query", ""))
        for block in blocks
        if block.get("type") == "server_tool_use" and block.get("name") == "web_search"
    }
    mode = "fixture" if adapter.mode == "fake" else adapter.mode
    found = []
    for block in blocks:
        if block.get("type") != "web_search_tool_result":
            continue
        content = block.get("content")
        ok = isinstance(content, list)
        results = [
            {"url": item.get("url"), "title": item.get("title"), "page_age": item.get("page_age")}
            for item in (content if isinstance(content, list) else [])
            if isinstance(item, dict)
        ]
        call_id = str(uuid7())
        query = queries.get(block.get("tool_use_id")) or "(query not shown)"
        adapter.sink.add(
            SourceCallRecord(
                call_id=call_id,
                run_id=context.run_id,
                step=context.step,
                lead_id=context.lead_id,
                kind="web_search",
                target=query,
                mode=mode,
                status="succeeded" if ok else "failed",
                robots_decision=None,
                http_status=None,
                bytes=None,
                content_sha256=None,
                results_json=json.dumps(results, sort_keys=True),
                model_call_id=result.call_id,
                detail="ok" if ok else f"search error: {content}",
                latency_ms=None,
                trace_id=context.trace_id,
                span_id=new_span_id(),
                parent_span_id=result.span_id,
                started_at=utc_now(),
                ended_at=utc_now(),
            )
        )
        found.append((call_id, [str(item["url"]) for item in results if item["url"]]))
    return found
