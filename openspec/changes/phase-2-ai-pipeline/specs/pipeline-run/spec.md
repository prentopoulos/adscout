## MODIFIED Requirements

### Requirement: Labelled scripted stubs
A run started with a stub script SHALL use stubs for the `enrich`, `rules`, `score`,
`research` and `draft` steps, whose outcome per lead comes from that committed stub script
keyed by domain; every other run SHALL use the real steps. Every row a stub writes SHALL be
labelled `stub`, and no stub output SHALL state a fact about a real company; an exit reason
SHALL read as a scripted stub reason that names the stub script. For each real seed, the stub
script SHALL record the expected outcome, its rationale and at least one source URL with its
retrieval date. Synthetic test fixtures SHALL exercise every exit reason.

#### Scenario: Stub rows labelled
- **WHEN** a stub-script run on the real seeds finishes
- **THEN** every enrichment, score, brief and draft row it wrote is labelled `stub`, and
  every brief has no claims

#### Scenario: Stub script without a source
- **WHEN** a real seed's entry in the stub script has no source URL or retrieval date
- **THEN** loading the stub script fails and names the seed

#### Scenario: Every exit path covered
- **WHEN** the synthetic fixture run and its approval and sync runs finish
- **THEN** each exit reason and each flag in the vocabulary appears at least once

#### Scenario: Real steps by default
- **WHEN** a run starts without a stub script
- **THEN** its enrich, rules, score, research and draft step rows are labelled `real`

### Requirement: Step outcomes and exit reasons
For every lead entering a step, the run SHALL record one outcome, `kept` or `exited`, and an
exit SHALL carry one reason code from `duplicate`, `excluded`, `out_of_profile`,
`missing_key_fields`, `score_failed`, `near_miss`, `below_threshold`, `research_failed`,
`draft_failed` and `rejected`. A kept outcome SHALL carry either no flag or one of
`research_partial`, `critic_unresolved` and `crm_conflict`. Exits `score_failed`, `near_miss`,
`research_failed` and `draft_failed` SHALL be listed for a person.

#### Scenario: Unknown reason refused
- **WHEN** a step records an exit with reason `bad_vibes`
- **THEN** the database refuses the row

#### Scenario: Near miss recorded
- **WHEN** a lead scores 57
- **THEN** it exits at `score` with reason `near_miss`

### Requirement: Run records
Every run SHALL write a `runs` row before its first step with its run ID (the evaluation
harness format), kind (`pipeline`, `approval`, `crm_sync`, `rescore` or `eval`), start time,
status `running` and its system version: code revision and dirty flag, `uv.lock` digest,
package, agent and prompt versions, Python version, platform, schema version, segment ID,
`icp_config_hash`, `seed_list_hash` and source (`stub`, `fixture`, `replay` or `live`). Each
step SHALL write a `step_runs` row with its implementation (`stub` or `real`), timing, status
and its entering, kept and exited counts, and its model, token and cost totals summed from
its `model_calls` rows. Model, token and cost fields SHALL be null with a reason while the
step makes no model call. Timestamps SHALL be UTC RFC 3339 with milliseconds.

#### Scenario: Stub step has explained nulls
- **WHEN** a stub step finishes
- **THEN** its model, input tokens, output tokens and cost are null and its null reasons
  name each one

#### Scenario: Real step totals match its calls
- **WHEN** a fake-adapter scoring step finishes
- **THEN** its token and cost totals equal the sums of its `model_calls` rows

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

### Requirement: Offline pipeline
Without `--live`, the pipeline SHALL make no network call, no live model call and no
external write; model calls SHALL be served by the fake adapter or the replay cache and page
reads by recorded fixtures.

#### Scenario: Full demo offline
- **WHEN** the demo script runs the whole flow under the test suite's socket block
- **THEN** it finishes with no socket error

#### Scenario: Fake run covers every step
- **WHEN** a fake-adapter run on synthetic fixture companies finishes
- **THEN** each real step ran, and leads reached `pending_approval`, `near_miss`,
  `research_failed` and `draft_failed`
