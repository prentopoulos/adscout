# AdScout AI operations

PROJECT.md owns scope and operator gates; OpenSpec owns requirements and tasks.
Read [the AI-ops skill](.agents/skills/adscout-ai-ops/SKILL.md) for affected procedures.
The local MVP uses real pipeline code with scripted responses and synthetic sites.
It establishes offline contracts, not live model quality, email delivery or sales results.

## Capability map

| Capability | Current status and evidence | Recheck when |
|---|---|---|
| Model inference | Adapter implemented with fake, replay and live transports, explicit tools, retries, escalation, usage records and spend reservation; `tests/test_adapter.py`, `test_budget.py`, `test_invoke.py`. No paid provider run established | Provider, model, pricing or budget changes |
| Prompts and structured output | Versioned prompt/schema pairs for extraction, launch search, scoring, research and drafting; role-specific context builders. `tests/test_prompts.py`, `test_security.py` | Prompt/schema/context changes |
| Research team | LangGraph lead/three-worker graph, read-only tools, worker and lead caps, deterministic claim verifier and single-agent baseline. `tests/test_research.py`, `test_registry.py` | Agent graph, tools, caps or verifier changes |
| Draft generation | Writer, deterministic checker, critic and at most two rewrites; unresolved critic warnings retained for human review. `tests/test_drafts.py` | Draft rules, media-kit facts or rewrite policy changes |
| Injection protection | Ten planted pages and clean twins exercised offline; canary tests exclude secrets, labels, CRM and revenue from model requests. `tests/test_injection.py`, `test_security.py`. Live injection test deferred | New source or tool, prompt, model or context changes |
| Caching | Fixed-prefix provider cache instructions and recorded request/page replay in ignored `data/cache.db`; failures retained. Replay cost is zero with original cost separate. `tests/test_cache.py` | Cache keys, scope or retention changes |
| Human review | Loopback forms bind decisions to the reviewed subject and body. Stale forms and later tampering refused. Generic local operator identity; editing deferred. `tests/test_workspace.py` | Review flow or access boundary changes |
| CRM and delivery | One CRM writer into SQLite, owned fields only with person edits preserved. One local send function into a SQLite inbox, human approval, synthetic domain, sender/footer, suppression and idempotence checks. No external delivery adapter or model write tool | New write path, service, destination or recipient |
| Persistent state | SQLite schema 3: runs, calls, spans, claims, approvals, local messages and simulated deals. Migration backups/checksums; immutable lead origins. Failed runs retained; no mid-step checkpoint resume | Migration, memory or state lifecycle changes |
| Tracing | Local span tree, call export and stored cost summaries; `adscout trace`, `export` and `check`. Cloud tracing deferred; LangSmith tracing variables refused | New trace destination or payload |
| Outcome measurement | Explicitly simulated USD deals only. No measured conversion, reply, meeting, revenue or uplift claim | Real outcomes or attribution become available |
| RAG, training, generated code, MCP servers, multiple users | Deferred; none required by this local MVP | First introduction of any of these capabilities |

## System bundle and evidence

Run rows record code revision/dirty state, lockfile hash, agent/prompt/schema versions,
config/seed/media-kit/site-list/price hashes and run options. Role versions derive from
prompt and schema content. Model/source calls carry trace and parent span IDs, status,
usage, cost and explained missing values. Full fetched pages remain in ignored replay data.

- Deterministic evaluation cases: 31 profile-rule, 21 claim-verifier and 30 draft cases in
  `evals/cases/`, plus scaffold cases (90 evaluation tests in total).
- Security evidence and full fake pipeline: `tests/test_security.py`,
  `tests/test_injection.py`, `tests/test_real_pipeline.py`.
- Local workflow: `tests/test_workspace.py`, including real HTTP handler requests with
  sockets blocked, stale/tampered approval, rejection, duplicate placement, suppression,
  CRM and sender prerequisites, unsafe requests and escaping.
- Latest gate, dependency audit, manual review and environment limitations:
  [local MVP verification](docs/local-mvp-verification.md) and [HANDOFF](HANDOFF.md).
- Earlier Phase 1 stub evidence remains in `evidence/runs/`. It is structural evidence,
  not an AI evaluation. Current demo data is ignored and includes its dirty-code marker;
  it is not a clean-tree live evidence run.

The original `phase-2-ai-pipeline` change stays open. Owner labels, approved 30-company
sites/seeds, committed comparison plans and paid baseline/candidate measurements remain
deferred. No winning model tier or multi-agent advantage is claimed. The original research
comparison still needs its 12-call single-agent versus 20-call team-cap inconsistency
resolved before measurement. Person-name detection in claims is a conservative heuristic,
not proof that arbitrary live text contains no personal data.

## Limits and operation

One pipeline run at a time; worker and lead call/page/search caps, per-role token limits,
three concurrent model calls, per-run spend reservation, a 2 MB decoded page cap and at
least 1 s host pacing. Pricing and the Haiku prompt-size guard are enforced before calls.
Budget errors stop; no automatic purchase or credit reload exists. Only the live transport
reads the API key. Live reads and paid calls remain behind PROJECT.md gates.

`uv run --locked adscout demo` creates or resumes `data/demo.db` and serves 127.0.0.1:8765.
Only the local PC/session is trusted; no login or multi-user security is claimed. Host,
Origin, CSRF, request-size and output-escaping checks protect the local form boundary.
Stop with Ctrl+C. Keep databases and failed runs; use a different `--db` for a fresh demo.
Never expose the listener, add a remote, upload traces or enable an external adapter
without the relevant operator gate.

For an interrupted pipeline, inspect `adscout runs`, `trace` and `check` before another
run. The recorder marks a dead local process interrupted and permits retry; a run belonging
to another host requires operator investigation. Never alter migration checksums or reset
a database to hide a failure. For a code regression, stop the server, preserve the DB and
cache, inspect the recorded system bundle, and review a fix against the locked environment
and a copy of the database. Restoring old code does not downgrade schema 3.

Operational owner: Peter Rentopoulos. Maintenance cadence is manual; rerun the gate on
changes, audit dependencies at release, and establish fresh live evidence before enabling
or claiming live model behavior.
