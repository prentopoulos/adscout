# Generate AI asset metadata

## Purpose and inputs

Act as the AI catalog curator. Produce structured discovery records for models, prompts, agents and their dependent tools without confusing registration, approval, deployment and retirement states.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: `spec`, project registry schema/naming rules, model/tool catalogs, prompt manifest, architecture, immutable artifact references, evaluation evidence and release decision. Generate local registration payloads; publishing to a registry is a separate authorized action.

## Procedure

1. Identify each asset and whether to reference an existing catalog entry or propose a new one. An agent that uses a registered model should link its approved model/version; it should not create a duplicate model record automatically.
2. Assign stable local IDs and versions using supplied naming rules. When rules are absent, mark IDs provisional. Include type, name, concise purpose, capability tags, intended users, business owner role, technical owner role, support reference, lifecycle status and source repository/revision.
3. Record dependencies with exact versions/digests: models, prompts, tools/schemas, runtime, data products and architecture patterns. Include allowed data classes, environments/regions, access process, authorization scopes, operational action limits and usage/cost constraints.
4. Link evaluation datasets/runs and release evidence to the exact asset version. Record limitations, known risks, license/provider terms where supplied, approval references, expiry/review date, and whether a dependency changed since evaluation. Use null for absent evidence rather than fabricated identifiers.
5. Validate against the real registry schema when available. If no external registry is needed, use versioned local records as the catalog. If an external registry is required but its schema is unavailable, emit the proposed canonical schema and field mapping while leaving external registration unresolved. Check required fields, dependency resolution, duplicate IDs and lifecycle transitions.
6. Define updates and retirement: owner review, compatible/breaking changes, deprecation notice/reference, replacement asset, dependency impact, access removal and retention-aware archival. Update deployment status only from verified deployment evidence.

## Canonical record shape

```yaml
metadata_schema_version: "0.2"
asset_id: inventory-planning-assistant
asset_type: agent
version: "0.1.0"
name: Inventory Planning Assistant
description: Advisory explanations and comparisons grounded in authorized inventory and forecast data.
lifecycle_status: draft
registration_status: not_submitted
approval_status: not_required
deployment_status: not_deployed
owners:
  business: project-owner
  technical: project-owner
capabilities: [stock-shortage-explanation, advisory-scenario-comparison]
data_classification: internal
deployment_target: local
allowed_regions: []
region_applicability: not_applicable
dependencies: []
source_ref: null
artifact_digest: null
evaluation_refs: []
approval_refs: []
limitations:
  - Does not place purchase orders or update inventory records.
review_due: null
```

This is a synthetic proposed record shape. With `deployment_target: local` and `region_applicability: not_applicable`, no hosted region is required. For a hosted asset, empty `allowed_regions` means no regions verified, not unrestricted deployment. Populate dependencies from actual manifests; missing required references keep the record a draft. Link a schema alongside records so consumers can interpret fields and enums consistently.

## Outputs

- `artifacts/catalog/asset-metadata.schema.json`: canonical or supplied registry schema reference/adapter.
- `artifacts/catalog/agent.yaml`, `artifacts/catalog/prompts.yaml`, `artifacts/catalog/model-references.yaml`: records/references with current evidence status; include tools when the target catalog requires them.
- `artifacts/catalog/registration-plan.md`: target schema mapping, duplicate checks, unresolved fields, update/retirement process and proposed publication payload locations.
- Shared result envelope using skill stem `generate_asset_metadata`.

## Inventory assistant example and completion checks

The example agent remains draft and not deployed. Formal approval is not required under its personal-project applicability record; this is distinct from having received approval. Reference the local prompt and tool manifests, and leave actual implementation/evaluation identifiers unresolved until they exist.

Complete when required fields and dependencies have verified values or explicit gaps, evidence matches asset revisions, sensitive data/secrets are absent from catalog descriptions, and lifecycle/registration/approval/deployment status remain independent.

## Progression to production

Record declared/effective lifecycle stage, allowed user/data/action scope, baseline evidence references and unresolved production limits per version. Mark affected evidence stale after capability changes; a personal owner or registered asset is not proof of readiness.
