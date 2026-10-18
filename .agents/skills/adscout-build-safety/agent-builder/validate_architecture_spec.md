# Validate architecture specification

## Purpose and inputs

Act as the architecture conformance reviewer. Evaluate the developer's YAML specification against the project requirements and any applicable supplied patterns and expose incompatible or unsupported combinations before generation begins.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: `spec`, versioned pattern catalog, model/runtime/region compatibility records, project policy bundle, and any approved exceptions. A missing catalog prevents a conformance claim only when the project requires that catalog. Otherwise validate against owner requirements and local architecture decisions.

## Procedure

1. Parse YAML safely, reject duplicate keys, and validate required objects, types, enums, numeric bounds, and source/tool reference integrity against contract v0.3. Report each issue with a YAML field path and corrective action. Preserve the original file.
2. Separate missing structure from unresolved values. A missing required object is invalid; a null required approval reference is an unresolved dependency, while an inapplicable formal approval needs only its documented applicability reason. Identify conflicting declarations, such as `cloud: gcp` with Bicep, a disabled RAG mode with an unexplained mandatory vector store, or a write tool contradicting read-only non-goals.
3. Map every component and data flow to supplied patterns or local architecture decisions. Formal L1/L2 mapping is optional unless the project requires it. Check permitted cloud, region, runtime, framework, model, grounding store, memory, integration protocols, and data class as a combination. A model appearing in a catalog is insufficient if its region or data-use restrictions do not match.
4. Validate authorization, external data transfer, source entitlements, retention, recovery objectives, and operational action boundaries. For multi-agent patterns, check each delegated tool scope and shared memory boundary. Validate approved fallback models separately.
5. For each deviation, record the governing rule, evidence, impact, remediation, and any exception's scope, owner, expiry, and approval record. Distinguish an explicit policy rejection from absent evidence.
6. Produce a proposed normalization patch for spelling or structural improvements. Leave architectural choices for the dependency resolver. Identify which checks must repeat after accepting that patch.

## Outputs

- `artifacts/architecture-validation.yaml`: `structural_validity`, `policy_conformance` (`pass`, `fail`, `unverified`, `not_applicable`), `deployment_eligible`, requirement checks, component-to-pattern mapping, deviations, and unresolved inputs.
- `artifacts/spec-normalization.patch.yaml`: proposed field-level changes with before/after values and reasons; empty changes are acceptable.
- `artifacts/security-baseline.yaml`: B01-B08 coverage, capability/subcheck applicability, implementation and evidence status, evaluated scope/revision and revalidation triggers.
- `artifacts/lifecycle-plan.md`: declared/target/effective stage, observed or planned capability changes, prototype limitations and required work before pilot/production.
- Shared result envelope using skill stem `validate_architecture_spec`.

Set `deployment_eligible: false` when required approval, region, data scope, or security evidence is unavailable. Use `needs_input` for an otherwise useful validation with missing required evidence; use `blocked` for malformed input or a confirmed prohibited architecture.

## Inventory assistant worked example

For [the example spec](examples/inventory-assistant.spec.yaml), local execution without IaC and an advisory tool set are coherent. Formal approval, cloud-region selection and organization catalogs are not required for its declared local prototype. Model selection and actual tool contracts remain unresolved for an executable build. Record those real gaps and keep `deployment_eligible: false` until the selected run/release scope has the required evidence. Use `policy_conformance: not_applicable` if no separate policy bundle applies; still evaluate owner requirements and safety constraints. Do not treat absent optional catalogs as defects.

## Completion checks

Every required field, selected component, lifecycle capability and baseline control has a disposition. Unknown capability facts cannot be treated as false. A production target cannot inherit prototype exemptions without current supporting evidence. Every failure cites an actual rule or input conflict. Every approval claim has evidence. The report distinguishes structural validity, policy conformance, and release eligibility, and lists exact inputs required to finish review.
