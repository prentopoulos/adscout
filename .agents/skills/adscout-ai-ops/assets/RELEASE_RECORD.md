# Release evidence

Use alongside existing OpenSpec and PROJECT records. This form does not authorize deployment.

## Bundle

- Candidate ID / environment / lifecycle / scope: TBD
- Code revision and dirty-state digest if applicable: TBD
- Runtime, dependency lock and packaged artifact digests: TBD
- Model/provider concrete version and generation settings: TBD
- Prompt, tools/schema, policy and non-secret configuration revisions: TBD
- Data, feature, corpus, embedding, index and cache versions where enabled: TBD
- Evaluator / case dataset revision: TBD
- Mutable or unavailable versions and their reproducibility limits: TBD

## Gates

| Required gate | Predicate / sample / window | Evidence tied to bundle | Outcome | Owner / recheck trigger |
|---|---|---|---|---|
| TBD | TBD | Missing | not_run | TBD |

Outcomes: pass, fail, not_run, stale. An absent capability can be not_applicable with evidence.
Any hard-control failure rejects; absent/stale required evidence holds.

## Recovery and decision

- Previous compatible bundle and protected artifact location: TBD
- Rollback/forward-recovery command and state/index/cache compatibility: TBD
- Recovery drill evidence and post-recovery checks: TBD
- Rollout population, monitoring window and stop conditions if applicable: TBD
- Applicable PROJECT authorization references: TBD
- Technical decision: hold (unmeasured template)
- Actual deployment: not_run
