"""The agent registry: every pipeline node, its tools, caps, model and trust zone.

The registry is the one place that says what each node may do (design decisions 33 and 39).
The adapter refuses a model request whose tools differ from its role's entry, the graphs
are built from it, and the agent-flow diagram is generated from it. No node holds a send,
CRM-write or file-write tool; agents that read untrusted content get no private data.

Trust zones: `untrusted_content` (reads fetched or extracted web content), `no_tools` (a
model call with no tools over data already validated), `code_only` (deterministic code),
`human` (a person decides).
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from adscout.llm.invoke import HAIKU, SONNET

NodeKind = Literal["step", "agent", "tool", "person", "gate"]
Pattern = Literal[
    "sequential",
    "router",
    "orchestrator_workers",
    "evaluator_optimizer",
    "single_call",
    "tool_loop",
    "code",
    "human",
]
TrustZone = Literal["untrusted_content", "no_tools", "code_only", "human"]
Effort = Literal["low", "medium", "high"]

# Tools that would act on the world rather than read it; no node may hold one (§5).
WRITE_TOOLS = frozenset(
    {"send_email", "send_message", "crm_write", "write_file", "edit_file", "bash", "code_execution"}
)


@dataclass(frozen=True)
class Caps:
    """Limits on one invocation; a cost cap is per model, in US dollars."""

    calls: int | None = None
    searches: int | None = None
    pages: int | None = None
    seconds: float | None = None
    cost_usd: dict[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: NodeKind
    pattern: Pattern
    step: str
    trust_zone: TrustZone
    input_type: str
    output_type: str
    model: str | None = None
    fallback: str | None = None
    effort: Effort | None = None
    prompt: str | None = None
    tools: frozenset[str] = frozenset()
    caps: Caps | None = None
    exits: tuple[str, ...] = ()


WORKER_CAPS = Caps(
    calls=6,
    searches=3,
    pages=2,
    seconds=90,
    cost_usd={HAIKU: Decimal("0.10"), SONNET: Decimal("0.40")},
)
LEAD_RESEARCH_CAPS = Caps(
    calls=20,
    searches=9,
    pages=6,
    cost_usd={HAIKU: Decimal("0.30"), SONNET: Decimal("0.90")},
)
SINGLE_CAPS = Caps(
    calls=12, searches=9, pages=6, cost_usd={SONNET: Decimal("0.90"), HAIKU: Decimal("0.30")}
)
DRAFT_CAPS = Caps(cost_usd={SONNET: Decimal("0.12"), HAIKU: Decimal("0.12")})
RESEARCH_TOOLS = frozenset({"web_search", "fetch_page", "submit_findings"})
WORKERS = {
    "worker_audience": ("Audience and channels", "audience_channels"),
    "worker_ads": ("Ad activity", "ad_activity"),
    "worker_launches": ("Launches and sponsorships", "launches"),
}

REGISTRY: tuple[Node, ...] = (
    Node(
        "source",
        "Source seeds",
        "step",
        "sequential",
        "source",
        "code_only",
        "SeedList",
        "list[Lead]",
        exits=("duplicate", "excluded"),
    ),
    Node(
        "enrich",
        "Enrich",
        "step",
        "sequential",
        "enrich",
        "code_only",
        "list[Lead]",
        "list[Enriched]",
        exits=("missing_key_fields",),
    ),
    Node(
        "extractor",
        "Extract fields",
        "agent",
        "single_call",
        "enrich",
        "untrusted_content",
        "company pages",
        "Extraction",
        model=HAIKU,
        fallback=SONNET,
        effort="low",
        prompt="extract",
    ),
    Node(
        "launch_searcher",
        "Search launches",
        "agent",
        "tool_loop",
        "enrich",
        "untrusted_content",
        "company name",
        "launches",
        model=HAIKU,
        fallback=SONNET,
        effort="low",
        prompt="launch_search",
        tools=frozenset({"web_search", "submit_launches"}),
        caps=Caps(calls=2, searches=1),
    ),
    Node(
        "rules",
        "Profile rules",
        "step",
        "code",
        "rules",
        "code_only",
        "Enriched fields",
        "Outcome",
        exits=("out_of_profile", "missing_key_fields"),
    ),
    Node(
        "score",
        "Score and route",
        "step",
        "router",
        "score",
        "code_only",
        "Enriched fields",
        "Scored",
        exits=("near_miss", "below_threshold", "score_failed"),
    ),
    Node(
        "scorer",
        "Rubric scorer",
        "agent",
        "single_call",
        "score",
        "untrusted_content",
        "Enriched fields",
        "ratings",
        model=SONNET,
        fallback=HAIKU,
        effort="low",
        prompt="score",
    ),
    Node(
        "research",
        "Research",
        "step",
        "orchestrator_workers",
        "research",
        "code_only",
        "Qualified lead",
        "Brief",
        exits=("research_failed",),
    ),
    Node(
        "research_plan",
        "Lead: plan",
        "agent",
        "single_call",
        "research",
        "untrusted_content",
        "Enriched fields",
        "Plan",
        model=SONNET,
        fallback=HAIKU,
        effort="medium",
        prompt="research_plan",
    ),
    *(
        Node(
            worker_id,
            label,
            "agent",
            "tool_loop",
            "research",
            "untrusted_content",
            "WorkerTask",
            "WorkerFindings",
            model=HAIKU,
            fallback=SONNET,
            effort="low",
            prompt="research_worker",
            tools=RESEARCH_TOOLS,
            caps=WORKER_CAPS,
        )
        for worker_id, (label, _topic) in WORKERS.items()
    ),
    Node(
        "research_single",
        "Single agent (baseline)",
        "agent",
        "tool_loop",
        "research",
        "untrusted_content",
        "WorkerTask",
        "WorkerFindings",
        model=SONNET,
        fallback=HAIKU,
        effort="medium",
        prompt="research_single",
        tools=RESEARCH_TOOLS,
        caps=SINGLE_CAPS,
    ),
    Node(
        "verifier",
        "Claim verifier",
        "step",
        "code",
        "research",
        "code_only",
        "WorkerFindings",
        "list[VerifiedClaim]",
    ),
    Node(
        "research_merge",
        "Lead: merge",
        "agent",
        "single_call",
        "research",
        "untrusted_content",
        "list[VerifiedClaim]",
        "Brief",
        model=SONNET,
        fallback=HAIKU,
        effort="medium",
        prompt="research_merge",
    ),
    Node(
        "draft",
        "Draft",
        "step",
        "evaluator_optimizer",
        "draft",
        "code_only",
        "Brief",
        "Draft",
        exits=("draft_failed",),
    ),
    Node(
        "writer",
        "Writer",
        "agent",
        "single_call",
        "draft",
        "untrusted_content",
        "Brief and media kit",
        "Draft",
        model=SONNET,
        fallback=HAIKU,
        effort="medium",
        prompt="draft_writer",
        caps=DRAFT_CAPS,
    ),
    Node(
        "rule_checker", "Rule checker", "step", "code", "draft", "code_only", "Draft", "RuleCheck"
    ),
    Node(
        "critic",
        "Critic",
        "agent",
        "single_call",
        "draft",
        "untrusted_content",
        "Draft and brief",
        "Critique",
        model=SONNET,
        fallback=HAIKU,
        effort="low",
        prompt="draft_critic",
    ),
    Node(
        "approval",
        "Person approves",
        "person",
        "human",
        "approve",
        "human",
        "Draft",
        "Approval",
        exits=("rejected",),
    ),
)

BY_ID = {node.id: node for node in REGISTRY}


def node(node_id: str) -> Node:
    try:
        return BY_ID[node_id]
    except KeyError:
        raise LookupError(f"{node_id} is not in the agent registry") from None


def tools_for(node_id: str) -> frozenset[str]:
    return node(node_id).tools


def agents() -> list[Node]:
    return [item for item in REGISTRY if item.kind == "agent"]
