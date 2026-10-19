"""The real `research` step for one qualified lead (design decisions 24 to 29).

Multi-agent (the default): the lead plans questions, LangGraph fans the three workers out
with `Send` (at most three model calls at once), code verifies every claim against the
pages fetched for this lead, and the lead merges the verified claims into summary points.
Single-agent (`--research-design single`, the baseline): one Sonnet agent with the same
tools, verifier and schema, under the same total budget, researches all three topics.

A lead with no verified claim, or whose workers all failed, exits as `research_failed` for
a person, keeping a failed brief. A brief with any cap hit, failed worker, uncovered topic
or failed merge is kept with the flag `research_partial`. Budget stops end the run.
"""

import json
import operator
import sqlite3
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from adscout.db.connection import utc_now
from adscout.llm.adapter import CallContext, ModelAdapter
from adscout.llm.budget import BudgetExhausted
from adscout.llm.invoke import CallsFailed
from adscout.llm.prompts import Prompt
from adscout.pipeline.contexts import planner_context
from adscout.pipeline.contracts import Lead, Outcome
from adscout.pipeline.registry import LEAD_RESEARCH_CAPS, SINGLE_CAPS, WORKERS, node
from adscout.research.handoffs import TOPICS, Brief, Design, SummaryPoint, VerifiedClaim, WorkerTask
from adscout.research.lead import DEFAULT_QUESTIONS, merge, plan
from adscout.research.verifier import VERIFIER_VERSION, FetchedPage, drop_reason, verify
from adscout.research.worker import LeadBudget, Worker, WorkerRun
from adscout.sources.fetcher import Fetcher
from adscout.spans import Span, step_span

MAX_PARALLEL = 3  # design decision 37
MAX_SEEDS = 5
WITHHELD = "(withheld: the claim names a person)"


class FanOut(TypedDict):
    tasks: list[WorkerTask]
    parent: str
    run_id: str
    budget: LeadBudget
    runs: Annotated[list[WorkerRun], operator.add]


class WorkerInput(TypedDict):
    task: WorkerTask
    parent: str
    run_id: str
    budget: LeadBudget


@dataclass(frozen=True)
class Researched:
    lead: Lead
    brief: Brief
    claims: list[VerifiedClaim]
    runs: list[WorkerRun]
    outcome: Outcome
    lead_caps_hit: list[str]
    notes: list[str]


def seed_urls(domain: str, fields: dict[str, Any]) -> list[str]:
    """Starting pages from enrichment, chosen by code: the home page and launch sources."""
    urls = [f"https://{domain}/"]
    for launch in fields.get("recent_launches") or []:
        url = launch.get("source_url") if isinstance(launch, dict) else None
        if isinstance(url, str) and url.startswith("https://") and url not in urls:
            urls.append(url)
    return urls[:MAX_SEEDS]


