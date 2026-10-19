"""The real pipeline run: source, enrich, rules, score, research and draft (Phase 2).

The chain is a LangGraph `StateGraph` built from the agent registry's step nodes (design
decisions 24 and 39); each node is a plain function that records its step and its leads'
outcomes, and the per-lead router lives in the score step. A run stops at approval: no
draft is sent and nothing is written to a CRM.

Modes: offline by default, with scripted model answers and fixture sites (synthetic
companies) or a replay of a recorded live run (models and pages); live with `--live`, a
spend cap, the API key, a contact for the User-Agent and the owner-approved site list.
"""

import itertools
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, TypedDict

import httpx2
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from adscout.config import SeedList, SegmentConfig
from adscout.drafts.media_kit import MediaKit, load_media_kit
from adscout.drafts.step import Drafter
from adscout.drafts.step import store as store_draft
from adscout.enrichment.step import Enricher
from adscout.enrichment.step import store as store_enrichment
from adscout.llm.adapter import ModelAdapter
from adscout.llm.cache import ReplayCache
from adscout.llm.invoke import SONNET
from adscout.llm.prompts import load_prompt, prompt_set_version
from adscout.pipeline.contracts import PIPELINE_STEPS, Lead
from adscout.pipeline.models import ModelChoice, ModelsNotChosen, build_adapter, price_snapshot
from adscout.pipeline.recorder import Run, Snapshot
from adscout.pipeline.registry import REGISTRY
from adscout.pipeline.run import require_migrated, seeds_snapshot, segment_snapshot
from adscout.pipeline.source import source
from adscout.research.handoffs import Design
from adscout.research.step import Researched, Researcher
from adscout.research.step import store as store_research
from adscout.rules import rules_step
from adscout.scoring import Scorer
from adscout.scoring import store as store_scores
from adscout.sources.fetcher import (
    FIXTURE_CONTACT,
    Fetcher,
    FixtureTransport,
    RecordingTransport,
    ReplayPageTransport,
    live_contact,
)
from adscout.sources.site_list import SiteList, load_site_list, site_list_path
from adscout.sources.urls import system_resolver

ROLES = (
    "extract",
    "launch_search",
    "score",
    "research_plan",
    "research_worker",
    "research_single",
    "research_merge",
    "draft_writer",
    "draft_critic",
)


class RunRefused(ValueError):
    """The run's settings cannot work; nothing was written."""


@dataclass(frozen=True)
class RunSettings:
    models: ModelChoice
    media_kit: Path
    fixture_sites: Path | None = None
    site_list: Path | None = None
    score_repeats: int = 1
    research_design: Design = "multi"
    scorer_model: str = SONNET


class PipelineState(TypedDict):
    leads: list[Lead]
    fields: dict[str, dict[str, Any]]
    researched: dict[str, Researched]
    brief_ids: dict[str, int]


