"""Task 1.2 spike: LangGraph as orchestration only, under `mypy --strict`.

Two small graphs exercise the shapes the Phase 2 design needs (decision 24): a plan node that
fans out typed worker tasks with `Send` and collects their findings through a reducer, and a
writer-checker loop bounded by a rewrite counter with `recursion_limit` as a backstop. Nodes
are plain typed functions; nothing here calls a model. The registry-built graphs of task 5.1
replace this module.
"""

import operator
from collections.abc import Callable
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send
from pydantic import BaseModel, ConfigDict

MAX_PARALLEL_CALLS = 3  # Design decision 37: at most 3 parallel model calls.
MAX_REWRITES = 2  # Design decision 30: at most two rewrites.


class SpikeTask(BaseModel):
    """Stands in for the design's `WorkerTask` handoff."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    worker: str
    question: str


class SpikeFinding(BaseModel):
    """Stands in for the design's `WorkerFindings` handoff."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    worker: str
    text: str
    failed: bool = False


class ResearchState(TypedDict):
    company: str
    workers: list[str]
    tasks: list[SpikeTask]
    findings: Annotated[list[SpikeFinding], operator.add]


class WorkerState(TypedDict):
    task: SpikeTask


class ResearchUpdate(TypedDict, total=False):
    tasks: list[SpikeTask]
    findings: list[SpikeFinding]


Worker = Callable[[SpikeTask], SpikeFinding]


def plan(state: ResearchState) -> ResearchUpdate:
    company = state["company"]
    return {"tasks": [SpikeTask(worker=name, question=company) for name in state["workers"]]}


def dispatch(state: ResearchState) -> list[Send]:
    return [Send("work", WorkerState(task=task)) for task in state["tasks"]]


def build_research_graph(
    worker: Worker,
) -> CompiledStateGraph[ResearchState, None, ResearchState, ResearchState]:
    def work(state: WorkerState) -> ResearchUpdate:
        task = state["task"]
        try:
            finding = worker(task)
        except Exception as error:  # A failed worker makes a partial brief (ASI08).
            finding = SpikeFinding(worker=task.worker, text=type(error).__name__, failed=True)
        return {"findings": [finding]}

    builder = StateGraph(ResearchState)
    builder.add_node("plan", plan)
    builder.add_node("work", work)
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", dispatch, ["work"])
    builder.add_edge("work", END)
    return builder.compile(name="research_spike")


def run_research(
    graph: CompiledStateGraph[ResearchState, None, ResearchState, ResearchState],
    company: str,
    workers: list[str],
) -> list[SpikeFinding]:
    initial = ResearchState(company=company, workers=workers, tasks=[], findings=[])
    output = graph.invoke(
        initial, {"max_concurrency": MAX_PARALLEL_CALLS, "recursion_limit": 10}, version="v2"
    )
    return output.value["findings"]


class DraftState(TypedDict):
    text: str
    rewrites: int
    passed: bool


class DraftUpdate(TypedDict, total=False):
    text: str
    rewrites: int
    passed: bool


Writer = Callable[[str, int], str]
Checker = Callable[[str], bool]


def build_draft_graph(
    writer: Writer, checker: Checker
) -> CompiledStateGraph[DraftState, None, DraftState, DraftState]:
    def write(state: DraftState) -> DraftUpdate:
        rewrites = state["rewrites"] + (1 if state["text"] else 0)
        return {"text": writer(state["text"], rewrites), "rewrites": rewrites}

    def check(state: DraftState) -> DraftUpdate:
        return {"passed": checker(state["text"])}

    def route(state: DraftState) -> str:
        if state["passed"] or state["rewrites"] >= MAX_REWRITES:
            return END
        return "write"

    builder = StateGraph(DraftState)
    builder.add_node("write", write)
    builder.add_node("check", check)
    builder.add_edge(START, "write")
    builder.add_edge("write", "check")
    builder.add_conditional_edges("check", route, ["write", END])
    return builder.compile(name="draft_spike")


def run_draft(
    graph: CompiledStateGraph[DraftState, None, DraftState, DraftState],
    recursion_limit: int = 10,
) -> DraftState:
    return graph.invoke(
        DraftState(text="", rewrites=0, passed=False),
        {"recursion_limit": recursion_limit},
        version="v2",
    ).value
