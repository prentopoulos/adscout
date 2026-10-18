# Define release gates

## Purpose and inputs

Act as the release-readiness designer. Translate approved policies, evaluation criteria, business risk and service targets into explicit promotion gates with attributable evidence.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: validation, architecture/IaC/security/data-handling artifacts, evaluation plan, nonfunctional/FinOps targets, delivery environments and approval policy. Generate gate definitions even when test evidence is not yet available; never manufacture a release pass.

## Procedure

1. Identify promotion stages and the exact release bundle: source commit, container digest, model configuration, prompt/schema/tool versions, infrastructure plan and policy revisions. Evidence must refer to that bundle; material changes invalidate affected evidence.
2. Convert requirements into gates with ID, stage, metric/check, operator, threshold, dataset/cohort, sample requirement, measurement window, evidence validity rule, owner role and failure action. Use supplied approved thresholds; label local defaults as proposals.
3. Keep non-negotiable checks separate from graded quality. Identity failures, prohibited disclosure, unapproved critical dependencies and missing mandatory approvals cannot be averaged away by high relevance scores.
4. Define evidence outcomes as `pass`, `fail`, `not_run`, or `stale`; only a current pass satisfies a required gate. Mark genuinely inapplicable gates with a reason and exclude them from the required set. Record minimum samples and unresolved judge cases explicitly. A missing/null metric is not zero and cannot pass.
5. Define staged rollout, monitoring, rollback triggers and recovery checks. Require a known-good compatible bundle and account for schema/state changes that cannot be reversed by changing a container.
6. Derive readiness as the conjunction of required current gate passes and any required valid approvals. Keep `hold` when required evidence is absent/stale, and `reject` when a mandatory check fails. Exceptions may address only non-baseline requirements explicitly overridable by their governing policy. A required B01-B08 failure cannot be waived: fix it or remove/isolate the capability and verify the reduced scope.

## Proposed inventory assistant baselines — require owner acceptance

G00 and the technical baseline apply across projects. The numerical quality/load thresholds in the remaining table illustrate a hosted service with consequential recommendations. Tailor it to the project before execution; these numbers are not defaults for every app. For a reversible local prototype, use a focused set of representative tasks plus all relevant authorization, data-handling and business-rule checks; skip hosted availability, staged traffic and formal approval gates that do not apply. A higher-risk personal app may still require substantial evidence. Freeze selected criteria before evaluating a candidate.

| Gate | Proposed condition | Evidence/stage |
|---|---|---|
| G00 Baseline and lifecycle | Effective target stage verified; every triggered B01-B08 check has current passing runtime/test evidence; no unsupported exemptions | Baseline report, actual/configured scope and lifecycle plan before enabling affected capabilities or promotion |
| G01 Conformance | All required patterns, models, tools, region/data policy and governance approvals verified | Architecture/policy records before production |
| G02 Security | Zero observed M05 failures; no unresolved required baseline failures; other critical/high risks need remediation or a permitted non-baseline exception | All applicable threat/access/redaction cases before production |
| G03 Domain and tools | M04 = 100%; M10 = 100% of required assertions | Deterministic/contract suite in CI and staging |
| G04 Answer quality | M01 >= 95%; M02 >= 98%; M03 >= 90% | Held-out representative quality cohort before promotion |
| G05 Failure behavior | M06 = 100% | All stale/denied/unavailable/budget cases |
| G06 Performance | M07 p95 <= `spec.nonfunctional.p95_latency_ms`; M08 <= 1% | At declared peak load in staging, with cold-start/error breakdown |
| G07 Cost | M09 <= `spec.finops.max_cost_per_successful_task`; forecast monthly cost <= budget | Reconciled or explicitly qualified conservative estimate, all cost drivers included |
| G08 Operability | Alerts, access restrictions, rollback rehearsal and recovery objectives verified | Runbook and recorded staging exercises |
| G09 Release evidence | Immutable artifacts, provenance, scans, protected environment and accountable sign-off present | Exact candidate bundle and delivery records |

Proposed minimum evaluation design: at least 200 representative quality cases, plus 60 distinct adversarial/access/privacy cases and all identified domain/contract/failure cases. Run stochastic cases three times; report per-run and pooled quality, and require each run to meet the quality gates. Any hard-control failure fails its gate. Require at least 200 eligible factual claims for M02 and manually review unresolved labels. Avoid counting refusal-only cases as grounded-answer successes. Report uncertainty and coverage alongside point thresholds.

For a hosted service, an illustrative G06 load window is 30 minutes at five requests/second, subject to the actual traffic profile and test budget. A proposed 99.5% monthly availability objective would need measurement over its production window, not just a staging load test. Example recovery targets of RTO 60 minutes and RPO 15 minutes require state-specific drills if adopted. The supplied local specification intentionally leaves these hosted-service targets inapplicable.

For a service that supports progressive traffic routing, proposed rollout: 5% eligible traffic, then 25%, then 100%, with at least 30 minutes and 100 completed requests per step; extend the window at low traffic. Roll back or halt immediately on confirmed unauthorized disclosure/action. For sustained latency/error/cost breaches, define a five-minute alert window plus minimum request count in the rollout policy to avoid interpreting no traffic as a pass. Verify rollback time in rehearsal. Initial traffic percentages/windows must fit the actual project. A local tool can instead use a smoke check and a verified version-control/configuration rollback; do not invent traffic-routing infrastructure.

## Outputs and example

Write `artifacts/release-gates.yaml` and `artifacts/release-readiness.md`, plus the shared result envelope under stem `define_release_gates`. Gate YAML includes gate IDs, proposed/approved status, threshold source, evidence requirements and enforcement owner. The readiness report separately states `hold`, `reject`, or `eligible_for_promotion`.

For the supplied local inventory example, formal approvals and a cloud region are not required. Readiness for a working release remains `hold` until model/tool configuration and applicable verification evidence exist. Do not attribute the hold to optional organization controls. Gate definitions can be complete while execution evidence is still missing. For examples/inventory-assistant.production-target.spec.yaml, retain personal ownership but activate production checks for its shared, hosted, persistent and sensitive-data scope. Its missing evidence yields `hold`; in a gate evaluator, a tested baseline failure yields `reject`. Neither result can be changed by keeping the personal profile.

## Completion checks

Every required gate has a computable predicate and evidence source. Production also requires the operational evidence in SECURITY_BASELINE.md: appropriate observability/incident response, maintenance ownership, release recovery and durable-data recovery/deletion where applicable. Missing/stale evidence cannot pass. Cost/quality denominators match upstream definitions. Proposal status, reviewer roles and rollback behavior are explicit.
