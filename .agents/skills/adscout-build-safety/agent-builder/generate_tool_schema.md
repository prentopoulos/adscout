# Generate tool schemas

## Purpose and inputs

Act as the tool-contract engineer. Generate precise input/output schemas and adapter mappings that let the selected model and agent runtime call approved tools correctly.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: tool-selection manifest, actual API/function contracts, source types/units, pinned runtime/model schema capabilities, IAM and data-handling policies. If backend contracts are missing, emit proposed schemas with explicit unverified status.

## Procedure

1. For each tool, define its name, single responsibility, invocation conditions, side effects, required inputs, output envelope, and errors. Carry stable tool/version IDs from selection.
2. Generate canonical JSON Schema with explicit required fields, bounded strings/arrays, enums, numeric ranges, units, timestamp semantics and unknown-field policy. Specify null versus absent versus empty behavior. Keep authentication, user identity, roles and approval evidence in trusted server context.
3. Generate a separate provider/runtime adapter mapping. Document the supported schema subset and any unsupported constraints that must be enforced in runtime validation. A canonical JSON Schema is not automatically a valid model function declaration. Verify schema format checks are actually enabled.
4. Validate arguments before any backend call and validate outputs before model consumption. Resolve item/location/date keys unambiguously; enforce matching units/horizons and freshness. Return structured safe errors such as `NOT_AUTHORIZED`, `NOT_FOUND`, `STALE_DATA`, `INVALID_ARGUMENT`, `UPSTREAM_UNAVAILABLE`, and `BUDGET_EXCEEDED`.
5. Define timeouts, pagination/result limits and retry policy. Read operations may retry transient failures within the request budget; write operations need idempotency and state reconciliation. Bind any write approval to the exact action/arguments and recheck server-side.
6. Supply valid, invalid and boundary examples. Test unexpected properties, overlong values, malformed dates, negative quantities where forbidden, mismatched units, unauthorized scope, empty results, stale timestamps, and backend contract drift.

## Outputs

- `artifacts/tools/<tool-id>.input.schema.json` and `.output.schema.json` for every selected or proposed tool.
- `artifacts/tool-adapter-mapping.yaml`: canonical-to-provider/runtime translation, context injection, unsupported features, versions, and validation enforcement.
- `artifacts/tool-contract-cases.jsonl`: inputs, expected status, backend-call permission and expected response shape.
- Shared result envelope using skill stem `generate_tool_schema`.

## Inventory assistant proposed input example

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "get_inventory_status input — proposed",
  "type": "object",
  "additionalProperties": false,
  "required": ["item_id", "location_id", "as_of_date"],
  "properties": {
    "item_id": {"type": "string", "minLength": 1, "maxLength": 64},
    "location_id": {"type": "string", "minLength": 1, "maxLength": 64},
    "as_of_date": {"type": "string", "format": "date", "description": "Inventory snapshot date in the authoritative source's documented timezone."}
  }
}
```

The proposed output includes item/location key, source/as-of metadata, timezone, on-hand units, reserved units, available units, applicable constraints and error status. Define available units as on-hand minus reserved in this example. Keep forecast additional demand separate so committed demand is not double counted. A numerical scenario does not create a purchase order or update stock.

## Completion checks

Every tool has input/output validation and contract cases. Canonical and provider schemas are distinguished. Server-owned identity fields are absent from model arguments. Ambiguous quantity terms and unsupported schema constraints are resolved or explicitly blocked.

## Progression to production

Carry capability/version changes into contract cases and baseline evidence. Before enabling writes, test action authority, retries/replay and reconciliation appropriate to the effect. A schema validation pass alone does not establish authorization or side-effect safety.
