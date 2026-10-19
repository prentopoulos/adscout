## ADDED Requirements

### Requirement: Deterministic profile rules
The `rules` step SHALL be plain code over validated fields: a lead passes only if it sells in
every region of the segment (US and CA), has at least one allowed category, has at least the
segment's minimum employees (50) and matches no exclusion. A failing lead SHALL exit as
`out_of_profile` with the failed rule named.

#### Scenario: Sells in the US only
- **WHEN** a lead's `sells_in` is `["US"]`
- **THEN** it exits as `out_of_profile` naming the region rule

#### Scenario: Rules case set
- **WHEN** the gate runs `evals/cases/rules.jsonl`
- **THEN** every case's expected outcome matches

### Requirement: Rubric score combined by code
The `score` step SHALL ask the model for a 1–5 rating of each criterion (audience, ad
activity, budget capacity, recent launches) against written anchors, each with reasons that
cite enriched field IDs, as structured output. Code SHALL combine the ratings into 0–100 as
the weighted mean of (rating − 1) × 25 with the segment config's weights, and SHALL refuse
reasons that cite field IDs the lead does not have.

#### Scenario: Combination is code
- **WHEN** the fake model rates a lead 5, 3, 3, 1 with weights 0.35, 0.30, 0.20, 0.15
- **THEN** the stored score is 0.35×100 + 0.30×50 + 0.20×50 + 0.15×0 = 60.0

#### Scenario: Reason cites a missing field
- **WHEN** a rating's reason cites a field the lead has no value for
- **THEN** the output is treated as invalid and retried

### Requirement: Threshold and router
A lead scoring at or above the segment's threshold (60) SHALL go to research; 55–59 SHALL
exit as `near_miss` for a person, with no research spend; below 55 SHALL exit as
`below_threshold`; output still invalid after retry and fallback SHALL exit as
`score_failed`. A lead is qualified only if it passed the rules and reached the threshold.

#### Scenario: Near miss
- **WHEN** a lead scores 57.5
- **THEN** it exits as `near_miss`, no research call is made, and it is not counted as
  qualified

### Requirement: Repeat scoring and tier evaluation
`adscout run --score-repeats N` SHALL score each lead N times and record every sample, with
the first sample deciding the route. `python -m evals score-compare` SHALL score stored
enrichments on two models N times each under its own cap and report the predeclared tier
rule's outcome; `adscout rescore --segment <id>` SHALL rescore stored enrichments as a run of
kind `rescore`.

#### Scenario: Rescore needs no enrichment calls
- **WHEN** `adscout rescore` runs on a segment with stored enrichments
- **THEN** it makes scoring calls only and records a `rescore` run
