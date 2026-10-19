"""The research lead's two calls: plan the workers' questions, merge verified claims.

Both calls have no tools (design decision 25). The roster is fixed in code: the plan can only
word questions for the three known workers; any other worker it names is ignored, URLs are
stripped from its questions, and seed URLs come from enrichment, never from a model. A
worker the plan leaves out gets the code's default questions. The merge sees verified claims
only and may cite only their IDs and use only their numbers; anything else is invalid
output, retried once and then sent to the other tier.
"""

import re
from collections.abc import Sequence

from adscout.llm.adapter import CallContext, ModelAdapter, ModelCallFailed, ModelResult
from adscout.llm.invoke import CallsFailed, InvalidOutput, invoke
from adscout.llm.prompts import Prompt, request_for
from adscout.pipeline.contexts import merge_context
from adscout.pipeline.registry import WORKERS, Node
from adscout.research.handoffs import SummaryPoint, VerifiedClaim
from adscout.research.verifier import numbers

PLAN_TOKENS = 800
MERGE_TOKENS = 1_500
MAX_QUESTIONS = 3
URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
DEFAULT_QUESTIONS = {
    "worker_audience": [
        "Who buys this company's products, and which gaming or tech channels reach them?",
    ],
    "worker_ads": ["Where and how does this company advertise or sponsor today?"],
    "worker_launches": [
        "What products did this company launch or announce in the last twelve months?",
        "Which teams, events or leagues does this company sponsor?",
    ],
}


def plan(
    adapter: ModelAdapter,
    prompt: Prompt,
    node: Node,
    user: str,
    context: CallContext,
) -> tuple[dict[str, list[str]], str | None]:
    """Questions for each worker; on a failed plan, the defaults and why."""
    request = request_for(
        prompt,
        node.model or "",
        max_tokens=PLAN_TOKENS,
        effort=node.effort or "medium",
        user=user,
    )
    try:
        planned = invoke(adapter, request, context, parse_plan).value
    except (CallsFailed, ModelCallFailed) as error:
        return dict(DEFAULT_QUESTIONS), f"plan failed, default questions used: {error}"
    return {worker: planned.get(worker) or DEFAULT_QUESTIONS[worker] for worker in WORKERS}, None


def parse_plan(result: ModelResult) -> dict[str, list[str]]:
    try:
        data = result.json()
    except ValueError as error:
        raise InvalidOutput(f"the plan is not JSON: {error}") from None
    assignments = data.get("assignments") if isinstance(data, dict) else None
    if not isinstance(assignments, list):
        raise InvalidOutput("the plan has no assignments list")
    planned: dict[str, list[str]] = {}
    for item in assignments:
        worker = item.get("worker") if isinstance(item, dict) else None
        if worker not in WORKERS:
            continue  # the roster is fixed in code
        questions = [
            " ".join(URL.sub("", str(question)).split()) for question in item.get("questions") or []
        ]
        questions = [question for question in questions if question][:MAX_QUESTIONS]
        if questions:
            planned[worker] = questions
    return planned


def merge(
    adapter: ModelAdapter,
    prompt: Prompt,
    node: Node,
    claims: Sequence[VerifiedClaim],
    context: CallContext,
) -> list[SummaryPoint]:
    """Summary points citing verified claim IDs; raises CallsFailed when none is valid."""
    request = request_for(
        prompt,
        node.model or "",
        max_tokens=MERGE_TOKENS,
        effort=node.effort or "medium",
        user=merge_context(list(claims)),
    )
    by_id = {claim.claim_id: claim for claim in claims}

    def parse(result: ModelResult) -> list[SummaryPoint]:
        try:
            data = result.json()
        except ValueError as error:
            raise InvalidOutput(f"the merge is not JSON: {error}") from None
        items = data.get("summary_points") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            raise InvalidOutput("the merge has no summary points")
        points = []
        for item in items:
            try:
                point = SummaryPoint.model_validate(item)
            except ValueError as error:
                raise InvalidOutput(f"a summary point is malformed: {error}") from None
            unknown = sorted(set(point.claim_ids) - set(by_id))
            if unknown:
                raise InvalidOutput(f"a summary point cites claims that were not given: {unknown}")
            allowed = set().union(*(numbers(by_id[cid].claim.text) for cid in point.claim_ids))
            stray = sorted(numbers(point.text) - allowed)
            if stray:
                raise InvalidOutput(f"a summary point uses numbers its claims do not: {stray}")
            points.append(point)
        return points

    return invoke(adapter, request, context, parse).value
