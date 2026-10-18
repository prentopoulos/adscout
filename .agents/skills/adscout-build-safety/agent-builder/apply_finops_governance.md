# Apply FinOps governance

## Purpose and inputs

Act as the AI cost-governance designer. Derive allocation metadata, cost forecasts, and enforceable usage boundaries from the specification and resource blueprint.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: `spec`, IaC blueprint, workload estimates, approved tagging policy, verified dated rate cards, billing scope and accountable cost owner. The word `apply` means apply policy to the design; this prompt does not change a billing account.

## Procedure

1. Map organization metadata to supported cloud labels/tags and application usage dimensions. Proposed keys are `use_case_id`, `project_group`, `owner`, `cost_center`, `environment`, `data_classification`, and `managed_by`. For a personal/local project, use local usage metadata and skip cloud tags or cost-center fields that do not apply. Validate actual platform syntax, inheritance, and resource support. Keep personal/sensitive values out of labels. Require a cost center only when a real allocation policy needs one; identify the project owner for any paid usage.
2. Model monthly cost as model usage + compute + retrieval/embedding + storage + data processing + network + telemetry + delivery/evaluation + allocated shared services. Include failed requests, retries, tool fan-out, cache behavior, minimum instances, and idle capacity where applicable.
3. Calculate model cost with separately metered input/output/cached token classes and current rates. Record region, currency, pricing date, units, and exclusions. Use symbolic rates if prices are unavailable. Give low/base/peak scenarios; peak requests per second is not average monthly utilization.
4. Define `cost_per_successful_task = total_attributable_cost / successfully_completed_tasks` for the same measurement window. Include the cost of failures in the numerator. For zero successes, return undefined and fail the corresponding release check; never return zero. Distinguish estimated live cost from reconciled billing.
5. Specify request token/model/tool budgets, bounded retries, maximum concurrency, per-user/project admission quotas, and resource limits. Define who may change each limit and the degraded behavior at exhaustion. Avoid abrupt automatic shutdown of operational services without an approved response plan.
6. Configure proposed budget notifications and forecast alerts, owner routing, anomaly checks, and an explicit response runbook. A billing alert alone is not a hard spending cap. [Google Cloud's budget documentation](https://docs.cloud.google.com/billing/docs/how-to/budgets) makes that distinction.

## Outputs

- `artifacts/finops-policy.yaml`: required/proposed metadata, ownership, budget scope, notification policy, enforcement points, exceptions and unresolved inputs.
- `artifacts/cost-model.md`: assumptions, dated/symbolic prices, calculations, sensitivity, allocation and reconciliation process.
- Shared result envelope using skill stem `apply_finops_governance`.

## Inventory assistant worked example

The sample's proposed budget is USD 1,000/month with USD 0.05 per successful task. Its limits are 8,000 input and 1,500 output tokens, four model calls, and six tool calls per request. Treat the token limits as aggregate request limits across all calls, not a fresh allowance per call. At 20,000 successful tasks, USD 0.05/task consumes the full USD 1,000 envelope; reserve room for fixed and shared costs. This is arithmetic on synthetic targets, not a vendor price estimate.

## Completion checks

All cost drivers and metadata gaps are visible. Units and denominators agree. Budget alerts and enforcement mechanisms are distinguished. No unknown price is represented as zero, and no sample limit is labeled mandatory project policy.

## Progression to production

Recalculate budgets and enforceable limits when users, provider rates, retries, tools or concurrency change. Prototype traffic assumptions do not establish production affordability. B06 remains required even without a billing department or cost center.
