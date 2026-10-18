# Security baseline and progression to production

Read this document whenever assessing control applicability, changing deployment scope or generating readiness evidence. It is the shared security requirement for all 17 skills. It defines requirements for the application being built; a written design alone does not establish that controls are implemented or tested.

## Ownership and lifecycle are separate

`governance.profile` describes who runs the project and which administrative processes apply. It never lowers the technical baseline. A single-person project can be a production system.

`lifecycle.stage` describes the intended use: `prototype`, `pilot`, or `production`. Record the target stage and actual/planned capabilities in the specification. Evaluate the target being proposed, and compare it against deployed configuration and actual use when available. A stage label cannot override observed exposure or reliance.

| Stage | Required posture |
|---|---|
| Prototype | Enforce relevant baseline controls from the first working version. Prefer synthetic data and bounded tools. Document unimplemented controls and restrict use to what is actually protected. |
| Pilot | Before shared use or external exposure, verify access boundaries, data isolation, dependency credentials, limits, filtered events, failure behavior and a tested way to disable/revert the pilot. Define the allowed users/data/actions and an accountable operator. |
| Production | Before users or business processes rely on the system, verify the baseline plus target-specific release, recovery, monitoring, incident and maintenance evidence. Freeze the candidate and its configuration. A personal owner can operate it without a corporate review board. |

The effective stage is the strongest of the declared stage and observed/intended use: real operational reliance requires production checks; shared trials or external exposure require at least pilot checks. Sensitive data, paid providers, persistent storage, write actions or high-impact decisions activate their controls at any stage. A hosted model alone does not make a local prototype a production service, but it activates data-transfer, credential and cost controls.

## Required technical baseline

Every skill reports how its work affects these controls. All control IDs must be accounted for during architecture validation and readiness review. Individual skills may reference current upstream evidence for controls outside their scope.

| ID | Requirement | Evidence when the capability is present |
|---|---|---|
| B01 Secrets and credentials | Keep real secrets out of code, prompts, logs, tool payloads and unprotected state. Limit credential scope and support revocation. | Configuration/secret-access review; secret scan where applicable; filtered-error tests; rotate/revoke procedure |
| B02 Access and isolation | Enforce permissions at runtime/tool/data boundaries, using trusted identity context. Separate users/tenants when present. A local-only tool may use OS/file/process permissions. | Allowed/denied cases, cross-user/tenant cases when applicable, and verification of the actual listening/network/file boundary |
| B03 Tools and action authority | Expose only needed capabilities; validate arguments/results and bound side effects. Bind write authority to actual permitted actions; use idempotency/reconciliation for repeatable external writes and recovery for destructive changes. | Contract tests; out-of-scope action rejection; replay/error cases; evidence for standing or per-action authorization as appropriate |
| B04 Untrusted content | Treat user/retrieved/tool content as data. Prevent it from expanding permissions, destinations or execution scope. Instructions complement enforceable controls. | Relevant direct/indirect injection, unsafe destination and unauthorized tool-use cases; no claim that a prompt alone eliminates injection |
| B05 Data handling | Minimize context and logs; use allowed processing destinations; protect retained data with access, retention and deletion rules. Include provider logs, caches and backups where they exist. | Data-flow/field inventory, filtering and denied-disclosure cases, storage isolation and deletion checks where applicable |
| B06 Bounded execution and spending | Bound model/tool calls, tokens, time, retries, concurrency and any paid usage. Distinguish cost notifications from enforced admission limits. | Configuration plus timeout, retry, cancellation, quota and exhausted-budget cases; safe degraded behavior |
| B07 Correctness and safe failure | Validate important calculations/constraints deterministically; ground factual decisions where needed. Handle missing, stale, conflicting or denied evidence without fabricating success. | Domain/tool assertions and failure cases; quality metrics suited to the task; calibrated judgment where useful |
| B08 Change integrity and recovery | Identify the code/configuration/model/tool/prompt versions being run; verify relevant changes; provide an appropriate stop/revert/recover path. | Reproducible version/digest references, relevant dependency/security checks, and exercised recovery for state/actions that need it |

