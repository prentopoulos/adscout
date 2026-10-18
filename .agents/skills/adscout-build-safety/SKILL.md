---
name: adscout-build-safety
description: Apply relevant engineering workflows to AdScout architecture, dependencies, tool contracts, data handling, cost controls, telemetry and phase readiness. Use for those boundaries, not as a mandatory full audit of every edit.
---

# AdScout build safety

Read [PROJECT.md](../../../PROJECT.md) and the affected OpenSpec design/tasks. Follow current
scope and existing authorization. This skill grants no spending, publication or data-transfer
permission and adds no per-edit approval ritual.

The full 17-workflow Agent Builder collection is preserved under
[agent-builder](agent-builder/README.md). **First read the project adaptation below**, then the
[shared contract](agent-builder/FOUNDATION_CONTRACT.md), [baseline](agent-builder/SECURITY_BASELINE.md)
and only workflows relevant to the current boundary. Source examples are not project defaults.

## Project adaptation

- PROJECT owns scope, decisions and operator gates; OpenSpec owns requirements/design/tasks.
  Apply source questions to those records and actual code. Do not create a competing YAML
  project spec, mandatory catalog, or 17 separate result envelopes.
- Source frameworks, cloud defaults, inventory examples, sample budgets and evaluation counts
  are illustrative. Use this project's actual stack, lockfile and gate.
- Current target: a single-user local portfolio prototype on the owner's PC. Planned but
  deferred (absent, not silently implemented): hosted model API calls, live search, fetch
  and enrichment, a HubSpot sandbox, Langfuse tracing and a sandbox inbox. Absent by §5:
  real sends, real personal data. Not planned: remote access, multiple users, deployment.
- Term mapping: "tools" are the research agent's read-only search and fetch tools plus
  typed adapters for model, enrichment, CRM and send; "evaluation" is deterministic rule
  and field checks plus LLM-judged draft and brief cases on fixed sets; "model versions"
  are model ID, prompt version and agent version tagged on every lead; "tracing" is a
  span and log row per pipeline step with tokens and cost.
- Gates: spend, accounts, live reads, sends, publishing and deployment (PROJECT.md §6). A
  document or mock cannot close one.
- The source's inventory example, cloud defaults and production release machinery do not
  apply; Ship is light here (one container at most). The realistic threats are prompt
  injection from fetched pages, non-compliant email, personal data and CRM corruption.
- Use existing artifacts for small reviews. Substantial reviews go in docs/reviews with
  scope/revision, applicability, findings, evidence, owner, next action and recheck trigger.

Read [adscout-ai-ops](../adscout-ai-ops/SKILL.md) for system versioning, evaluation, retrieval, state, training and operations.

## Route the work

| AdScout boundary | Complete workflows to read in agent-builder |
|---|---|
| Pipeline architecture and phase scope | validate_architecture_spec.md, Architecturebuild.md |
| Dependencies and package structure | resolve_stack_dependencies.md, scaffold_repo_tree.md |
| Research tools and model, enrichment, CRM and send adapters | select_adk_tools.md, generate_tool_schema.md |
| Fetched web pages, company and contact data, credentials | assess_threat_vectors.md, design_pii_redaction.md; map_rbac_policies.md (deferred until a second user or role exists) |
| Run records, traces, lead source and version tags | configure_telemetry_schema.md, generate_asset_metadata.md |
| Model, search and enrichment spend; cost per lead | apply_finops_governance.md |
| Offline eval suite, CI and phase readiness | generate_eval_metrics.md, define_release_gates.md, orchestrate_ci_cd.md |
| Infrastructure proposal | design_iac_blueprint.md (deferred until a hosted deployment is proposed) |
| Scoring, research and drafting prompts; agent behavior | standardize_system_prompt.md plus relevant tool/data workflows |

Source filenames above resolve in [agent-builder/](agent-builder/README.md).
Read [adscout-eval-review](../adscout-eval-review/SKILL.md) for evaluation, scoring and
funnel-figure evidence.
For an explicitly comprehensive review account for all 17 workflows; for normal work record
only the relevant scope. Deferred controls must be revisited when their capability is added.

## Completion

Trace each material failure to a control, enforcement point, test and requirement. Separate
proposed, implemented, tested and externally verified. Unknown usage stays null; a mock or
local run is not a live result. Preserve failed evidence and unresolved dependencies.

[Source manifest](references/source-manifest.json) records the exact Agent Builder copies.
