"""Task 1.2 spike: LangGraph fan-out and a bounded loop, run with sockets blocked."""

import threading
import time

import pytest
from langgraph.errors import GraphRecursionError

from adscout.pipeline.graph_spike import (
    MAX_PARALLEL_CALLS,
    MAX_REWRITES,
    SpikeFinding,
    SpikeTask,
    build_draft_graph,
    build_research_graph,
    run_draft,
    run_research,
)


def test_fan_out_collects_one_finding_per_worker_in_dispatch_order() -> None:
    delays = {"audience": 0.06, "ads": 0.0, "launches": 0.03}

    def worker(task: SpikeTask) -> SpikeFinding:
        time.sleep(delays[task.worker])
        return SpikeFinding(worker=task.worker, text=f"{task.worker}: {task.question}")

    findings = run_research(build_research_graph(worker), "example.test", list(delays))

    # Completion order is ads, launches, audience; the reducer keeps dispatch order.
    assert [finding.worker for finding in findings] == ["audience", "ads", "launches"]
    assert all(isinstance(finding, SpikeFinding) for finding in findings)
    assert findings[0].text == "audience: example.test"


def test_fan_out_runs_in_parallel_up_to_the_concurrency_cap() -> None:
    lock = threading.Lock()
    running = 0
    peak = 0

    def worker(task: SpikeTask) -> SpikeFinding:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return SpikeFinding(worker=task.worker, text="ok")

    workers = [f"w{i}" for i in range(6)]
    findings = run_research(build_research_graph(worker), "example.test", workers)

    assert len(findings) == 6
    assert 1 < peak <= MAX_PARALLEL_CALLS


def test_a_failed_worker_leaves_the_others_findings() -> None:
    def worker(task: SpikeTask) -> SpikeFinding:
        if task.worker == "ads":
            raise TimeoutError
        return SpikeFinding(worker=task.worker, text="ok")

    findings = run_research(build_research_graph(worker), "example.test", ["audience", "ads"])

    assert [(f.worker, f.failed, f.text) for f in findings] == [
        ("audience", False, "ok"),
        ("ads", True, "TimeoutError"),
    ]


def test_draft_loop_stops_after_the_rewrite_cap() -> None:
    calls: list[int] = []

    def writer(text: str, rewrites: int) -> str:
        calls.append(rewrites)
        return f"draft {rewrites}"

    state = run_draft(build_draft_graph(writer, lambda text: False))

    assert calls == [0, 1, 2]
    assert state == {"text": f"draft {MAX_REWRITES}", "rewrites": MAX_REWRITES, "passed": False}


def test_draft_loop_stops_when_the_check_passes() -> None:
    state = run_draft(
        build_draft_graph(lambda text, rewrites: f"draft {rewrites}", lambda t: t == "draft 1")
    )

    assert state == {"text": "draft 1", "rewrites": 1, "passed": True}


def test_recursion_limit_backstops_a_runaway_loop() -> None:
    graph = build_draft_graph(lambda text, rewrites: "draft", lambda text: False)

    with pytest.raises(GraphRecursionError):
        run_draft(graph, recursion_limit=3)


def test_mermaid_is_drawn_offline() -> None:
    research = build_research_graph(lambda task: SpikeFinding(worker=task.worker, text=""))
    draft = build_draft_graph(lambda text, rewrites: "", lambda text: True)

    research_mermaid = research.get_graph().draw_mermaid()
    draft_mermaid = draft.get_graph().draw_mermaid()

    assert "plan" in research_mermaid and "work" in research_mermaid
    assert "check -.-> write" in draft_mermaid
