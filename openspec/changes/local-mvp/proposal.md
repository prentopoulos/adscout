## Why

The owner requested a finished MVP of the remaining project in the current usage window
on 2026-10-19, explicitly authorizing condensation and simplification. Finish the local
workflow using the AI pipeline already built, without making live access a prerequisite.

## What Changes

- One local app for reviewing cited briefs and drafts, recording human approval or rejection,
  syncing to the existing SQLite CRM sandbox, and inspecting a local sandbox outbox.
- A funnel and simulated-revenue dashboard, plus a reproducible one-command offline demo.
- Finish the in-progress generated diagrams, add a README, verify the workflow and review code.
- Defer hosted CRM, email and tracing integrations, Docker, CI hosting, video, the 30-company
  study and paid comparisons. Preserve original Phase 2 tasks and gates as deferred, not passed.

## Capabilities

### New Capabilities
- `local-workspace`: local review, CRM, sandbox delivery and simulated-revenue workflow.

### Modified Capabilities
None. The original AI phase remains open for live validation; this is a smaller local milestone.

## Impact

Standard-library HTTP UI bound to 127.0.0.1; SQLite migration 0003; existing CRM writer,
model adapters and tracing reused. No new runtime dependency, account or paid call.
