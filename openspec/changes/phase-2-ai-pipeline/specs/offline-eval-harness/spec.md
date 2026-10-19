## ADDED Requirements

### Requirement: Phase 2 case sets
The harness SHALL hold deterministic case sets for rules (`evals/cases/rules.jsonl`, about 30
cases), drafts (`evals/cases/drafts.jsonl`, about 30 cases), the claim verifier and the ten
injection pages with their twins, each with normal, edge and deliberately failing cases, and
the gate SHALL pass only when every case's expected outcome matches.

#### Scenario: A rule regresses
- **WHEN** a change makes the region rule accept `["US"]`
- **THEN** the rules case set fails in the gate

### Requirement: Owner labels with a hash
Owner labels SHALL live in `evals/labels/<segment_id>.v<N>.csv` with one label (good, maybe
or poor) per seed domain, committed with their SHA-256 before any live scoring they are
compared against. A relabel SHALL create a new version, never edit a committed one.

#### Scenario: Label file edited
- **WHEN** a committed label file's content no longer matches its recorded hash
- **THEN** the score comparison refuses to run and names the file

### Requirement: Comparison plans committed before measuring
Each judged comparison (score check, tier evaluation, worker tier, research design) SHALL
have a plan in `evals/plans/` naming its population, repeats, metrics, decision rule and cap,
committed before its first live call, and its report SHALL cite the plan's commit and include
every repeat.

#### Scenario: Plan committed after the run
- **WHEN** a comparison report cites a plan commit newer than its first live call
- **THEN** the report is marked as not following a predeclared plan