@dataclass
class Steps:
    """The step functions, each recording its step on the run."""

    run: Run
    segment: SegmentConfig
    seeds: SeedList
    enricher: Enricher
    scorer: Scorer
    researcher: Researcher
    drafter: Drafter

    def source(self, state: PipelineState) -> dict[str, Any]:
        leads: list[Lead] = []
        with self.run.step("source", "real", len(self.seeds.rows)) as recorder:
            # Sourcing only touches the local database, so it runs inside the write.
            recorder.defer(
                lambda: leads.extend(
                    source(self.run, recorder, self.segment, self.seeds, self.seeds.content_hash())
                )
            )
        return {"leads": leads}

    def enrich(self, state: PipelineState) -> dict[str, Any]:
        fields = dict(state["fields"])
        with self.run.step("enrich", "real", len(state["leads"])) as recorder:
            for lead in state["leads"]:
                enriched = self.enricher.enrich(lead, self.run.run_id)
                fields[lead.lead_id] = enriched.summary()
                recorder.defer(
                    partial(store_enrichment, self.run.connection, self.run.run_id, enriched)
                )
                recorder.outcomes.append(enriched.outcome)
        return {"leads": _kept(state["leads"], recorder.outcomes), "fields": fields}

    def rules(self, state: PipelineState) -> dict[str, Any]:
        with self.run.step("rules", "real", len(state["leads"])) as recorder:
            outcomes = rules_step(
                self.segment,
                [(lead.lead_id, state["fields"][lead.lead_id]) for lead in state["leads"]],
            )
            recorder.outcomes.extend(outcomes)
        return {"leads": _kept(state["leads"], outcomes)}

    def score(self, state: PipelineState) -> dict[str, Any]:
        with self.run.step("score", "real", len(state["leads"])) as recorder:
            for lead in state["leads"]:
                scored = self.scorer.score(lead, state["fields"][lead.lead_id], self.run.run_id)
                recorder.defer(
                    partial(
                        store_scores, self.run.connection, self.run.run_id, scored, self.segment
                    )
                )
                recorder.outcomes.append(scored.outcome)
        return {"leads": _kept(state["leads"], recorder.outcomes)}

    def research(self, state: PipelineState) -> dict[str, Any]:
        researched = dict(state["researched"])
        brief_ids = dict(state["brief_ids"])
        with self.run.step("research", "real", len(state["leads"])) as recorder:
            for lead in state["leads"]:
                done = self.researcher.research(
                    lead, state["fields"][lead.lead_id], self.run.run_id
                )
                researched[lead.lead_id] = done

                def write(done: Researched = done) -> None:
                    brief_ids[done.lead.lead_id] = store_research(
                        self.run.connection, self.run.run_id, done
                    )

                recorder.defer(write)
                recorder.outcomes.append(done.outcome)
        return {
            "leads": _kept(state["leads"], recorder.outcomes),
            "researched": researched,
            "brief_ids": brief_ids,
        }

    def draft(self, state: PipelineState) -> dict[str, Any]:
        with self.run.step("draft", "real", len(state["leads"])) as recorder:
            for lead in state["leads"]:
                done = state["researched"][lead.lead_id]
                kept = [claim for claim in done.claims if claim.verified]
                drafted = self.drafter.draft(lead, done.brief.summary_points, kept, self.run.run_id)
                recorder.defer(
                    partial(
                        store_draft,
                        self.run.connection,
                        self.run.run_id,
                        drafted,
                        state["brief_ids"].get(lead.lead_id),
                    )
                )
                recorder.outcomes.append(drafted.outcome)
        return {"leads": _kept(state["leads"], recorder.outcomes)}


def _kept(leads: list[Lead], outcomes: list[Any]) -> list[Lead]:
    going_on = {outcome.lead_id for outcome in outcomes if outcome.outcome == "kept"}
    return [lead for lead in leads if lead.lead_id in going_on]


def pipeline_graph(
    steps: Steps,
) -> CompiledStateGraph[PipelineState, None, PipelineState, PipelineState]:
    """The chain of the registry's pipeline steps, in their pipeline order."""
    order = [node.id for node in REGISTRY if node.kind == "step" and node.id in PIPELINE_STEPS]
    if order != list(PIPELINE_STEPS):
        raise RuntimeError(
            f"the registry's steps {order} differ from the pipeline {PIPELINE_STEPS}"
        )
    builder = StateGraph(PipelineState)
    for name in order:
        builder.add_node(name, getattr(steps, name))  # each step is a method of the same name
    builder.add_edge(START, order[0])
    for earlier, later in itertools.pairwise(order):
        builder.add_edge(earlier, later)
    builder.add_edge(order[-1], END)
    return builder.compile(name="pipeline")


def build_fetcher(settings: RunSettings, run: Run, cache: ReplayCache | None) -> Fetcher:
    choice = settings.models
    if choice.mode == "live":
        if cache is None:
            raise RunRefused("live runs record pages in the replay cache")
        transport: httpx2.BaseTransport = RecordingTransport(
            cache, run.run_id, httpx2.HTTPTransport()
        )
        return Fetcher(
            "live", transport, run.calls, contact=live_contact(), resolver=system_resolver
        )
    if choice.mode == "replay":
        if cache is None or choice.replay_run_id is None:
            raise RunRefused("a replay needs the cache and the recorded run")
        return Fetcher(
            "replay",
            ReplayPageTransport(cache, choice.replay_run_id),
            run.calls,
            contact=FIXTURE_CONTACT,
            sleep=lambda seconds: None,
        )
    if settings.fixture_sites is None:
        raise RunRefused("an offline run with scripted answers needs --fixture-sites")
    return Fetcher(
        "fixture",
        FixtureTransport(settings.fixture_sites),
        run.calls,
        contact=FIXTURE_CONTACT,
        sleep=lambda seconds: None,
    )


