# Evaluate before tuning and before promotion

Use for prompt/model/tool/routing/retrieval changes or reported model results. Reuse domain
review for independent correctness and Agent Builder release gates for promotion policy.

## Define the experiment

1. Name the decision, baseline and candidate bundles, target population, metric directions,
   units, minimum useful difference, thresholds, required sample size, repetition policy,
   budget and stopping rule before measuring. Keep tuning cases separate from held-out cases.
2. Version case IDs, inputs, expected facts/invariants, allowed and forbidden tools, desired
   abstention, rubric and critical slices. Cover normal, edge, denied, injection, missing/
   stale evidence, timeout, exhausted budget and partial failure when applicable.
3. Separate three layers: deterministic schema/domain/access tests; stochastic task-quality
   evaluation; operational limits (cost, duration, calls and recovery). A plausible answer
   cannot compensate for a forbidden tool call or leaked record.
4. Evaluate trajectories as observable actions: tool names, validated arguments, result
   statuses and final outcome. Flexible correct trajectories may pass; assert an exact
   sequence only when it is itself a requirement. Do not solicit hidden chain-of-thought.
5. For RAG, measure retrieval coverage separately from grounded answer quality. For ML,
   inspect per-class and relevant subgroup errors. For agents, include completion and
   safe-action behavior. A technical success status alone is not task success.
6. When value is a downstream business outcome (qualified leads, meetings, resolved tickets,
   revenue), define it separately from model-level checks: the outcome metric, its
   attribution rule, the delay before outcomes arrive, cohorts by start date, and guard
   metrics that must not worsen. Model-level checks gate shipping a change; a controlled
   comparison on the outcome gates scaling it. Outcomes that arrive later become labeled
   regression and evaluation cases.

## Execute and interpret

- Run the same fixed cases for baseline and candidate with the same constraints. Retain every
  declared repetition. Report missing cases, timeouts, blocked cases and failures explicitly.
- Freeze judge model, rubric, prompt and sampling configuration. Calibrate against a human
  labeled sample and inspect disagreement and injection into judge inputs. Judge scores
  supplement deterministic facts; they do not certify truth or access controls.
- Report per-case regressions and critical slices alongside aggregates, denominators,
  repetition spread and uncertainty. Define zero-denominator and insufficient-sample results
  as unknown, with a reason. Separate intentional safe refusal from failed useful answers.
- Keep ordinary CI credential-free with synthetic fixtures and mocked adapters. Provider
  evals belong to an explicitly budgeted lane; mock success cannot satisfy a live-quality gate.
- A/B testing needs a stable assignment unit, fixed variants, exposure records and analysis
  appropriate to that unit. Repeated requests from one user are not independent users.
  Predeclare the sample/stopping rule and avoid selecting winners by repeated peeking.
  Statistical significance alone does not establish a useful improvement.
- Baseline, corpus or evaluator corrections require a version bump and affected comparisons
  to rerun. A model provider change can trigger rechecks without a repository code change.

## Decision

Any failed hard requirement rejects the candidate. Missing/stale required evidence or an
insufficient sample holds promotion. A current pass on all applicable requirements makes
the candidate eligible within the tested scope; execution still follows existing authority.

Use [EVAL_PLAN.md](../assets/EVAL_PLAN.md). Carry real failures into regression fixtures after
sanitization; retain independent held-out coverage so tuning does not become test memorization.
