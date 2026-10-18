## MODIFIED Requirements

### Requirement: Result records
The runner SHALL write one JSON Lines record per case and repetition that validates against a
committed JSON Schema. Each record SHALL carry the run ID, case ID, repetition index, input
hash, code revision and dirty flag, `uv.lock` digest, case-set and evaluator versions,
configuration, budgets, platform and Python version, the agent version as defined for leads,
status (pass, fail, not_run or error), the independent validation outcome, metrics, start
time and duration, and the source (fixture or live). Fields with no value SHALL be null with a
reason in the record, never zero, and each reason SHALL be true for the run that wrote it.

#### Scenario: Scaffold record has explained nulls
- **WHEN** the scaffold runs, which has no model step and no segment
- **THEN** the model ID, prompt version, tokens, cost, segment and config hashes are null,
  each with a reason that does not refer to a future phase, the agent version is filled, and
  the source is "fixture"

#### Scenario: Schema files match the code
- **WHEN** the case or result model changes without regenerating its JSON Schema file
- **THEN** the gate fails

#### Scenario: Records validated independently
- **WHEN** the scaffold run finishes
- **THEN** each record is validated against the committed JSON Schema by a validator separate
  from the code that wrote it
