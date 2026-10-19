"""The real `enrich` step: one lead's fields from its site, Wikidata, SEC EDGAR and models.

Per lead (design decisions 7 to 11): a live run reads the company's site only if the approved
site list allows it; at most three pages (home, newsroom, store) are read; ad tags come from
the home page's HTML; Wikidata and, for SEC filers, EDGAR give size, ownership and revenue;
Haiku extracts categories, markets and launches from the pages; one web search looks for
launches when the pages named none. Every value is validated, the best source is chosen,
and a lead missing a key field exits as `missing_key_fields`, naming the fields and why.
A budget stop ends the run; any other source or model failure is noted and the lead goes on
with what the other sources gave.
"""

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from adscout.config import SegmentConfig
from adscout.db.connection import utc_now
from adscout.enrichment.extract import extract
from adscout.enrichment.fields import (
    Candidate,
    Checked,
    check,
    choose,
    missing_key_fields,
    valid_values,
)
from adscout.enrichment.pages import pick_pages
from adscout.enrichment.search import TOOLS as SEARCH_TOOLS
from adscout.enrichment.search import search_launches
from adscout.enrichment.sec import Sec
from adscout.enrichment.tags import detect
from adscout.enrichment.wikidata import Wikidata
from adscout.llm.adapter import CallContext, ModelAdapter, ModelCallFailed
from adscout.llm.invoke import HAIKU, CallsFailed
from adscout.llm.prompts import Prompt
from adscout.pipeline.contracts import Lead, Outcome
from adscout.sources.fetcher import Fetcher, FetchFailed, FetchRefused, Page, SourceContext
from adscout.sources.site_list import SiteList, company_site_refusal
from adscout.spans import SpanRecord, SpanStatus, step_span

MAX_PAGES = 3


@dataclass
class Enricher:
    adapter: ModelAdapter
    fetcher: Fetcher
    segment: SegmentConfig
    extract_prompt: Prompt
    search_prompt: Prompt
    today: date
    site_list: SiteList | None = None
    extract_model: str = HAIKU
    search_model: str = HAIKU  # Sonnet if Haiku lacks web search (decision 41)
    wikidata: Wikidata = field(init=False)
    sec: Sec = field(init=False)

    def __post_init__(self) -> None:
        self.wikidata = Wikidata(self.fetcher)
        self.sec = Sec(self.fetcher)

    def enrich(self, lead: Lead, run_id: str) -> "Enriched":
        span = step_span(run_id, lead.lead_id, "enrich")
        sources = SourceContext(run_id, "enrich", lead.lead_id, span.span_id)
        found: list[Candidate] = []
        rows: list[Checked] = []
        notes: list[str] = []
        agents: list[SpanRecord] = []

        pages = self._pages(lead, sources, found, notes)
        try:
            result = self.wikidata.enrich(lead.name, lead.domain, sources)
            if result is None:
                notes.append("Wikidata has no item with this website")
            else:
                found.extend(result.candidates)
                if result.cik is not None:
                    found.extend(self.sec.enrich(result.cik, sources))
        except (FetchFailed, FetchRefused, ValueError) as error:
            notes.append(f"Wikidata or SEC EDGAR failed: {error}")
        for candidate in found:
            rows.extend(check(candidate, self.segment.categories, self.today))
        if pages:
            agent = span.child("extractor")
            try:
                extraction = extract(
                    self.adapter,
                    self.extract_prompt,
                    self.segment,
                    lead.name,
                    pages,
                    self._context(run_id, lead, "extractor", agent.span_id),
                    self.today,
                    self.extract_model,
                )
                rows.extend(extraction.rows)
                if extraction.escalated:
                    notes.append("extraction escalated to Sonnet after a validator failure")
                agent_status: SpanStatus = "succeeded"
            except (ModelCallFailed, CallsFailed) as error:
                notes.append(f"extraction failed: {error}")
                agent_status = "failed"
            agents.append(agent.close(agent_status, "extraction"))
        if "recent_launches" not in valid_values(rows):
            agent = span.child("launch_searcher")
            context = self._context(run_id, lead, "launch_searcher", agent.span_id, SEARCH_TOOLS)
            try:
                outcome = search_launches(
                    self.adapter,
                    self.search_prompt,
                    self.segment,
                    lead.name,
                    lead.domain,
                    context,
                    self.today,
                    self.search_model,
                )
                rows.extend(outcome.rows)
                notes.append(outcome.note)
                agent_status = "succeeded"
            except ModelCallFailed as error:
                notes.append(f"launch search failed: {error}")
                agent_status = "failed"
            agents.append(agent.close(agent_status, "launch search"))
        checked = choose(rows)
        missing = missing_key_fields(checked)
        if missing:
            detail = f"missing key fields: {', '.join(missing)}"
            if notes:
                detail += f" ({'; '.join(notes)})"
            outcome_row = Outcome(
                lead_id=lead.lead_id,
                outcome="exited",
                reason="missing_key_fields",
                detail=detail,
            )
        else:
            kept = len(valid_values(checked))
            outcome_row = Outcome(
                lead_id=lead.lead_id, outcome="kept", detail=f"{kept} fields enriched"
            )
        for record in [*agents, span.close("succeeded", outcome_row.detail)]:
            self.adapter.sink.add(record)
        return Enriched(lead, checked, outcome_row, notes)

    def _pages(
        self, lead: Lead, sources: SourceContext, found: list[Candidate], notes: list[str]
    ) -> list[Page]:
        home_url = f"https://{lead.domain}/"
        refusal = company_site_refusal(self.fetcher.mode, self.site_list, lead.domain)
        if refusal:
            self.fetcher.refuse(home_url, sources, refusal)
            notes.append(refusal)
            return []
        try:
            home = self.fetcher.fetch(home_url, sources, site=lead.domain)
        except (FetchFailed, FetchRefused) as error:
            notes.append(f"home page not read: {error}")
            return []
        found.append(
            Candidate(
                field="ad_signals",
                value=detect(home.text),
                source_url=home.final_url,
                source_kind="company_site",
                method="parsed",
                retrieved_at=utc_now(),
                source_call_id=home.call_id,
            )
        )
        pages = [home]
        for url in pick_pages(home.text, home.final_url, lead.domain)[: MAX_PAGES - 1]:
            try:
                pages.append(self.fetcher.fetch(url, sources, site=lead.domain))
            except (FetchFailed, FetchRefused) as error:
                notes.append(f"{url} not read: {error}")
        return pages

    def _context(
        self,
        run_id: str,
        lead: Lead,
        agent: str,
        parent: str,
        tools: frozenset[str] = frozenset(),
    ) -> CallContext:
        prompt = self.search_prompt if agent == "launch_searcher" else self.extract_prompt
        return CallContext(
            run_id=run_id,
            step="enrich",
            lead_id=lead.lead_id,
            role=agent,
            agent_name=agent,
            prompt_version=prompt.version,
            parent_span_id=parent,
            allowed_tools=tools,
        )


