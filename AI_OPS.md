# AdScout AI operations

PROJECT.md owns scope, decisions and operator gates. OpenSpec owns requirements and tasks.
This record maps AI capabilities to their current evidence; link existing artifacts rather
than maintaining duplicate specifications. Read
[the AI-ops skill](.agents/skills/adscout-ai-ops/SKILL.md) for the affected procedure.

## Capability map

No AI capability is implemented yet: Phase 1 built the pipeline skeleton with stub steps and
no model call. Phase 2 (`openspec/changes/phase-2-ai-pipeline/`) is specified and builds the
model steps. "Deferred" below means planned but not built.

| Capability | Status | Reason / evidence or task | Recheck when |
|---|---|---|---|
| Hosted or local model inference | deferred (Phase 2 specified) | Anthropic API through an in-house adapter (fake, replay, live): Haiku 5.5 for extraction and research workers, Sonnet 5.5 for scoring (provisional), research lead, writer and critic; fallback to the other tier once; behind the spend and account gates (Phase 2 design, decisions 13–16) | First model call, model or provider change |
| Prompts and structured output | deferred (Phase 2 specified) | Prompt files with digests; structured output for extraction, rubric ratings, worker findings, briefs, drafts and critic verdicts (Phase 2 design, decisions 21, 23–31) | Prompt/schema/model changes |
| RAG / document ingestion | deferred | No index planned; research workers read pages directly through `fetch_page` and drafts use configured media-kit facts | First indexed source or ingestion change |
| Semantic or response caching | deferred (Phase 2 specified) | Provider prompt caching on fixed prefixes; a record-and-replay cache for development reruns at $0 (decisions 18, 20); no semantic cache | Cache scope or key changes |
| Model training / feature pipelines | deferred | A classic lead-scoring model needs real won/lost outcomes, which this project lacks | Real outcome labels become available |
| Tool actions / external adapters | partial (local only) | The single CRM writer writes only the local fake CRM (Phase 1, `src/adscout/crm/writer.py`); HubSpot is Phase 3. Research workers get server web search and our read-only `fetch_page` (Phase 2); no agent holds a send, CRM-write or file-write tool (§5 1.1.0) | New tool, destination or write action |
| Persistent state / replay | enabled (local) | SQLite database of companies, leads, step outcomes, outputs, approvals and runs (Phase 1). A run stops at approval; approval and CRM sync are separate runs. Leads of a failed or interrupted run re-enter the next run; nothing is replayed mid-step. Phase 2 adds model and source call records and a replay cache | Memory, checkpoints or mid-step resume added |
| Multiple users / tenants | deferred | Single user on the owner's PC (PROJECT.md §2) | Second user, shared listener or worker |
| Generated code execution | deferred | Not planned; server tools pinned to versions without code execution (Phase 2 design, decision 28) | Code execution tool enabled |
| MCP / external tool servers | deferred | Not planned | Server or tool contract changes |
| Messages sent to people | deferred | Sandbox inbox only, after approval, with sender ID and unsubscribe enforced in the send function (§5, Phase 3) | First automated send, new channel or new region |
| Business outcome measurement | deferred | Revenue is simulated; no real sends, so reply, meeting and revenue outcomes are not measurable (PROJECT.md §3) | Value depends on a downstream outcome or attribution |

## Evidence locations

| Record | Location / current status |
|---|---|
| Design choices: autonomy, pattern, framework, model tiers, hosting, fallback | Phase 1 design (decision 23) for autonomy and hosting. Phase 2 design: a workflow whose research step is an orchestrator–workers team and whose drafts use evaluator–optimizer; LangGraph for orchestration only; model per role and fallback (decisions 2, 14, 15, 24–31); the agent and security map (Rule of Two, OWASP LLM 2025 and Agentic 2026) |
| System bundle and last known-good version | Every run row records code revision and dirty flag, `uv.lock` digest, package, agent and prompt versions, schema version and config, seed-list and stub-script hashes (Phase 1). Last known-good: the Phase 1 evidence runs at c957258 (`evidence/runs/`) |
| Evaluation plan, held-out cases and evaluator | Phase 2 design, decisions 19, 29, 34 and 35: deterministic case sets (rules, drafts, verifier, injection), owner labels with a hash, and comparison plans committed in `evals/plans/` before measuring. Harness, case and result formats in `evals/` (Phase 0) |
| Offline deterministic check command | `uv run --locked python scripts/gate.py`; its evaluation step is `uv run --locked pytest evals` |
| Authorized provider-evaluation command and budget | `python -m evals score-compare` and the research design comparison, with per-run caps in the Phase 2 design (decision 16) under the owner's $45 workspace limit (PROJECT.md §6) |
| Run records / metrics / alerts | Evaluation run records in gitignored `evals/runs/`, never deleted; cited runs in `evals/evidence/` (Phase 0). Pipeline runs in `runs`, `step_runs` and `lead_step_outcomes` of the gitignored `data/adscout.db`; `adscout check` validates a run independently; exports cited as evidence in `evidence/runs/` (Phase 1). Phase 2 adds `model_calls` with trace fields, an end-of-run cost table and `adscout trace`; Langfuse Cloud in Phase 3 |
| Release evidence and stop/recovery runbook | TBD; not planned beyond the portfolio README |
| Operational owner and maintenance/recheck cadence | Peter Rentopoulos; cadence TBD |

## Current operational limits

Enforced since Phase 1: one live run at a time, and each run records budgets of zero model and
network calls (nothing in Phase 1 makes either). Specified for Phase 2 (design, decisions 10,
16 and 37): per-run spend caps reserved before each call, per-worker and per-lead step, page
and search caps, at most 3 parallel model calls, fetch pacing of at least 1 s per host,
`max_tokens` per role, and a $45 workspace limit with auto-reload off. Research runs only for
qualified leads; drafts get at most two rewrites before a person. Data retention: only public
company-level data, synthetic contacts and claim quotes of at most 300 characters are stored
(§5); full pages stay in the gitignored replay cache.

## Latest scoped evidence

Phase 1 (2026-10-18): three evidence runs of the stub pipeline on the five real seeds at
c957258, each passing `adscout check` and an independent check of the exports (HANDOFF.md). They
show the pipeline's structure, not AI behaviour: no model ran, so AI runtime evaluation is
not_run. No AI runtime evaluation has been established by installing this kit. Record actual candidate
and baseline versions, case counts, commands, pass/fail/not_run/stale outcomes and limitations
as implementation proceeds. A deferred capability needs fresh evidence before it is enabled.
