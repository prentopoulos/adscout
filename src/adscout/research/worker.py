"""One research worker's tool loop: search, fetch, submit, inside its caps (decisions 25, 28).

The loop is ours, on the adapter: each turn is one model call with the role's exact tools.
Claude's server web search runs inside a call; `fetch_page` and `submit_findings` are client
tools this code answers. `fetch_page` reads a URL only if it came from this worker's search
results or the task's seed URLs, or is on the company's own site, and never a blocked
domain; the polite fetcher then applies its egress rules and robots.txt. A refused fetch is
recorded and answered as an error, and nothing is sent.

Caps (the worker's and the lead's, shared by the workers under a lock): model calls,
searches, pages, seconds and cost. Near a cap the worker is told to submit; a Haiku worker's
last turn forces `submit_findings`. A worker that ends without findings has failed; the
others' findings stand (ASI08).
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from adscout.enrichment.pages import text_of
from adscout.enrichment.search import audit_searches, web_search_tool
from adscout.llm.adapter import CallContext, ModelAdapter, ModelCallFailed, ModelRequest
from adscout.llm.invoke import HAIKU
from adscout.llm.prompts import Prompt, data_block, fixed_system, neutralize
from adscout.pipeline.registry import Caps, Node
from adscout.research.handoffs import WorkerFindings, WorkerTask
from adscout.research.verifier import FetchedPage, normalize_url
from adscout.sources.fetcher import Fetcher, FetchFailed, FetchRefused, SourceContext
from adscout.sources.urls import BLOCKED_DOMAINS, on_site

MAX_TOKENS = 2_000
PAGE_CHARS = 12_000  # about 4K tokens
FINAL_NOTE = "Your limits are reached: call submit_findings now with what you have."
NUDGE = "Call submit_findings now with your claims and gaps."
FETCH_TOOL: dict[str, Any] = {
    "name": "fetch_page",
    "description": (
        "Read a web page's text. Use only URLs from your search results, the task's seed "
        "URLs, or pages on the company's own site."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
        "additionalProperties": False,
    },
    "strict": True,
}


class LeadBudget:
    """The per-lead research caps, shared by the workers of one lead under a lock."""

    def __init__(self, caps: Caps, model: str) -> None:
        self.caps = caps
        self.cost_cap = caps.cost_usd.get(model)
        self.calls = self.searches = self.pages = 0
        self.cost = Decimal(0)
        self.hit: set[str] = set()
        self._lock = threading.Lock()

    def room(self) -> list[str]:
        """The caps already reached."""
        with self._lock:
            reached = []
            if self.caps.calls is not None and self.calls >= self.caps.calls:
                reached.append("lead calls")
            if self.caps.searches is not None and self.searches >= self.caps.searches:
                reached.append("lead searches")
            if self.cost_cap is not None and self.cost >= self.cost_cap:
                reached.append("lead cost")
            self.hit.update(reached)
            return reached

    def take_page(self) -> bool:
        with self._lock:
            if self.caps.pages is not None and self.pages >= self.caps.pages:
                self.hit.add("lead pages")
                return False
            self.pages += 1
            return True

    def add(self, *, calls: int = 0, searches: int = 0, cost: Decimal = Decimal(0)) -> None:
        with self._lock:
            self.calls += calls
            self.searches += searches
            self.cost += cost


@dataclass
class WorkerRun:
    worker: str
    findings: WorkerFindings | None = None
    pages: dict[str, FetchedPage] = field(default_factory=dict)
    calls: int = 0
    searches: int = 0
    pages_read: int = 0
    cost: Decimal = Decimal(0)
    caps_hit: list[str] = field(default_factory=list)
    failure: str | None = None

    @property
    def failed(self) -> bool:
        return self.findings is None


@dataclass
class Worker:
    """Runs one worker node's loop for one task."""

    node: Node
    prompt: Prompt
    adapter: ModelAdapter
    fetcher: Fetcher
    lead_budget: LeadBudget
    run_id: str
    clock: Callable[[], float] = time.monotonic

    def tools(self, searches_left: int) -> list[Any]:
        submit = {
            "name": "submit_findings",
            "description": "Hand back your claims and gaps. Call it once, at the end.",
            "input_schema": self.prompt.schema,
            "strict": True,
        }
        return [web_search_tool(max(1, searches_left)), FETCH_TOOL, submit]

    def run(self, task: WorkerTask, parent_span_id: str) -> WorkerRun:
        caps = self.node.caps or Caps()
        model = self.node.model or HAIKU
        cost_cap = caps.cost_usd.get(model)
        result = WorkerRun(self.node.id)
        context = CallContext(
            run_id=self.run_id,
            step="research",
            lead_id=task.lead_id,
            role=self.node.id,
            agent_name=self.node.id,
            prompt_version=self.prompt.version,
            parent_span_id=parent_span_id,
            allowed_tools=self.node.tools,
        )
        sources = SourceContext(self.run_id, "research", task.lead_id, parent_span_id)
        allowed = {normalize_url(url) for url in task.seed_urls}
        # Assistant turns go back exactly as the API returned them (SDK block dumps).
        messages: list[Any] = [
            {"role": "user", "content": data_block("task", task.model_dump(mode="json"))}
        ]
        started, nudged, told_final = self.clock(), False, False
        while True:
            reached = self._reached(result, caps, cost_cap, started)
            if reached and (told_final or result.calls >= (caps.calls or 10**9)):
                result.caps_hit = sorted(set(reached))
                result.failure = f"stopped at {', '.join(result.caps_hit)} without findings"
                return result
            final = bool(reached) or result.calls + 1 >= (caps.calls or 10**9)
            if final and not told_final:
                messages = _with_note(messages, FINAL_NOTE)
                told_final = True
                result.caps_hit = sorted(set(reached))
            searches_left = (caps.searches or 1) - result.searches
            request = ModelRequest(
                model=model,
                max_tokens=MAX_TOKENS,
                system=fixed_system(self.prompt.text),
                messages=messages,
                tools=self.tools(searches_left),
                effort=self.node.effort,
                tool_choice=(
                    {"type": "tool", "name": "submit_findings"}
                    if final and model == HAIKU
                    else None
                ),
            )
            try:
                answer = self.adapter.call(request, context)
            except ModelCallFailed as error:
                result.failure = f"model call failed: {error}"
                return result
            searched = answer.usage.web_search_requests
            result.calls += 1
            result.searches += searched
            result.cost += answer.cost_usd
            self.lead_budget.add(calls=1, searches=searched, cost=answer.cost_usd)
            blocks = [block.model_dump(exclude_none=True) for block in answer.message.content]
            for _, urls in audit_searches(self.adapter, context, answer, blocks):
                allowed.update(normalize_url(url) for url in urls)
            messages = [*messages, {"role": "assistant", "content": blocks}]
            if answer.message.stop_reason == "pause_turn":
                continue
            uses = [block for block in blocks if block.get("type") == "tool_use"]
            replies: list[dict[str, Any]] = []
            for use in uses:
                if use.get("name") == "submit_findings":
                    try:
                        result.findings = WorkerFindings.model_validate(
                            {
                                "worker": self.node.id,
                                **use.get("input", {}),
                                "stopped_because": ", ".join(result.caps_hit) or "submitted",
                            }
                        )
                    except ValueError as error:
                        replies.append(_reply(use, f"Invalid findings: {error}", error=True))
                        continue
                    return result
                if use.get("name") == "fetch_page":
                    replies.append(self._fetch(use, task, allowed, sources, caps, result))
            if not uses:
                if nudged:
                    result.failure = "ended without submitting findings"
                    return result
                nudged = True
                messages = [*messages, {"role": "user", "content": NUDGE}]
                continue
            messages = [*messages, {"role": "user", "content": replies}]

    def _reached(
        self, result: WorkerRun, caps: Caps, cost_cap: Decimal | None, started: float
    ) -> list[str]:
        reached = self.lead_budget.room()
        if caps.calls is not None and result.calls >= caps.calls:
            reached.append("worker calls")
        if caps.searches is not None and result.searches >= caps.searches:
            reached.append("worker searches")
        if caps.seconds is not None and self.clock() - started >= caps.seconds:
            reached.append("worker time")
        if cost_cap is not None and result.cost >= cost_cap:
            reached.append("worker cost")
        return reached

    def _fetch(
        self,
        use: dict[str, Any],
        task: WorkerTask,
        allowed: set[str],
        sources: SourceContext,
        caps: Caps,
        result: WorkerRun,
    ) -> dict[str, Any]:
        url = str(use.get("input", {}).get("url", ""))
        host = (urlsplit(url).hostname or "").lower()
        problem = None
        if any(host == blocked or host.endswith(f".{blocked}") for blocked in BLOCKED_DOMAINS):
            problem = f"{host} is a blocked domain"
        elif normalize_url(url) not in allowed and not on_site(url, task.domain):
            problem = "this URL did not come from your searches, the seed URLs or the company site"
        elif caps.pages is not None and result.pages_read >= caps.pages:
            problem = "your page limit is reached"
            result.caps_hit = sorted({*result.caps_hit, "worker pages"})
        elif not self.lead_budget.take_page():
            problem = "this company's page limit is reached"
        if problem is not None:
            self.fetcher.refuse(url or "(no URL)", sources, f"fetch_page refused: {problem}")
            return _reply(use, f"Not fetched: {problem}.", error=True)
        result.pages_read += 1
        try:
            page = self.fetcher.fetch(url, sources, site=host.removeprefix("www."))
        except (FetchRefused, FetchFailed) as error:
            return _reply(use, f"Not fetched: {error}", error=True)
        text = text_of(page.text)
        result.pages[normalize_url(url)] = FetchedPage(url, text, page.call_id)
        if page.final_url != url:
            result.pages[normalize_url(page.final_url)] = FetchedPage(
                page.final_url, text, page.call_id
            )
        body = neutralize(text[:PAGE_CHARS], "page")
        return _reply(use, f'<page url="{page.final_url}">\n{body}\n</page>')


def _reply(use: dict[str, Any], content: str, *, error: bool = False) -> dict[str, Any]:
    reply: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": use.get("id"),
        "content": content,
    }
    if error:
        reply["is_error"] = True
    return reply


def _with_note(messages: list[Any], note: str) -> list[Any]:
    """The note added to the last user turn, or as a new one after an assistant turn."""
    last = messages[-1]
    if last["role"] == "user":
        content = last["content"]
        blocks: list[Any] = (
            content if isinstance(content, list) else [{"type": "text", "text": content}]
        )
        return [
            *messages[:-1],
            {"role": "user", "content": [*blocks, {"type": "text", "text": note}]},
        ]
    return [*messages, {"role": "user", "content": note}]