These are required engineering controls whenever their capability exists. Personal ownership, speed, budget, a small user count, owner acceptance or a missing corporate policy is not a reason to waive them. Administrative requirements such as a cost center or external catalog may remain optional.

A capability-specific subcheck may be `not_applicable` only with evidence that the capability is absent within a stated scope. Examples: no cross-tenant test when there is one local OS user and no remote listener; no write-replay check when the tool set cannot write; no database restore when no durable application state exists. The underlying control still has a disposition. For example, memory disabled does not by itself exempt provider logs or other persisted data from B05.

A required baseline failure cannot receive a release pass through risk acceptance. Fix the control, or remove/isolate the capability and verify the reduced scope. Preserve exception handling only for requirements whose governing policy actually permits exceptions; that cannot bypass this technical baseline.

## Capability triggers and revalidation

Reassess before introducing a capability, even if the project profile or stage has not changed:

| Change | Recheck before enabling it |
|---|---|
| Remote access, another user or tenancy | B02/B04/B06, actual network boundary, authentication, authorization, session/cache/data isolation; at least pilot scope |
| Hosted provider or new external tool | B01/B03/B04/B05/B06, destination/data handling, credentials, capability scope, outage behavior and spend |
| Sensitive or real user data | B01/B02/B05/B07, field handling, storage/transfer/retention and representative protected test fixtures |
| Persistent state, memory or retrieval | B02/B04/B05/B08, ownership, poisoning, provenance, deletion, backup and restore as appropriate |
| Write/destructive/payment action | B02/B03/B06/B08, authority, preview/confirmation only as required, retry/idempotency, reconciliation and stop/recovery |
| Production reliance or consequential decisions | All baseline controls plus operational release requirements and scenario-specific harm controls; production stage when reliance exists |
| Model, prompt, tool, schema, dependency or infrastructure change | Invalidate affected evidence and rerun the checks tied to the changed behavior and boundaries |

`unknown` or missing capability facts cannot establish absence. Mark affected evidence unresolved and hold the dependent exposure/promotion while continuing useful design or isolated implementation. Preserve the user's existing authorization; reassessment does not itself require another permission question.

## Evidence and expiration

Use applicability records with control/subcheck ID, capability, scope, required/not-applicable status, reason, owner, evidence reference, evaluated specification/configuration revision, and `recheck_on` triggers. Temporary prototype limitations also need a target stage or explicit condition by which they must be resolved. A calendar review date may supplement, but cannot replace, change-triggered invalidation.

Documented, implemented and tested are separate states. Security prose, mock-only results or an assistant's confidence cannot prove a runtime boundary. Record `pass`, `fail`, `not_run` or `stale` for evidence; use `not_applicable` only under the absence rule. Keep evidence tied to the current release bundle and allowed scope.

Architecture validation produces `artifacts/security-baseline.yaml` and `artifacts/lifecycle-plan.md`: control coverage, effective stage, capability triggers, evidence gaps, prototype limitations, owners and required work before the next stage. Other skills update the affected entries rather than inventing independent security defaults.

## Production readiness requirements

For a production candidate, require current baseline evidence, appropriate representative task and abuse/failure evaluation, and verified deployed configuration. Define load/latency and dependency limits for the real usage pattern; a local scheduled tool can have different targets from a web service. Provide filtered events and actionable incident signals, an accountable operator, credential revocation/disable instructions, a tested release rollback or forward-recovery strategy, and restore/deletion evidence for durable data where applicable.

Record dependency/model maintenance and security-update ownership. Keep development/evaluation data and privileges separated from production wherever those boundaries exist. External CI, Kubernetes, paid monitoring, formal boards and fixed sample counts are not universal requirements; reproducible local tooling and one accountable owner may satisfy the same technical outcomes.

The release-gate skill derives concrete predicates and required evidence from these outcomes and project risks. All required passes must be current before eligibility is reported. Eligibility is a review outcome, not a deployment action or a guarantee that no undiscovered risk remains.
