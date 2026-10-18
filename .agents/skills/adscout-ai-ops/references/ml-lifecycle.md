# Operate trained models and their data

Use only when the project trains, evaluates or serves learned models or shared ML features.
A hosted LLM call alone does not require a feature store, training pipeline or model registry.

## Data and features

1. Record dataset source rights, owner, revision/hash, acquisition time, schema and lineage.
   Version transformations, split logic and parameters. Validate structural and statistical
   expectations; quarantine rejected data with counts and reasons.
2. Split by the domain's time/entity boundaries to prevent leakage. Fit preprocessing on
   training data only. Keep a held-out evaluation set and document contamination checks.
3. Reuse feature definitions for training and serving. Test point-in-time joins so future
   information cannot enter historical predictions. Define freshness/TTL and missing-feature
   behavior. Add a feature store only when reuse/serving needs justify the infrastructure.
4. Track code, dependencies, data, seeds, parameters, metrics and artifact digests for every
   experiment. A local manifest can serve this purpose; MLflow/DVC are course examples.

## Train, evaluate, register and serve

Use bounded pipeline stages with restart/idempotency behavior. Triggers may be new data,
a schedule or investigated degradation. A trigger creates a candidate, not an automatic
production promotion. Prevent overlapping retraining jobs and cap resource use.

Compare candidate and champion on the same held-out cohort with per-class and relevant
subgroup results. Freeze thresholds before evaluating. Bind scores to the exact registered
artifact; never compare the latest run's score to an unrelated latest model version.

Load an immutable model version or resolve an alias once and record its concrete identity.
Verify preprocessing, feature, model-signature and runtime compatibility. Distinguish process
liveness from readiness to predict. Exercise invalid inputs, unloaded models, batching,
timeouts, failure metrics and the actually packaged artifact. Test prior-version recovery
and state compatibility before changing the active alias or traffic.

## Monitor and respond

Keep service health (latency, failures, load) separate from model quality. Define reference
and current windows, data revisions, eligible counts, tests/effect sizes and alert thresholds.
Inspect missingness, schema shifts, predictions and features with seasonal/cohort context.
Account for multiple comparisons and small samples.

Input drift is an investigation signal, not proof of concept drift or accuracy loss. Delayed
labels limit what can be concluded; track when ground truth arrives and backfill quality.
Investigate collection/feature bugs before retraining. Promotion still needs candidate
quality gates, and an older model may also fail under a changed distribution.

When outputs affect people, define relevant groups and harm metrics with the project's
requirements. Report group sample sizes and uncertainty and protect sensitive attributes.
Aggregate accuracy can hide subgroup failures. Fairness measures can conflict; name the
chosen measure and tradeoff. SHAP/LIME-style explanations describe model behavior under
assumptions; they do not establish causality, fairness or correctness.

Done when data-to-model lineage, reproducible comparison, serving compatibility and the
triggered monitoring/recovery paths have evidence. Cloud deployment and course stack choices
remain project decisions.