def check_settings(
    settings: RunSettings, segment: SegmentConfig
) -> tuple[MediaKit, SiteList | None]:
    """Refuse unusable settings before any row is written."""
    try:
        settings.models.check()
    except ModelsNotChosen as error:
        raise RunRefused(str(error)) from None
    if settings.score_repeats < 1:
        raise RunRefused("--score-repeats must be at least 1")
    if not settings.media_kit.is_file():
        raise RunRefused(
            f"no media kit at {settings.media_kit}: drafts need the owner-named fictional "
            "publisher (config/media-kit/<publisher_id>.yaml)"
        )
    kit = load_media_kit(settings.media_kit)
    sites = None
    if settings.models.mode == "live":
        live_contact()  # refuse early when the contact is missing
        path = settings.site_list or site_list_path(segment.segment_id)
        if not path.is_file():
            raise RunRefused(
                f"live runs read company sites only with an approved site list: {path}"
            )
        sites = load_site_list(path)
        if not sites.approval.given:
            raise RunRefused(f"the site list {path.name} is not approved by the owner yet")
    elif settings.models.mode == "fake" and settings.fixture_sites is None:
        raise RunRefused("an offline run with scripted answers needs --fixture-sites")
    return kit, sites


def run_real_pipeline(
    connection: sqlite3.Connection,
    segment: SegmentConfig,
    seeds: SeedList,
    settings: RunSettings,
) -> str:
    require_migrated(connection)
    kit, sites = check_settings(settings, segment)
    snapshots: dict[str, Snapshot] = {
        "icp_config_hash": segment_snapshot(segment),
        "seed_list_hash": seeds_snapshot(seeds),
        "media_kit_hash": Snapshot("media_kit", kit.content_hash(), kit.model_dump(mode="json")),
        "price_table_hash": price_snapshot(),
    }
    null_reasons = {"stub_script_hash": "a real run uses no stub script"}
    if sites is not None:
        snapshots["site_list_hash"] = Snapshot(
            "site_list", sites.content_hash(), sites.model_dump(mode="json")
        )
    else:
        null_reasons["site_list_hash"] = "offline runs read fixture or recorded pages only"
    choice = settings.models
    run = Run(
        connection,
        "pipeline",
        segment.segment_id,
        choice.source,
        snapshots,
        null_reasons,
        budgets={"max_spend_usd": float(choice.cap_usd)} if choice.cap_usd else {},
        prompt_version=prompt_set_version(),
        options={
            "mode": choice.mode,
            "replay_of": choice.replay_run_id,
            "score_repeats": settings.score_repeats,
            "research_design": settings.research_design,
            "scorer_model": settings.scorer_model,
            "publisher_id": kit.publisher_id,
            "started": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    adapter, cache = build_adapter(choice, run)
    try:
        fetcher = build_fetcher(settings, run, cache)
        steps = _steps(run, segment, seeds, settings, adapter, fetcher, kit, sites)
        with run.recording():
            pipeline_graph(steps).invoke(
                PipelineState(leads=[], fields={}, researched={}, brief_ids={}),
                {"recursion_limit": 20},
                version="v2",
            )
    finally:
        if cache is not None:
            cache.close()
    return run.run_id


def _steps(
    run: Run,
    segment: SegmentConfig,
    seeds: SeedList,
    settings: RunSettings,
    adapter: ModelAdapter,
    fetcher: Fetcher,
    kit: MediaKit,
    sites: SiteList | None,
) -> Steps:
    prompts = {role: load_prompt(role) for role in ROLES}
    today = datetime.now(UTC).date()
    return Steps(
        run=run,
        segment=segment,
        seeds=seeds,
        enricher=Enricher(
            adapter=adapter,
            fetcher=fetcher,
            segment=segment,
            extract_prompt=prompts["extract"],
            search_prompt=prompts["launch_search"],
            today=today,
            site_list=sites,
        ),
        scorer=Scorer(
            adapter, prompts["score"], segment, settings.scorer_model, settings.score_repeats
        ),
        researcher=Researcher(adapter, fetcher, prompts, design=settings.research_design),
        drafter=Drafter(adapter, kit, prompts["draft_writer"], prompts["draft_critic"]),
    )
