## Why

Phase 1 built the pipeline's skeleton with scripted stubs. The owner merged the playbook's
Phases 2–6 into two MVP phases to finish faster (PROJECT.md §6, 2026-10-18): this phase makes
every step that calls a model real, and Phase 3 adds the human, CRM and showcase side. The
owner also approved a multi-agent design, so the phase shows the conventional agent patterns
each where it fits, measured rather than assumed.

This change implements **PROJECT.md Phase 2** ("AI pipeline on real companies: enrichment
with field validation, deterministic profile rules, LLM fit scoring with structured output
and reasons, a read-only research agent (search and fetch tools, step cap, page budget, a
citation per claim), draft writer and rule checker; per-step offline evaluations and cost per
call; answers the model cost and access TBDs in §4. Real leads stop at approval"). Its
decisions come from the Phase 2 grilling of 2026-10-18 (three rounds; the owner accepted
every recommendation), recorded in PROJECT.md §2–4 and §6 and in design.md with who made each.

## What Changes

- **Model access:** an in-house adapter over the `anthropic` SDK with fake, replay and live
  modes; a dated price table; every call recorded with tokens, cache use, search fees, cost,
  latency and role; a spend reservation before each call under a per-run cap; a model
  fallback in our own code; a gitignored record-and-replay cache; prompts as versioned files
  with a digest.
- **Enrichment:** a polite fetcher for each company's own site (robots.txt, pacing, page
  cap, egress rules, an owner-approved site list), Wikidata and SEC EDGAR for size,
  ownership and revenue, Haiku extraction of categories, regions and launches, deterministic
  ad-pixel detection, and field validators.
- **Rules and scoring:** deterministic profile rules (sells in US and CA, an allowed
  category, at least 50 employees); a per-criterion anchored rubric scored by a model and
  combined by code into 0–100, threshold 60; a router to research, a person (near-miss
  55–59) or exit; a Haiku-versus-Sonnet tier evaluation with a predeclared rule.
- **Research team:** orchestrator–workers on LangGraph: a lead (Sonnet) plans and merges, and
  three read-only Haiku workers (audience and channels, ad activity, launches and
  sponsorships) search and fetch under their own caps. Every claim quotes its page, and code
  verifies the quote and its numbers against what was fetched. A single-agent baseline runs
  through the same tools for a predeclared comparison.
- **Drafts:** evaluator–optimizer: a writer, a deterministic rule checker and a critic, at
  most two rewrites, for a fictional publisher with simulated media-kit facts; drafts stop at
  `pending_approval`.
- **Security:** an agent registry fixes each role's tools and context; no agent that reads
  untrusted content gets private data (constitution 1.1.0); canary, allowlist and egress
  tests; ten planted-injection pages offline and live; both OWASP lists mapped to controls.
- **Observability:** span and trace IDs on every call, an end-of-run cost table by step,
  role and model, cost per qualified lead, and `adscout trace` for each lead's agent tree.
- **Diagrams:** the registry generates a LangGraph-style agent-flow diagram (Mermaid and a
  self-contained HTML page, shown to the owner as a private artifact) and the C4 views gain
  the research team; drift tests cover them.
- **Evaluation:** rules, draft and verifier case sets; owner labels for 30 seeds; the score
  check, tier, worker-tier and design comparisons as committed plans run under budget caps.
- **Data:** migration 0002 (enrichment fields, model and source calls, claims, new exit
  reasons, replay runs); 30 seeds from desk research, labelled by the owner.

## Capabilities

### New Capabilities

- `model-access`: the model adapter and its modes, price table and cost records, spend
  reservation and caps, budget errors, fallback, replay cache, prompt files and digests.
- `enrichment`: the fetcher and its policy, the site list, external sources, extraction, ad
  signals, field validation and key fields.
- `fit-scoring`: profile rules, the rubric score, the threshold and router, and the tier
  evaluation.
- `research-team`: the lead and workers, caps, handoff schemas, claim verification, briefs,
  the single-agent baseline and the design comparison.
- `draft-writer`: the writer, rule checker and critic loop, the media-kit config and draft
  outcomes.
- `agent-security`: the agent registry, tool allowlists, context builders, egress rules,
  canary and injection tests, and the OWASP map.
- `run-observability`: trace fields, the end-of-run cost table, cost per qualified lead and
  `adscout trace`.

### Modified Capabilities

- `pipeline-run`: real enrich, rules, score, research and draft steps; new exit reasons and
  flags; live runs behind a flag; stubs kept only for synthetic fixtures.
- `pipeline-store`: migration 0002 tables and the `replay` run source.
- `segment-config`: size range, score threshold, criterion weights and the near-miss band
  set.
- `architecture-diagrams`: the registry-generated agent-flow diagram and the C4 research-team
  view.
- `offline-eval-harness`: new case sets, owner labels with a hash, and comparison plans
  committed before measuring.

## Non-goals

- Approval UI, dashboard and trace page, HubSpot sync, the send function and sandbox inbox,
  synthetic contacts and mock revenue, reviewer reasons saved as labels, the README crewAI
  comparison, near-miss promotion, Langfuse Cloud, CI workflow, README, Dockerfile, video,
  minutes per account (Phase 3).
- Batch API, checkpoints and mid-step resume, the n8n variant, fine-tuning, an injection
  classifier, the 60-company label set and precision in the top 20.

## Impact

- New: `src/adscout/` modules for the model adapter, fetcher, sources, enrichment, rules,
  scoring, research, drafts, registry and trace; `src/adscout/prompts/`; migration
  `0002`; `config/site-checks/`, `config/media-kit/`, `config/prices/`; `evals/cases/`
  rules, drafts, verifier and injection sets; `evals/labels/`; `docs/architecture/agents.md`
  and `agent-flow.html`; `scripts/diagrams.py`.
- Changed: `pyproject.toml` and `uv.lock` (`anthropic`, `httpx2`, `langgraph`), segment
  config and seeds (30 companies), `workspace.dsl` and exports, `export.py` mapping,
  PROJECT.md, AI_OPS.md, AGENTS.md, HANDOFF.md, `openspec/config.yaml` context.
- Owner: an Anthropic Console account, an "adscout" workspace with a $45 spend limit and
  auto-reload off, prepaid credit in two purchases ($20, then about $25), web search enabled,
  the API key in `.env`, a project contact mailbox, approval of the 30 seeds and the site
  list, blind labels for the 30 seeds, a blind spot-check of up to 100 claims, and a name for
  the fictional publisher.
- Constitution: amended to 1.1.0 in its own commit (8488886) before this one: research may
  use several read-only agents, and agents that read untrusted content get no private data.
  Operator decisions are recorded under the spend, account and live-read gates (PROJECT.md
  §6); they are not amendments.