@dataclass
class Researcher:
    adapter: ModelAdapter
    fetcher: Fetcher
    prompts: dict[str, Prompt]
    design: Design = "multi"
    clock: Callable[[], float] = time.monotonic
    graph: CompiledStateGraph[FanOut, None, FanOut, FanOut] = field(init=False)

    def __post_init__(self) -> None:
        self.graph = self._fan_out_graph()

    def _fan_out_graph(self) -> CompiledStateGraph[FanOut, None, FanOut, FanOut]:
        def dispatch(state: FanOut) -> list[Send]:
            return [
                Send(
                    "work",
                    WorkerInput(
                        task=task,
                        parent=state["parent"],
                        run_id=state["run_id"],
                        budget=state["budget"],
                    ),
                )
                for task in state["tasks"]
            ]

        def work(state: WorkerInput) -> dict[str, list[WorkerRun]]:
            return {"runs": [self._run_worker(state)]}

        builder = StateGraph(FanOut)
        builder.add_node("work", work)
        builder.add_conditional_edges(START, dispatch, ["work"])
        builder.add_edge("work", END)
        return builder.compile(name="research_workers")

    def _run_worker(self, state: WorkerInput) -> WorkerRun:
        task = state["task"]
        agent_node = node(task.worker)
        span = Span(
            state["run_id"], task.lead_id, "research", "invoke_agent", state["parent"], task.worker
        )
        worker = Worker(
            agent_node,
            self.prompts[agent_node.prompt or ""],
            self.adapter,
            self.fetcher,
            state["budget"],
            state["run_id"],
            self.clock,
        )
        try:
            run = worker.run(task, span.span_id)
        except BudgetExhausted:
            raise  # a budget stop ends the run
        except Exception as error:
            # One worker's crash must not take the others with it (ASI08).
            run = WorkerRun(task.worker, failure=f"worker crashed: {error!r}")
        self.adapter.sink.add(
            span.close("failed" if run.failed else "succeeded", run.failure or "findings submitted")
        )
        return run

    def research(self, lead: Lead, fields: dict[str, Any], run_id: str) -> Researched:
        span = step_span(run_id, lead.lead_id, "research")
        notes: list[str] = []
        seeds = seed_urls(lead.domain, fields)
        if self.design == "multi":
            questions = self._plan(lead, fields, run_id, span, notes)
            budget = LeadBudget(LEAD_RESEARCH_CAPS, node("worker_ads").model or "")
            tasks = [
                WorkerTask(
                    lead_id=lead.lead_id,
                    worker=worker,
                    topics=[topic],
                    company=lead.name,
                    domain=lead.domain,
                    questions=questions[worker],
                    seed_urls=seeds,
                )
                for worker, (_label, topic) in WORKERS.items()
            ]
        else:
            budget = LeadBudget(SINGLE_CAPS, node("research_single").model or "")
            tasks = [
                WorkerTask(
                    lead_id=lead.lead_id,
                    worker="research_single",
                    topics=list(TOPICS),
                    company=lead.name,
                    domain=lead.domain,
                    questions=[q for qs in DEFAULT_QUESTIONS.values() for q in qs],
                    seed_urls=seeds,
                )
            ]
        state = self.graph.invoke(
            FanOut(tasks=tasks, parent=span.span_id, run_id=run_id, budget=budget, runs=[]),
            {"max_concurrency": MAX_PARALLEL, "recursion_limit": 10},
            version="v2",
        ).value
        runs = sorted(state["runs"], key=lambda run: [t.worker for t in tasks].index(run.worker))
        researched = self._brief(lead, runs, run_id, span, notes, budget)
        self.adapter.sink.add(span.close("succeeded", researched.outcome.detail))
        return researched

    def _plan(
        self, lead: Lead, fields: dict[str, Any], run_id: str, span: Span, notes: list[str]
    ) -> dict[str, list[str]]:
        agent = span.child("research_plan")
        lead_node = node("research_plan")
        questions, note = plan(
            self.adapter,
            self.prompts["research_plan"],
            lead_node,
            planner_context(lead, fields),
            self._context(run_id, lead, "research_plan", agent.span_id),
        )
        if note:
            notes.append(note)
        self.adapter.sink.add(agent.close("failed" if note else "succeeded", note or "planned"))
        return questions

    def _brief(
        self,
        lead: Lead,
        runs: Sequence[WorkerRun],
        run_id: str,
        span: Span,
        notes: list[str],
        budget: LeadBudget,
    ) -> Researched:
        fetched: dict[str, FetchedPage] = {}
        for run in runs:
            fetched.update(run.pages)
        claims: list[VerifiedClaim] = []
        for run in runs:
            if run.findings is not None:
                claims.extend(verify(run.worker, run.findings.claims, fetched, lead.name))
        kept = [claim for claim in claims if claim.verified]
        budget_hit = sorted(budget.hit)
        caps_hit = sorted({*budget_hit, *(cap for run in runs for cap in run.caps_hit)})
        gaps = [gap for run in runs if run.findings for gap in run.findings.gaps]
        gaps += [f"{run.worker} failed: {run.failure}" for run in runs if run.failed]
        if not kept or all(run.failed for run in runs):
            why = "every worker failed" if all(r.failed for r in runs) else "no claim was verified"
            brief = Brief(status="failed", design=self.design, gaps=gaps, caps_hit=caps_hit)
            outcome = Outcome(
                lead_id=lead.lead_id,
                outcome="exited",
                reason="research_failed",
                detail=f"research failed: {why}; {len(claims)} claims emitted; for a person",
            )
            return Researched(lead, brief, claims, list(runs), outcome, budget_hit, notes)
        points: list[SummaryPoint] = []
        agent = span.child("research_merge")
        try:
            points = merge(
                self.adapter,
                self.prompts["research_merge"],
                node("research_merge"),
                kept,
                self._context(run_id, lead, "research_merge", agent.span_id),
            )
            self.adapter.sink.add(agent.close("succeeded", f"{len(points)} points"))
        except CallsFailed as error:
            gaps.append(f"merge failed: {error}")
            self.adapter.sink.add(agent.close("failed", "merge failed"))
        covered = {claim.claim.topic for claim in kept}
        uncovered = [topic for topic in TOPICS if topic not in covered]
        gaps += [f"no verified claim on {topic}" for topic in uncovered]
        partial = bool(caps_hit or any(r.failed for r in runs) or uncovered or not points)
        brief = Brief(
            status="partial" if partial else "complete",
            design=self.design,
            summary_points=points,
            claim_ids=[claim.claim_id for claim in kept],
            gaps=gaps,
            caps_hit=caps_hit,
        )
        detail = f"{len(kept)} of {len(claims)} claims verified; brief {brief.status}"
        outcome = Outcome(
            lead_id=lead.lead_id,
            outcome="kept",
            flag="research_partial" if partial else None,
            detail=detail,
        )
        return Researched(lead, brief, claims, list(runs), outcome, budget_hit, notes)

    def _context(self, run_id: str, lead: Lead, agent: str, parent: str) -> CallContext:
        return CallContext(
            run_id=run_id,
            step="research",
            lead_id=lead.lead_id,
            role=agent,
            agent_name=agent,
            prompt_version=self.prompts[node(agent).prompt or ""].version,
            parent_span_id=parent,
            allowed_tools=node(agent).tools,
        )


