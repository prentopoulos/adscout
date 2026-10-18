## ADDED Requirements

### Requirement: Steps in a fixed order
A pipeline run SHALL take a segment's seeds through the steps `source`, `enrich`, `rules`,
`score`, `research` and `draft`, in that order, and end with every surviving lead's draft
waiting for approval. Approval (`approve`) and CRM sync (`crm_sync`) SHALL be separate runs
over the stored drafts. Each step SHALL be a typed function with validated input and output
models, so a later phase replaces a stub without changing its callers.

#### Scenario: Run ends at approval
- **WHEN** `adscout run --segment gaming-hardware-na` finishes
- **THEN** the run's status is succeeded, and every lead that reached the draft step has a
  draft with status `pending_approval` and no approval

### Requirement: Real source and dedupe step
The `source` step SHALL be real code: it loads the seed list, normalizes domains, and exits a
seed as `duplicate` when its domain repeats in the seed list, already has a lead in the
segment or exists in the CRM, and as `excluded` when the segment config excludes its domain.

#### Scenario: Duplicate in the seed list
- **WHEN** a synthetic seed list holds the same domain twice
- **THEN** one lead is created and the second row exits as `duplicate`

#### Scenario: Excluded domain
- **WHEN** a seed's domain is in the segment's exclusions
- **THEN** it exits at `source` as `excluded` and no later step sees it

### Requirement: Labelled scripted stubs
The `enrich`, `rules`, `score`, `research` and `draft` steps SHALL be stubs whose outcome per
lead comes from a committed stub script keyed by domain. Every row a stub writes SHALL be
labelled `stub`, and no stub output SHALL state a fact about a real company; an exit reason
SHALL read as a scripted stub reason. The Phase 1 stub script for the real seeds SHALL make at
least one lead exit before research, one exit as `below_threshold`, one be rejected at approval
and one be synced to the CRM. Synthetic test fixtures SHALL exercise every exit reason.

#### Scenario: Stub rows labelled
- **WHEN** a run on the real seeds finishes
- **THEN** every enrichment, score, brief and draft row it wrote is labelled `stub`, and
  every brief has no claims

#### Scenario: Every exit path covered
- **WHEN** the synthetic fixture run and its approval and sync runs finish
- **THEN** each exit reason and each flag in the vocabulary appears at least once

### Requirement: Step outcomes and exit reasons
For every lead entering a step, the run SHALL record one outcome, `kept` or `exited`, and an
exit SHALL carry one reason code from `duplicate`, `excluded`, `out_of_profile`,
`missing_key_fields`, `below_threshold`, `draft_failed` and `rejected`. A kept outcome SHALL
carry either no flag or one of `research_partial` and `crm_conflict`.

#### Scenario: Unknown reason refused
- **WHEN** a step records an exit with reason `bad_vibes`
- **THEN** the database refuses the row

### Requirement: Run records
Every run SHALL write a `runs` row before its first step with its run ID (the evaluation
harness format), kind (`pipeline`, `approval` or `crm_sync`), start time, status `running`
and its system version: code revision and dirty flag, `uv.lock` digest, package, agent and
prompt versions, Python version, platform, schema version, segment ID, `icp_config_hash`,
`seed_list_hash` and source (`stub`, `fixture` or `live`). Each step SHALL write a
`step_runs` row with its implementation (`stub` or `real`), timing, status and its entering,
kept and exited counts. Model, token and cost fields SHALL be null with a reason while the
step makes no model call. Timestamps SHALL be UTC RFC 3339 with milliseconds.

#### Scenario: Stub step has explained nulls
- **WHEN** a stub step finishes
- **THEN** its model, input tokens, output tokens and cost are null and its null reasons
  name each one

#### Scenario: Failed run kept
- **WHEN** the stub script makes the score step raise an error
- **THEN** the run's status is `failed` with an error category, and every row written before
  the error is still in the database

#### Scenario: Interrupted run
- **WHEN** a run starts while an older run is still marked `running` and its process is gone
- **THEN** the older run is marked `interrupted`, keeps its rows, and the new run proceeds

#### Scenario: Concurrent run refused
- **WHEN** a second run starts while another run's process is alive
- **THEN** the second run exits non-zero without writing any lead or step row

### Requirement: Stub approver bound to the draft
`adscout approve --stub` SHALL record one decision, approved or rejected, for each pending
draft, following the stub script. Each approval SHALL store the draft's SHA-256, the
approver kind `stub` and a reason for any rejection. A later edit to a draft SHALL invalidate
its approval. No command SHALL accept an approval that is not bound to the current draft
hash.

#### Scenario: Stub approval labelled
- **WHEN** the stub approver approves a draft
- **THEN** the approval row has approver kind `stub` and the draft's current SHA-256

#### Scenario: Changed draft
- **WHEN** a draft's text changes after it was approved
- **THEN** CRM sync treats the lead as not approved

### Requirement: One CRM writer
`adscout sync` SHALL write approved leads only through a single CRM writer module, which in
Phase 1 targets a local fake CRM labelled as such. The writer SHALL deduplicate by company
domain, write only AdScout-owned fields, never overwrite a field marked as edited by a
person (recording the lead as kept with flag `crm_conflict`), and log every write with an
operation ID, operation, fields written and status. No other module SHALL write to the CRM
tables.

#### Scenario: Person-edited field kept
- **WHEN** a fake CRM account has a field marked as edited by a person and sync would change
  it
- **THEN** the field is unchanged, the write log records the conflict, and the lead is kept
  with flag `crm_conflict`

#### Scenario: Second sync is idempotent
- **WHEN** sync runs twice over the same approved leads
- **THEN** the second run creates no new CRM accounts and logs its writes as no-ops

#### Scenario: Only approved leads synced
- **WHEN** sync runs while one draft is rejected and one is pending
- **THEN** neither lead is written to the fake CRM

### Requirement: Independent run check
`adscout check <run_id>` SHALL validate a run from the database with code separate from the
runner, using SQL only, and record the result on the run as its validation outcome and detail.
It SHALL check that, for every step, kept plus exited equals entering; that entering counts
never increase from one step to the next; that every stub-written row is labelled; that every
lead has all its immutable fields; and that every CRM write belongs to a lead with a valid
approval.

#### Scenario: Conservation broken
- **WHEN** a step's counts are altered so kept plus exited differs from entering
- **THEN** the check records `fail` and names the step

#### Scenario: Clean run passes
- **WHEN** the check runs on a finished stub run
- **THEN** it records `pass`

### Requirement: Run summaries and export
`adscout runs` SHALL list runs with their kind, status and validation outcome; `adscout
funnel <run_id>` SHALL print the entering, kept and exited counts per step with exit reasons;
and `adscout export <run_id>` SHALL write the run, its steps and its lead outcomes as JSON
Lines using OpenTelemetry GenAI attribute names where one exists, validated against a
committed JSON Schema. Exports cited as phase evidence SHALL be committed under
`evidence/runs/`, taken from a clean tree.

#### Scenario: Export validates
- **WHEN** a finished run is exported
- **THEN** every line validates against the committed export schema, and the model fields use
  names such as `gen_ai.request.model` and `gen_ai.usage.input_tokens`

#### Scenario: Dirty tree evidence refused
- **WHEN** `adscout export` is asked to write into `evidence/runs/` for a run whose code was
  dirty
- **THEN** it refuses and says why

### Requirement: Offline pipeline
The Phase 1 pipeline SHALL make no network call, model call or external write.

#### Scenario: Full demo offline
- **WHEN** the demo script runs the whole Phase 1 flow under the test suite's socket block
- **THEN** it finishes with no socket error
