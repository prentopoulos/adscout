# Orchestrate CI/CD

## Purpose and inputs

Act as the delivery pipeline designer. Produce build, test and deployment steps for the declared stack, enforcing the previously defined release gates and evidence chain.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: `spec`, repository manifest, IaC/IAM designs, evaluation plan, release gates, project CI templates and artifact policies. If external CI is unnecessary, describe a reproducible local check/build/release script. For a hosted pipeline with an unspecified provider, produce a provider-neutral DAG and adapter requirements; do not claim it is executable.

## Procedure

1. Identify triggers, branch protections, environments, artifact stores and separately scoped build/test/deploy identities. Restrict untrusted pull-request jobs from deployment credentials or production data. Pin third-party pipeline actions/images/dependencies through approved versions or digests.
2. Design pull-request validation: spec/policy checks, formatting/type checks appropriate to the stack, secret/dependency/IaC scanning, deterministic domain/unit tests, tool-schema contracts, access/redaction cases, and small synthetic regression evaluations. Mock paid/private dependencies unless the job has an explicit authorized integration-test environment.
3. On trusted integration, build the immutable artifact once; produce dependency inventory, provenance and scan evidence; version prompts, schemas and model configuration with it. Tie all downstream evidence to its digest and configuration revisions.
4. Generate a reviewed IaC plan using the permitted identity. Bind any eventual apply to that exact plan, source revision, target environment and bounded validity. Re-plan and re-review after drift or changes. Keep destructive changes and data migration implications visible.
5. Deploy the candidate to the appropriate test/stage environment using approved workload authentication. Run actual integration/access checks, held-out quality/safety evaluation, planned load/cost checks and recovery rehearsals. Capture sanitized evidence without embedding secrets or raw sensitive payloads in logs.
6. Enforce G00 baseline/lifecycle and the applicable release gates mechanically. Reject unsupported not-applicable declarations and hold promotion when current required evidence is absent. Compare the candidate capabilities and deployed configuration with the reviewed scope; flag expanded access/data/tool privileges before enabling them. Promote the same immutable bundle only with current passing evidence and any required environment approvals. Use the release plan's progressive rollout, monitoring and rollback rules. Record deployment and catalog status without treating a submitted job as a successful deployment.
7. Define cancellation, concurrency per environment, bounded retries, timeouts and cleanup. Retry transient infrastructure failures carefully; never rerun a failed stochastic evaluation until it happens to pass while discarding earlier runs.

## Pipeline stages

```text
PR: validate -> static/security checks -> deterministic/contract tests -> small eval
Trusted integration: build + provenance -> immutable candidate
Candidate: reviewed IaC plan -> test/stage deploy -> integration + full eval + load/recovery
Production: gate evaluation + approvals -> progressive rollout -> verify -> record evidence
Failure: stop promotion -> preserve evidence -> rollback/reconcile -> verify recovery
```

Jobs that can execute independently may run concurrently; dependencies, environment mutations and approvals remain ordered.

## Outputs

- `artifacts/ci-cd-plan.yaml`: DAG, triggers, job inputs/outputs, identities, permissions, gate references, caches, timeout/retry/concurrency rules and failure actions.
- `artifacts/pipeline-implementation.md`: actual provider adapter/template mapping, evidence storage, deployment verification and operational instructions.
- Shared result envelope using skill stem `orchestrate_ci_cd`.

## Inventory assistant worked example and checks

A change to the inventory calculation runs deterministic arithmetic and contract cases. A prompt/model/tool change also triggers grounded-answer, trajectory, failure-behavior and adversarial regressions. A schema change reruns adapter and backward-compatibility checks. A runtime/IAM/network change reruns integration and access verification.

Complete when every required release gate has a producing job and an enforcing job, every deployment uses the tested immutable bundle, untrusted jobs cannot acquire privileged credentials, and missing CI-provider configuration is clearly identified. Workflow syntax and actual execution are separate checks; record each honestly.
