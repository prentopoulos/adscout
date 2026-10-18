# Operations runbook

Adapt at the first operational milestone. Store real secrets and sensitive incident payloads
outside this document. Keep commands specific to the tested environment.

## Ownership and normal operation

- Operator / service and dependency owners: TBD
- Supported users, data and actions / system version lookup: TBD
- Start / stop / readiness commands and expected results: TBD
- Run-record/report location, protected access and retention: TBD
- Model/tool/token/time/retry/concurrency/cost limits and enforcement: TBD
- Maintenance, provider-change and evidence recheck triggers: TBD

## Signals and response

| Signal | Definition / denominator / window / minimum count | Threshold | Owner / response | Verify recovery with |
|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD |

Separate task quality from service health. Unknown usage and missing observations are visible
gaps. Include only applicable outages, cost, quality, security and data-freshness signals.

## Recovery

- Disable affected action/provider/ingestion path: TBD
- Preserve filtered run IDs, bundle IDs and failure evidence: TBD
- Reconcile pending or ambiguously completed writes before retries: TBD
- Restore prior compatible code/prompt/model/index/state or recover forward: TBD
- Credential revocation/rotation if implicated: TBD
- Backup restore and deletion verification when durable data exists: TBD
- Health, representative-task and isolation checks before resuming: TBD

## Drill / incident record

- Date, environment, injected or actual failure: TBD
- Commands, observations, affected scope and timing: TBD
- Recovery verification and remaining gaps: TBD
- Sanitized regression case / follow-up task: TBD

Installing this form is not a completed recovery drill.
