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
| Design choices: autonomy, pattern, framework, model tiers, hosting, fallback | TBD in the Phase 1 design; playbook proposal: workflow with one ReAct research step, evaluator-optimizer drafts, fast tier for scoring, workhorse tier for research and drafts |
| System bundle and last known-good version | TBD; none exists |
| Evaluation plan, held-out cases and evaluator | TBD in Phase 5 (PROJECT.md §3 outline); scaffold in Phase 0 |
| Offline deterministic check command | TBD in Phase 0 |
| Authorized provider-evaluation command and budget | TBD; behind the spend gate |
| Run records / metrics / alerts | TBD; runs table in Phase 1, tracing with cost per lead in Phase 5 |
| Release evidence and stop/recovery runbook | TBD; not planned beyond the portfolio README |
| Operational owner and maintenance/recheck cadence | Peter Rentopoulos; cadence TBD |

## Current operational limits

No limits are enforced yet. Decided by §5: the research agent has a step cap and a page budget
(values TBD in Phase 3), read-only tools, and no send or write access. Playbook proposals to
confirm: research only for leads above the fit threshold; at most two draft revisions before
handing to a person. Model, token, time, retry, concurrency and cost bounds are TBD behind the
spend gate. Data retention: TBD; only public company-level data and synthetic contacts are
stored (§5).

## Latest scoped evidence

No AI runtime evaluation has been established by installing this kit. Record actual candidate
and baseline versions, case counts, commands, pass/fail/not_run/stale outcomes and limitations
as implementation proceeds. A deferred capability needs fresh evidence before it is enabled.
