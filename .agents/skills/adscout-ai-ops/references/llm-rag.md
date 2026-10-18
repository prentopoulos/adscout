# Operate LLM and retrieval pipelines

Load the sections triggered by the change. RAG, gateways, semantic caching and specialized
inference servers are optional capabilities, each justified by measured project needs.

## Retrieval and ingestion

1. Define source ownership, access scope, schema, content revision, provenance, freshness,
   retention and deletion. Validate before indexing; quarantine malformed inputs with a
   bounded, sanitized error record. Treat retrieved instructions as untrusted content.
2. Version parsing, chunking, embedding model/revision/dimensions, distance metric and
   retrieval/reranking settings. Changing the embedding space requires rebuilding or
   explicitly migrating the index; matching dimensions alone does not prove compatibility.
3. Make ingestion idempotent using stable source/document IDs plus content and pipeline
   revisions. Handle updates, deletes, duplicate deliveries and interrupted batches.
   Content hashing alone does not remove chunks belonging to an older document revision.
4. For a full refresh, build an inactive index, validate counts/schema/ACLs and retrieval
   quality, then switch the active pointer atomically. Pin each request to one index version;
   retain the previous index until in-flight requests drain and rollback is verified.
   Test a failed build and a concurrent query during the swap.
5. Enforce access filtering at retrieval, before model context is assembled. Return source
   IDs/revisions and freshness evidence. Test absent, contradictory, stale and unauthorized
   documents. Define abstention behavior when supporting evidence is missing.
6. Measure retrieval recall/precision against known relevant documents and evaluate answer
   grounding separately. Freeze the corpus for comparable sweeps; record top-k, chunking,
   embedding and reranker revisions. Tune on development cases, validate on held-out cases.

## Cache correctness

Scope cache lookup by trusted tenant/access context and relevant prompt/model/policy,
corpus/index and generation versions. Apply expiration and invalidation for source deletion,
permission changes and policy changes. Recheck authorization on hits.

Test paraphrases and near-misses with different entities, dates, negation or versions.
Similarity thresholds alone may not distinguish them; use typed distinguishing keys,
metadata filters, reranking or bypass. Disable caching where context or side effects make
reuse invalid. A cached response still passes output policy and contributes to metrics.
Report false hits, quality, hit rate, cold/warm latency and actual attributable costs together.

## Gateway and budgets

Centralize provider adapters when multiple callers need shared routing, limits or credentials.
Validate structured responses and enumerate supported error classes. Define per-attempt
timeouts within the total request deadline, bounded retries with backoff/jitter, cancellation
and circuit behavior. Retry only classified transient errors; reconcile ambiguous billable
or state-changing requests before repeating them.

Fallbacks need their own quality, schema, data-destination and cost checks. Record actual
provider/model/route. Enforce aggregate limits across routing/classification, embedding,
generation, judge calls, retries and fan-out. Reserve shared budget atomically when calls
can run concurrently; reconcile estimates with reported usage. Unknown prices/usage are
unknown, never free. A dashboard alert is not an enforced cap.

## Reduce spend

Measure tokens and cost per step and per successful task first; output tokens usually cost
more than input. Apply levers roughly in order of payoff and rerun the same evaluation cases
after each, because a cheaper path that fails more often costs more per success:

1. Route or cascade: a fast model first, escalating when validation or confidence fails.
2. Order prompts from most to least stable (tool definitions, instructions, reference text,
   then conversation) and use the provider's prompt caching; keep timestamps and per-user
   values out of the cached prefix.
3. Compact long histories and drop tool results that later steps no longer need.
4. Trim tool results at the source: IDs and required fields, paginated, not whole documents.
5. Expose only the tools a step needs; load large tool sets on demand.
6. Constrain output with schemas and maximum lengths.
7. Send work that can wait to the provider's batch interface; use the semantic cache rules
   above where answers are genuinely reusable.
8. Keep hard step, token and spend caps per run so cost stays bounded when a loop misbehaves.

## Performance and serving

Profile the request critical path before changing architecture. Record time to first token,
end-to-end duration, p50/p95, concurrency, errors and cold/warm cache conditions with sample
counts. Parallel span durations may overlap; their sum is not necessarily wall-clock time.
Streaming can improve perceived latency without reducing total work. Specify how output
filtering works before bytes reach a user; a final check cannot retract already-streamed text.

Compare quality and cost with latency under the same workload. Add GPU inference servers or
vector tuning only when measured scale warrants them; verify supported APIs for pinned
versions. Follow [evaluation](evaluation.md) for prompt A/B experiments and regression gates.

Done when changed paths have ordinary, failure and regression evidence, and active index,
cache and provider versions can be identified for an observed request.
