## ADDED Requirements

### Requirement: Trace fields on every call
Each `model_calls` row SHALL carry a trace ID (the lead's UUIDv7 as hex), a span ID, a parent
span ID, an operation name (`chat`, `invoke_agent` or `execute_tool`) and the registry role
as the agent name, so each lead's calls form one tree. The export SHALL map them to
OpenTelemetry GenAI and Langfuse names through one mapping table.

#### Scenario: Worker calls nest under the research step
- **WHEN** a fake research step finishes for one lead
- **THEN** every worker call's parent chain reaches that lead's research span

### Requirement: End-of-run cost table
Every pipeline, rescore and evaluation run SHALL end by printing and storing a table of calls,
tokens, searches, cost and time by step, role and model, plus cost per lead and cost per
qualified lead (actual spend only; null with a reason when no lead qualified).

#### Scenario: No qualified leads
- **WHEN** a run qualifies no lead
- **THEN** cost per qualified lead is null with the reason "no qualified leads"

### Requirement: Trace command
`adscout trace <run_id> [--lead <domain>]` SHALL print each lead's span tree from the database
alone, showing role, model, tokens, cost, time and tool calls.

#### Scenario: Trace from the database alone
- **WHEN** `adscout trace` runs on a finished run with the cache deleted
- **THEN** it prints the full tree