@dataclass(frozen=True)
class Enriched:
    lead: Lead
    rows: list[Checked]
    outcome: Outcome
    notes: list[str]

    def summary(self) -> dict[str, Any]:
        return {name: row.value for name, row in sorted(valid_values(self.rows).items())}


def store(connection: sqlite3.Connection, run_id: str, enriched: Enriched) -> None:
    """The lead's `enrichments` row and one `enrichment_fields` row per checked value."""
    unattributed = [row for row in enriched.rows if not row.candidate.source_url.startswith("http")]
    cursor = connection.execute(
        "INSERT INTO enrichments (lead_id, run_id, implementation, fields_json, "
        "missing_fields_json, created_at) VALUES (?, ?, 'real', ?, ?, ?)",
        (
            enriched.lead.lead_id,
            run_id,
            json.dumps(
                {
                    "fields": enriched.summary(),
                    "notes": enriched.notes,
                    "dropped_without_source": [
                        {"field": row.field, "detail": row.detail} for row in unattributed
                    ],
                },
                sort_keys=True,
            ),
            json.dumps(missing_key_fields(enriched.rows)),
            utc_now(),
        ),
    )
    enrichment_id = cursor.lastrowid
    for row in enriched.rows:
        if row in unattributed:
            continue
        candidate = row.candidate
        connection.execute(
            "INSERT INTO enrichment_fields (enrichment_id, lead_id, run_id, field, value_json, "
            "source_url, source_kind, method, source_call_id, model_call_id, retrieved_at, "
            "as_of, status, status_detail, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                enrichment_id,
                enriched.lead.lead_id,
                run_id,
                row.field,
                json.dumps(row.value, sort_keys=True),
                candidate.source_url,
                candidate.source_kind,
                candidate.method,
                candidate.source_call_id,
                candidate.model_call_id,
                candidate.retrieved_at,
                candidate.as_of,
                row.status,
                row.detail,
                utc_now(),
            ),
        )


def enrich_all(enricher: Enricher, leads: Sequence[Lead], run_id: str) -> list[Enriched]:
    """Leads one after another: pacing is per host, and Wikidata and EDGAR are shared hosts."""
    return [enricher.enrich(lead, run_id) for lead in leads]
