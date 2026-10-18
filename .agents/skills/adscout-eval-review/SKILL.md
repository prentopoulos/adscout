---
name: adscout-eval-review
description: Design or review AdScout fit scores, evaluation results, cost per qualified lead and funnel or revenue figures with reproducible evidence and fair baselines. Use when any of them or a reported result changes.
---

# AdScout eval review

Read [PROJECT.md](../../../PROJECT.md) and the affected OpenSpec requirements. Follow
[adscout-build-safety](../adscout-build-safety/SKILL.md) when adapters,
recording or paid-call behavior also change.

## Define the question before running

Comparisons: AdScout fit scores against the owner's good/maybe/poor labels (does the
score rank good fits first); two models or prompts on the same fixed cases (field
accuracy, precision in the top 20, claim faithfulness, cost per qualified lead); a
pipeline change against the last known-good run on the same seed list. Business-level
comparisons (reply or meeting rate against a control) need real sends and are out of
scope; anything shown about them is simulated and labelled so.

Separate what is being compared from how it is computed. Use the same inputs, constraints,
metric, units and budget accounting for every candidate. Define the baseline, the
meaningful-difference criterion and the trial plan before measuring; select seeds, samples
and cases by the plan, never by how favorable a result looks.

Label each case as normal, edge or deliberately failing. Label synthetic inputs as synthetic.

## Validate independently

Check schema, finite values, dimensions, ranges and units before computing. Evaluate outputs
with deterministic domain code independent of the code that produced them.

- Fit scores lie in the declared range and each carries its reasons.
- Per step, kept plus dropped (with a reason) equals the step's input count; funnel
  counts never increase from one stage to the next.
- Precision in the top N states N and its denominator; ties at the cut are reported.
- Cost per qualified lead = (data + model + tool spend) ÷ qualified leads; zero
  qualified leads makes it undefined, not zero; unknown usage is null.
- Every brief claim has a source URL; every draft fact is present in its brief or the
  media-kit facts.
- Revenue rows and every figure derived from them are flagged simulated.

Establish correctness on tiny fixtures with known answers, plus normal, edge and impossible
cases. A timeout or empty result means nothing was found, not that nothing exists; a run
without exceptions is not a correct run. Distinguish best-known from proven, and measured
from estimated.

## Fix evaluation before tuning

Freeze the evaluator version, held-out cases, budgets and repetition policy before tuning.
Version corrections and rerun affected comparisons. Deterministic correctness is a hard gate;
stochastic quality is a separately interpreted report. Keep every predeclared repetition,
including the ones a preferred candidate loses. Paid calls stay out of ordinary CI.

For ML/LLM/agent outputs, identify the complete system bundle (prompt, model, tools,
configuration, data/index and environment), evaluate critical slices and per-case regressions,
and report uncertainty and missing-case counts. Calibrate judge rubrics against independent
labels. Apply the AI-ops evaluation procedure when that skill is installed.

## Record and compare honestly

Every result names its inputs (ID, hash or seed), code/dependency/model versions,
configuration, budgets and hardware, plus status, independent validation outcome, metrics,
timings and repetition index. Missing fields stay unknown with a reason; an unrun live
result is null, not zero.
Also record: segment, seed-list and ideal-customer config hashes, labelled-set version,
prompt and agent versions, model ID, per-step tokens and cost, fixture versus live source,
and the attribution rule used for any revenue figure.

Record failed runs. Statistics that exclude failures state their count and denominator.
A small demo establishes behavior on its tested cases, not scaling, savings or superiority.

For live work, follow PROJECT's `⛔` gates; capture actual provider/account properties, raw
timing and observed billing. An ambiguously successful billable call is investigated before
any retry.

## Interpret and deliver

Distinguish source fact, user decision, assumption, proposed experiment and measured result.
Explain which inputs and terms account for a difference, from the evidence alone. State the
exact tested cases and remaining unknowns. Completion is a traceable, independently checked
finding with limits, even when it is a tie or the baseline wins.
