# Resolve stack dependencies

## Purpose and inputs

Act as the solution architect. Infer the minimum missing capabilities needed to make the declared architecture coherent, then recommend implementations from the repository, project catalogs when used, and verified provider documentation.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: `spec`, architecture validation, source contracts, approved component catalogs, and workload/recovery constraints. Reuse validation findings instead of treating unverified components as approved.

## Procedure

1. Turn the agent's intent into required capabilities: request handling, model access, data access, orchestration, tool execution, session state, optional long-term memory, delivery, observability, and governance. Identify existing shared services before proposing new ones.
2. Apply the dependency rules below. For each dependency, record the triggering requirement, consumer, implementation candidates, data handled, lifecycle owner, cost driver, and approval reference.
3. Compare candidates against data residency, authorization boundaries, latency, scale, recovery, platform support, and operating burden. Recommend one primary choice and explain a meaningful alternative where a decision remains open.
4. Produce a dependency graph and proposed spec changes. Use existing project modules or verifiable custom/provider implementations when no catalog is required. If a required catalog is unavailable, mark dependent selections unverified. Detect cycles or conflicting requirements and record a resolution.
5. Return proposed changes to architecture validation. Update cost, IAM, network, threat, and telemetry designs if already generated. Changes to tools require contract and evaluation review.

## Dependency rules

| Trigger | Required design work |
|---|---|
| Structured operational questions | Typed source adapters, scope enforcement, freshness/units checks, deterministic calculations; no automatic vector-store requirement |
| RAG or hybrid grounding | Approved corpus, document ACLs, ingestion/versioning, embedding model, retrieval index, deletion propagation, citations, retrieval evaluation |
| Session memory | Durable session service if required across restarts, user/session isolation, TTL/deletion, filtered history and concurrency behavior |
| Long-term memory | Explicit purpose and consent/policy basis, ownership, retention, correction/deletion, provenance, poisoning defenses, cross-session access controls |
| Write tools | Server-side authorization, explicit approval policy, preview, idempotency, revalidation before execution, audit, reconciliation/compensation |
| Multi-agent orchestration | Bounded delegation, identity propagation, handoff schema, termination/budget rules, shared-state isolation |
| Async or event work | Durable work identity, queue/backpressure, retries, deduplication, dead-letter handling and operational ownership |
| External model/tool | Approved data transfer, authentication, network route, timeout, outage behavior and provider terms review |

## Outputs

- `artifacts/dependency-plan.yaml`: capability decisions, candidates, selected/proposed status, dependency edges, owner roles, and unresolved references.
- `artifacts/spec-dependencies.patch.yaml`: proposed additions/changes with reasons and affected checks.
- Shared result envelope using skill stem `resolve_stack_dependencies`.

## Inventory assistant worked example

Recommend typed inventory-status and forecast tools plus deterministic scenario arithmetic. The example disables memory, so avoid adding a session store. If persistent sessions are requested later, resolve storage, access and retention then. Its structured grounding does not justify adding a vector database. If approved procedure search is later added, introduce the full retrieval lifecycle and revalidate, rather than simply attaching a vector store.

## Completion checks

Every required capability has one proposed or verified implementation, or a specific unresolved decision. Optional components have a business reason. The graph includes storage, identity, network, monitoring, and recovery dependencies, and no missing catalog entry is represented as an approved asset.

## Progression to production

Identify present and future capability needs without provisioning unused production infrastructure early. Add the triggered controls and evidence work to the lifecycle plan whenever the target adds external access, users, providers, stores, write actions or operational reliance.
