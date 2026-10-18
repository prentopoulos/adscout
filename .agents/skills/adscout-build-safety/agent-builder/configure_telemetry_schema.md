# Configure telemetry schema

## Purpose and inputs

Act as the AI observability designer. Define correlated, privacy-aware tracking for requests, model calls, tools, retrieval, decisions, cost, and operational health.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: `spec`, architecture, tool contracts, data-handling policy, FinOps definitions, and platform observability standards. Propose a portable schema; validate SDK/provider-specific attribute names when implementing exporters.

For a local utility, structured local events and a small metrics summary may suffice; managed exporters, dashboards and on-call routing apply only when needed.

## Procedure

1. Define a trace hierarchy: request → agent run → model/tool/retrieval spans, with async work linked to its initiating request. Propagate correlation IDs without putting credentials or user-supplied labels into trusted metadata.
2. Define required event fields and types: `schema_version` (string), `event_name` (enum), `timestamp` (UTC date-time), `trace_id`/`span_id`/`request_id` (opaque strings), `use_case_id`, `environment`, `agent_version`, `status`, and `duration_ms` (nonnegative number). Define conditional model/tool/retrieval/error/budget fields.
3. For model events, capture provider/model and prompt versions, input/output/cached token counts where reported, and usage availability. For tools, capture tool/version, duration, outcome, safe error code, and authorization result. For retrieval, capture corpus/index versions, result count and freshness without raw passages. Represent unavailable usage as null plus a reason, not zero.
4. Use low-cardinality dimensions for metrics. Keep request/session/item/location identifiers in access-controlled traces only when justified; never use them as metric labels. Define sampling for routine traces and separate reliable audit delivery for security/action events.
5. Specify latency percentiles, technical success/error rate, tool/model failure rate, stale-source rate, abstention rate, budget exhaustion, estimated cost and evaluated task success. Technical HTTP success is not business-task success. Define each numerator, denominator, window, unit and exclusions.
6. Define dashboards, alert routing, redaction, access, retention and exporter-failure behavior. A telemetry outage must not leak raw fallback logs. Bound buffers and test loss/duplication handling. Missing required release evidence produces `not_run` or an evidence gap.

## Outputs

- `artifacts/telemetry.schema.json`: versioned canonical JSON Schema with required fields, enums and conditional event structures.
- `artifacts/observability-plan.md`: trace model, metric definitions, dashboard/alert design, data lifecycle, exporter mapping and validation cases.
- Shared result envelope using skill stem `configure_telemetry_schema`.

## Inventory assistant synthetic event

```json
{
  "schema_version": "0.2",
  "event_name": "tool.completed",
  "timestamp": "2026-09-09T12:00:00Z",
  "trace_id": "synthetic-trace-001",
  "span_id": "synthetic-span-002",
  "request_id": "synthetic-request-001",
  "use_case_id": "inventory-planning-assistant",
  "environment": "test",
  "agent_version": "0.1.0",
  "tool_id": "get_inventory_status",
  "tool_version": "0.1.0-example",
  "status": "success",
  "duration_ms": 125,
  "authorization_result": "allowed"
}
```

These are canonical application IDs, not a claim that the strings satisfy a particular tracing backend's native ID format. The exporter must map/validate that format.

## Completion checks

Example events validate against the generated schema. Unknown usage, timeouts, denied calls, cancellations and partial failures have representations. Metrics avoid sensitive/high-cardinality labels. Trace correlation and data filtering cover all tool/model paths.

## Progression to production

A local prototype may use filtered local events. Before production reliance, demonstrate actionable failure/security/cost signals, an accountable operator and tested incident/disable behavior using the chosen deployment; managed monitoring is optional, those outcomes are required.
