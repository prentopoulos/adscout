# Evaluation plan

Copy into the target project's existing evaluation/design location only when needed.
Replace TBD entries before executing the dependent evaluation. This form is not evidence.

## Decision and frozen inputs

- Question / requirement IDs: TBD
- Baseline system bundle / candidate bundle: TBD
- Dataset revision, case IDs, split and contamination checks: TBD
- Evaluator and judge revisions, rubric and human calibration: TBD
- Repetitions / seeds where supported / stopping rule / minimum sample: TBD
- Execution lane: offline deterministic, authorized provider evaluation, or deployment test
- Command, environment and aggregate evaluation budget: TBD
- Freeze date/revision; changes requiring re-evaluation: TBD

## Cases and criteria

| Case or slice | Expected outcome / prohibited actions | Metric, unit, direction and threshold | Required sample | Enforcement/test location |
|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD |

Include normal, edge and triggered failure/access cases. Report retrieval, generation and
task/action quality separately where relevant. Define failed, missing, refused and pending
case accounting. Predeclare the meaningful improvement and maximum acceptable regression.

## Results (complete after running)

| Case / repetition | Baseline | Candidate | Hard-control outcome | Duration / usage / cost | Evidence / failure reason |
|---|---|---|---|---|---|
| TBD | not_run | not_run | not_run | unknown | TBD |

Report denominators, coverage, critical-slice regressions and uncertainty. Unknown values
stay unknown with reasons. Retain all runs. Decision: hold until required evidence exists;
reject on a hard failure; eligible only for the current tested scope when all requirements pass.
