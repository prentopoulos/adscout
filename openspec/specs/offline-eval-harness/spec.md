# offline-eval-harness Specification

## Purpose
Fixed evaluation cases and honest, independently validated result records, so later model
evaluations bind to a complete system version and failed runs are kept.
## Requirements
### Requirement: Versioned case format
Evaluation cases SHALL be stored in version-controlled files that validate against a
committed JSON Schema (Draft 2020-12). Each case SHALL carry a case ID, case set and version,
pipeline step, layer (deterministic, judged or operational), label (normal, edge or
deliberately failing), a synthetic flag, a split (tuning or held out), inputs and expected
invariants.

#### Scenario: Invalid case rejected
- **WHEN** a case file omits the label or the synthetic flag
- **THEN** loading the case set fails and names the case

### Requirement: Result records
The runner SHALL write one JSON Lines record per case and repetition that validates against a
committed JSON Schema. Each record SHALL carry the run ID, case ID, repetition index, input
hash, code revision and dirty flag, `uv.lock` digest, case-set and evaluator versions,
configuration, budgets, platform and Python version, the agent version as defined for leads,
status (pass, fail, not_run or error), the independent validation outcome, metrics, start
time and duration, and the source (fixture or live). Fields with no value SHALL be null with a
reason in the record, never zero, and each reason SHALL be true for the run that wrote it.

#### Scenario: Phase 0 record has explained nulls
- **WHEN** the scaffold runs before any model step exists
- **THEN** the model ID, prompt version, tokens and cost are null, each with a reason, and the
  source is "fixture"

#### Scenario: Scaffold record carries the agent version and present-tense reasons
- **WHEN** the scaffold runs, which has no model step and no segment
- **THEN** the agent version is filled, and the segment and config hashes are null, each with
  a reason that does not refer to a future phase

#### Scenario: Schema files match the code
- **WHEN** the case or result model changes without regenerating its JSON Schema file
- **THEN** the gate fails

#### Scenario: Records validated independently
- **WHEN** the scaffold run finishes
- **THEN** each record is validated against the committed JSON Schema by a validator separate
  from the code that wrote it

### Requirement: Run records are preserved
Run records SHALL be written to gitignored `evals/runs/`, one file per run, and never deleted
or overwritten by the harness or the gate, including failed runs.

#### Scenario: Failed run kept
- **WHEN** a run has a failing case
- **THEN** its record file stays in `evals/runs/` after later runs

### Requirement: Scaffold self-test
The harness SHALL include a synthetic scaffold case set with at least one normal case, one
edge case and one deliberately failing case, labelled synthetic and not described as model
evaluation. The gate SHALL pass only when the normal and edge cases pass and the
deliberately failing case fails.

#### Scenario: Deliberately failing case passes
- **WHEN** the evaluator wrongly passes the deliberately failing case
- **THEN** the evaluation scaffold step fails

