# AdScout AI operations

PROJECT.md owns scope, decisions and operator gates. OpenSpec owns requirements and tasks.
This record maps AI capabilities to their current evidence; link existing artifacts rather
than maintaining duplicate specifications. Read
[the AI-ops skill](.agents/skills/adscout-ai-ops/SKILL.md) for the affected procedure.

## Capability map

Nothing is implemented yet. "Deferred" below means planned in PROJECT.md §6 but not built.

| Capability | Status | Reason / evidence or task | Recheck when |
|---|---|---|---|
| Hosted or local model inference | deferred | Planned hosted API calls for fit scoring (Phase 2), research (3) and drafts (4); provider TBD; behind the spend and account gates | First model call or provider change |
| Prompts and structured output | deferred | Fit score with reasons as structured output (Phase 2); draft checker output (4) | Prompt/schema/model changes |
| RAG / document ingestion | deferred | No index planned; the research agent reads pages directly and drafts use configured media-kit facts | First indexed source or ingestion change |
| Semantic or response caching | deferred | Playbook proposes provider prompt caching for the fixed draft prompt (Phase 4); no response cache planned | Cache enabled or scope/index changes |
| Model training / feature pipelines | deferred | A classic lead-scoring model needs real won/lost outcomes, which this project lacks | Real outcome labels become available |
| Tool actions / external adapters | deferred | Research agent gets read-only search and fetch tools (Phase 3); the CRM writer and send function are code paths, not model tools (§5) | New tool, destination or write action |
| Persistent state / replay | deferred | Local database of companies, scores, briefs, drafts, approvals and runs (Phase 1); resumable runs TBD | Memory or resumable execution added |
| Multiple users / tenants | deferred | Single user on the owner's PC (PROJECT.md §2) | Second user, shared listener or worker |
| Generated code execution | deferred | Not planned | Code execution tool enabled |
| MCP / external tool servers | deferred | Not planned | Server or tool contract changes |
| Messages sent to people | deferred | Sandbox inbox only, after approval, with sender ID and unsubscribe enforced in the send function (§5, Phase 4) | First automated send, new channel or new region |
| Business outcome measurement | deferred | Revenue is simulated; no real sends, so reply, meeting and revenue outcomes are not measurable (PROJECT.md §3) | Value depends on a downstream outcome or attribution |

## Evidence locations

| Record | Location / current status |
|---|---|
| Design choices: autonomy, pattern, framework, model tiers, hosting, fallback | Phase 1 design (decision 23): a workflow with one agentic step, the pattern per step, local single-user hosting and the security check. Model tiers, access and fallback TBD in Phase 2; agent framework TBD in Phase 3 (PROJECT.md §4) |
| System bundle and last known-good version | TBD; none exists |
| Evaluation plan, held-out cases and evaluator | TBD in Phase 5 (PROJECT.md §3 outline). Harness, case and result formats in `evals/` (Phase 0); only synthetic scaffold cases exist |
| Offline deterministic check command | `uv run --locked python scripts/gate.py`; its evaluation step is `uv run --locked pytest evals` |
| Authorized provider-evaluation command and budget | TBD; behind the spend gate |
| Run records / metrics / alerts | Evaluation run records in gitignored `evals/runs/`, never deleted; cited runs in `evals/evidence/` (Phase 0). Pipeline runs table in Phase 1, tracing with cost per lead in Phase 5 |
| Release evidence and stop/recovery runbook | TBD; not planned beyond the portfolio README |
| Operational owner and maintenance/recheck cadence | Peter Rentopoulos; cadence TBD |

## Current operational limits

No limits are enforced yet. Decided by §5: the research agent has a step cap and a page budget
(values TBD in Phase 3), read-only tools, and no send or write access. Playbook proposals to
confirm: research only for leads above the fit threshold; at most two draft revisions before
handing to a person. Model, token, time, retry, concurrency and cost bounds are TBD behind the
spend gate. The model cost and access items in PROJECT.md §4 (access route, tier per step and
fallback, cost recording from the first call, record-and-replay cache, per-run spend cap,
prompt caching and batch) are TBD and must be answered in Phase 2 grilling. Data retention:
TBD; only public company-level data and synthetic contacts are stored (§5).

## Latest scoped evidence

No AI runtime evaluation has been established by installing this kit. Record actual candidate
and baseline versions, case counts, commands, pass/fail/not_run/stale outcomes and limitations
as implementation proceeds. A deferred capability needs fresh evidence before it is enabled.
