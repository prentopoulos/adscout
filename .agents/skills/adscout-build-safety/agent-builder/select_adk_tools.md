# Select agent tools

## Purpose and inputs

Act as the project tool integrator. Match requirements to existing project functions, available catalog tools or justified custom tools, and identify precise gaps.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: `spec`, versioned project tool catalog inventory, tool/source contracts, framework/runtime version, dependency plan, IAM mapping and threat findings. The filename is retained for compatibility; use any framework or custom orchestration. If ADK is selected, its public documentation is an optional implementation reference.

## Procedure

1. Decompose business intent into atomic capabilities and observable outcomes. Prefer deterministic APIs/calculators for facts, constraints and arithmetic. Identify whether each capability reads, calculates, or changes an external system.
2. Match each capability to catalog entries using semantic fit, contract/version, approval status, data-class/region eligibility, authentication, access scope, reliability, latency, cost, and ownership. Verify runtime/model compatibility against the selected framework/runtime release.
3. Select the smallest sufficient set. For native functions, OpenAPI or MCP adapters, document the transport and schema mapping. Introduce agent-to-agent delegation only for an actual capability need with a defined handoff and security boundary.
4. Record timeout, maximum result size, retry/idempotency policy, authorization context, permitted destinations, source freshness, and failure behavior. Tool identity/scope must derive from authenticated server context, not model-authored claims.
5. When no approved tool exists, produce a gap specification: capability, proposed input/output, backend owner, data/control requirements and validation needed. Mark it `proposed_new`; never fabricate a project tool catalog ID or approval.
6. Trace selected capabilities back to architecture, IAM, cost, threat and evaluation requirements. Return relevant changes for revalidation. Restrict the exposed tool list to this manifest; discovery alone does not authorize invocation.

## Outputs

- `artifacts/tool-selection.yaml`: requirement ID, tool ID/version, selection status (`selected_approved`, `candidate_unverified`, `proposed_new`, `rejected`), catalog/contract references, rationale, permissions, budgets, side effects and owner role.
- `artifacts/tool-gaps.md`: missing capabilities and reviewable proposed contracts.
- Shared result envelope using skill stem `select_adk_tools`.

## Inventory assistant worked selection

| Requirement | Candidate capability | Key constraint |
|---|---|---|
| Explain available stock | `get_inventory_status` | Item/location/date key, units, as-of time, caller's inventory scope |
| Explain predicted risk | `get_demand_forecast` | Same item/location/time horizon, forecast version, uncertainty where available |
| Compare options | `compare_inventory_options` | Deterministic arithmetic, provenance, validated operational constraints; advisory only |

These names originate in the local example, not a verified project catalog. A shared catalog is optional: inspect existing project functions and contracts or propose new ones. Keep unimplemented/unverified contracts marked as candidates. Owner-approved custom tools need no invented external catalog approval. General web search, arbitrary SQL, shell execution, and inventory-record modification are outside this example's requirements.

## Completion checks

Every functional requirement maps to an approved choice or a specific gap. Each selected tool has bounded behavior, an accountable owner and an authorization model. Redundant capabilities and unjustified external actions are excluded.

## Progression to production

Treat adding a provider, write capability, payment or destructive tool as a capability change. Update the baseline, permission, budget, schema and recovery requirements before enabling it; prototype read-only evidence cannot authorize a new write.
