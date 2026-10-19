"""Typed context builders: the only way data reaches a model request (design decision 33).

Each builder takes typed, company-level inputs (the lead, its validated enriched fields,
verified claims, the segment's rubric, the media kit) and returns the request's user
content. None can read secrets, the owner's labels, CRM data or revenue: they take no
database connection, no environment and no file path, so an agent that reads untrusted
content never holds private data (constitution 1.1.0). Untrusted values travel inside data
delimiters that cannot be closed from within.
"""

import os
from typing import Any

from adscout.llm.prompts import data_block
from adscout.pipeline.contracts import Lead
from adscout.research.handoffs import SummaryPoint, VerifiedClaim

# LangSmith tracing, if switched on by any of these, posts graph state off the machine
# (the task 1.2 spike); runs refuse to start while one is set to true.
TRACING_VARIABLES = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGCHAIN_TRACING_V2",
)


class TracingOn(RuntimeError):
    """A LangSmith tracing variable is on; the run would send its state to LangSmith."""


def refuse_tracing() -> None:
    on = [
        name
        for name in TRACING_VARIABLES
        if os.environ.get(name, "").strip().lower() in ("true", "1", "yes", "on")
    ]
    if on:
        raise TracingOn(
            f"{', '.join(on)} would send run data to LangSmith; unset it to run AdScout"
        )


def lead_data(lead: Lead, fields: dict[str, Any]) -> dict[str, Any]:
    """What scorers and the research lead see: the company and its validated fields."""
    return {"company": lead.name, "domain": lead.domain, "fields": fields}


def scorer_context(lead: Lead, fields: dict[str, Any]) -> str:
    return data_block("lead_data", lead_data(lead, fields))


def planner_context(lead: Lead, fields: dict[str, Any]) -> str:
    return data_block("lead_data", lead_data(lead, fields))


def merge_context(claims: list[VerifiedClaim]) -> str:
    return data_block(
        "claims",
        [
            {
                "id": claim.claim_id,
                "topic": claim.claim.topic,
                "text": claim.claim.text,
                "source_url": claim.claim.source_url,
            }
            for claim in claims
            if claim.verified
        ],
    )


def writer_brief(
    lead: Lead, points: list[SummaryPoint], claims: list[VerifiedClaim]
) -> dict[str, Any]:
    return {
        "company": lead.name,
        "summary_points": [point.model_dump() for point in points],
        "claims": [
            {"id": claim.claim_id, "text": claim.claim.text} for claim in claims if claim.verified
        ],
    }
