# Observe, budget and recover

Use when recording runs, tuning cost/latency or adding operational reliance. Reuse Agent
Builder telemetry and FinOps definitions; this procedure connects their output to response.

## Run records

Define a versioned record with run/request/trace correlation IDs, system bundle ID,
start/end time, terminal status, safe error category, outcome-validation status and duration.
Where used, include actual provider/model, tool outcomes, prompt/index versions, token usage,
price revision/currency, estimated cost, usage availability/reason, budget exhaustion,
guardrail events and approval reference. Distinguish success, failure, blocked, cancelled,
timeout and pending approval. A pending run is not a completed success.

Record counts/metadata by default. Keep raw prompts, messages, tool payloads, checkpoints and
user identifiers out of routine logs. Allow necessary diagnostic data only in access-controlled,
redacted, retention-limited storage. Trace observable tool/model steps and short decision
summaries; do not request hidden chain-of-thought.

Validate events at emission and ingestion. Test malformed/partial JSONL, missing usage,
duplicate run IDs, interrupted writes and exporter failure. Concurrent writers need a
serialization/transaction strategy. Required audit events must not disappear through routine
trace sampling; failure handling must remain bounded and must not emit raw fallback logs.

## Metrics with explicit denominators

Define each numerator, denominator, unit, measurement window, eligibility and minimum count.
Separate technical completion from independently evaluated task success. Report blocked and
pending runs separately, retain all failures, and avoid double-counting retried attempts.

Track latency percentiles, time to first token if streamed, error/timeout rate, tool failure,
task success, refusals, cost per successful task, budget exhaustion and any applicable
retrieval freshness/cache quality signals. Cost per successful task includes failed-attempt
costs in the same window; zero successes makes it undefined. Unknown usage has a coverage
metric and cannot silently reduce reported cost.

Use low-cardinality metric labels. Keep individual run/session IDs in protected records,
not metric dimensions. Specify how percentiles are computed and show sample counts; an
empty window is insufficient evidence, not zero latency or perfect reliability.

## Budgets and incidents

Use a dated, unit-correct price table and separately meter input/output/cached usage where
reported. Include embedding, judges, rerouting, retries, storage and local/cloud resources.
Distinguish estimates from reconciled billing. Exercise admission rejection and concurrent
budget reservation, not just threshold alerts.

For each actionable signal specify an owner, window, minimum observations, threshold,
response and recovery verification. Use [RUNBOOK.md](../assets/RUNBOOK.md) or an existing
equivalent. Test at least the changed failure path: provider outage, runaway calls, ingestion
failure, unauthorized access, checkpoint corruption or quality regression.

Recovery sequence: contain the affected capability; preserve sanitized evidence and version
IDs; identify affected users/data/actions; reconcile ambiguous writes; restore a compatible
bundle/state or apply forward recovery; verify health and representative behavior before
resuming exposure. Record the incident and add a sanitized regression case.

## Operating cadence

Record the owner and cadence in AI_OPS. A small routine catches slow decay:

- Each week: review a sample of failed, low-scored, long and negatively rated runs; classify
  causes; add sanitized representative failures to regression cases; check cost per
  successful task and steps per run; review guardrail blocks for false positives.
- Each month: rerun the full evaluation on the current system version; check provider
  model retirement and pricing notices and plan migrations as releases; update dependencies
  through the normal gate; remove unused tools, credentials and permissions; check retrieval
  and data freshness.
- Always: a named owner and escalation route, a runbook for the main failure modes, and a
  tested stop switch per capability and fallback model.

A local prototype can use one JSONL stream, a report command and one operator. Hosted
dashboards, paging services and distributed tracing are additions for demonstrated needs.
Done when a deliberately induced failure creates the expected record/signal and the operator
can execute a tested stop/recovery path within the declared scope.
