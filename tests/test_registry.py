"""The agent registry: tools, caps and the adapter's check against it (decisions 33, 39)."""

from datetime import date
from decimal import Decimal

import pytest

from adscout.ids import uuid7
from adscout.llm.adapter import (
    CallContext,
    CallSink,
    FakeTransport,
    ModelAdapter,
    ModelCallFailed,
    ModelRequest,
)
from adscout.llm.budget import SpendLedger
from adscout.llm.fakes import scripted
from adscout.llm.invoke import HAIKU, SONNET
from adscout.llm.prices import load_price_table
from adscout.pipeline.registry import (
    FLOWS,
    LEAD_RESEARCH_CAPS,
    REGISTRY,
    WORKERS,
    WRITE_TOOLS,
    agents,
    node,
    tools_for,
)


def test_no_node_holds_a_send_crm_or_file_write_tool() -> None:
    held = {tool for item in REGISTRY for tool in item.tools}
    assert not held & WRITE_TOOLS
    assert held == {"web_search", "fetch_page", "submit_findings", "submit_launches"}


def test_node_ids_are_unique_and_agents_are_fully_described() -> None:
    assert len({item.id for item in REGISTRY}) == len(REGISTRY)
    for agent in agents():
        assert agent.model in (HAIKU, SONNET) and agent.fallback in (HAIKU, SONNET)
        assert agent.model != agent.fallback and agent.effort and agent.prompt
        assert agent.trust_zone == "untrusted_content"  # every agent reads web-derived data
        if agent.tools:
            assert agent.caps is not None and agent.pattern == "tool_loop"


def test_worker_and_lead_caps_follow_the_design() -> None:
    assert set(WORKERS) == {"worker_audience", "worker_ads", "worker_launches"}
    caps = node("worker_ads").caps
    assert caps is not None
    assert (caps.calls, caps.searches, caps.pages, caps.seconds) == (6, 3, 2, 90)
    assert caps.cost_usd == {HAIKU: Decimal("0.10"), SONNET: Decimal("0.40")}
    single = node("research_single").caps
    assert single is not None and (single.calls, single.searches, single.pages) == (12, 9, 6)
    with pytest.raises(LookupError, match="not in the agent registry"):
        node("emailer")


def test_writer_request_carrying_fetch_page_is_refused_before_sending() -> None:
    transport = FakeTransport(scripted([]))
    adapter = ModelAdapter(
        transport,
        load_price_table(),
        SpendLedger(None),
        CallSink(),
        today=lambda: date(2026, 10, 19),
    )
    request = ModelRequest(
        model=SONNET,
        max_tokens=500,
        system=[{"type": "text", "text": "Write."}],
        messages=[{"role": "user", "content": "brief"}],
        tools=[{"name": "fetch_page", "input_schema": {"type": "object"}}],  # type: ignore[list-item]
    )
    context = CallContext(
        run_id="r",
        step="draft",
        lead_id=str(uuid7()),
        role="writer",
        agent_name="writer",
        prompt_version="p-0123456789ab",
        parent_span_id="0123456789abcdef",
        allowed_tools=tools_for("writer"),
    )
    with pytest.raises(ModelCallFailed, match="tools differ from its registry entry"):
        adapter.call(request, context)
    assert transport.requests == []


def test_every_flow_is_typed_by_its_ends() -> None:
    for source, target, handoff in FLOWS:
        sender, receiver = node(source), node(target)
        assert handoff in (sender.output_type, receiver.input_type), (source, target)
        same_step = sender.step == receiver.step
        assert same_step or (sender.kind, receiver.kind) == ("step", "person"), (source, target)
    flowing = {end for flow in FLOWS for end in flow[:2]}
    assert {item.id for item in REGISTRY if item.kind != "step"} <= flowing
    assert node("research").caps is LEAD_RESEARCH_CAPS  # the research step's per-lead budget