def store(connection: sqlite3.Connection, run_id: str, researched: Researched) -> int:
    """The lead's `briefs` row and one `claims` row per emitted claim; returns the brief ID."""
    brief = researched.brief
    caps = {
        "lead": researched.lead_caps_hit,
        "workers": {
            run.worker: {
                "calls": run.calls,
                "searches": run.searches,
                "pages": run.pages_read,
                "cost_usd": str(run.cost),
                "caps_hit": run.caps_hit,
                "failure": run.failure,
            }
            for run in researched.runs
        },
    }
    dropped = sum(not claim.verified for claim in researched.claims)
    cursor = connection.execute(
        "INSERT INTO briefs (lead_id, run_id, implementation, status, summary, claims_json, "
        "created_at, design, summary_points_json, gaps_json, caps_json, dropped_claims, "
        "verifier_version) VALUES (?, ?, 'real', ?, ?, '[]', ?, ?, ?, ?, ?, ?, ?)",
        (
            researched.lead.lead_id,
            run_id,
            brief.status,
            "\n".join(f"- {p.text} [{', '.join(p.claim_ids)}]" for p in brief.summary_points),
            utc_now(),
            brief.design,
            json.dumps([p.model_dump() for p in brief.summary_points], sort_keys=True),
            json.dumps(brief.gaps),
            json.dumps(caps, sort_keys=True),
            dropped,
            VERIFIER_VERSION,
        ),
    )
    brief_id = int(cursor.lastrowid or 0)
    for claim in researched.claims:
        withheld = claim.names_individual
        connection.execute(
            "INSERT INTO claims (brief_id, claim_key, agent_name, topic, text, source_url, "
            "quote, fetch_call_id, url_fetched_in_run, quote_found, numbers_ok, "
            "names_individual, carries_link, verified, drop_reason, verifier_version, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                brief_id,
                claim.claim_id,
                claim.worker,
                claim.claim.topic,
                WITHHELD if withheld else claim.claim.text,
                claim.claim.source_url,
                "" if withheld else claim.claim.quote,
                claim.fetch_call_id,
                int(claim.url_fetched_in_run),
                int(claim.quote_found),
                int(claim.numbers_ok),
                int(withheld),
                int(claim.carries_link),
                int(claim.verified),
                drop_reason(claim),
                claim.verifier_version,
                utc_now(),
            ),
        )
    return brief_id
