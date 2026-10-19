## ADDED Requirements

### Requirement: One model adapter with three modes
Every model call SHALL go through one in-house adapter over the `anthropic` SDK with the modes
`fake` (scripted responses, used by tests), `replay` (responses from the record-and-replay
cache) and `live` (the Anthropic API). Only the adapter SHALL read `ANTHROPIC_API_KEY`, from
the environment or gitignored `.env`. Live mode SHALL refuse to start without a key, a
per-run spend cap and an explicit `--live` flag.

#### Scenario: Offline by default
- **WHEN** `adscout run --segment gaming-hardware-na` runs without `--live`
- **THEN** no request leaves the process and every model call is served by the fake or the
  replay cache

#### Scenario: Live without a cap
- **WHEN** `adscout run --live` is given no `--max-spend-usd`
- **THEN** it exits non-zero before any call and names the missing cap

#### Scenario: Key never leaks
- **WHEN** a live call fails with an authentication error
- **THEN** the error recorded and printed does not contain the key

### Requirement: Every call recorded and costed
Each call SHALL write a `model_calls` row with run, step, lead, agent role, model, effort,
prompt version, call role (`primary`, `retry`, `fallback` or `escalation`), input,
cache-write, cache-read and output tokens from the API's usage fields, web search count and
fee, cost in USD, latency, stop reason and trace fields. Cost SHALL be computed from a
committed, dated price table (`config/prices/anthropic.yaml`) at the call's date, including
the long-prompt price above 100K tokens and $10 per 1,000 searches.

#### Scenario: Cost from the price table
- **WHEN** a fake Haiku call reports 2,000 input, 1,000 cache-read and 500 output tokens and
  one search
- **THEN** its recorded cost equals the price-table arithmetic for those counts plus $0.01

#### Scenario: Missing price
- **WHEN** a call uses a model with no row in the price table for its date
- **THEN** the call is refused before it is sent

### Requirement: Spend reserved before each call
Before each call the adapter SHALL reserve its worst-case cost (`max_tokens` output,
uncached input, `max_uses` searches) against the run's cap under a lock, refuse the call if
the reservation would exceed the cap, and settle the reservation to the actual cost after
the response. A refused reservation, the workspace-limit 400, the spend-cap 429 and "credit
balance is too low" SHALL end the run as `failed` with error category `budget_exhausted` and
SHALL NOT be retried.

#### Scenario: Cap hit mid-run
- **WHEN** a fake run's cap is reached while the third lead is being scored
- **THEN** no further call is made, the run is `failed` with `budget_exhausted`, and every
  row written before the stop is kept

#### Scenario: Parallel workers share the cap
- **WHEN** three workers reserve at the same time and only two reservations fit
- **THEN** exactly two calls proceed and the third is refused

### Requirement: Fallback in our own code
A refusal, output still invalid after one retry, or a 5xx or overload error after the SDK's
retries SHALL call the role's other tier once, recorded with call role `fallback`. No
server-side fallback SHALL be configured.

#### Scenario: Invalid output falls back
- **WHEN** the fake primary model returns schema-invalid output twice
- **THEN** one fallback call is made on the other tier and all three calls are recorded

### Requirement: Record-and-replay cache
Live model responses and fetched pages SHALL be stored in the gitignored `data/cache.db`,
keyed by a SHA-256 over the model, prompt version, tools and canonical input. A replay run
SHALL have `runs.source = 'replay'`, record each call's cost as 0 and keep its original cost.

#### Scenario: Replay reproduces a run at no cost
- **WHEN** a recorded live run is replayed
- **THEN** every output equals the original, every call's cost is 0 with the original cost
  kept, and no network call is made

### Requirement: Versioned prompt files
Each role's prompt SHALL live in `src/adscout/prompts/<role>.md` beside its output schema, and
its prompt version SHALL be `p-` followed by the first 12 hex characters of a SHA-256 over the
LF-normalized prompt and schema files. Prompts SHALL ask for short reasons, not step-by-step
reasoning, and SHALL hold no secret.

#### Scenario: Prompt edit changes the version
- **WHEN** one character of `score.md` changes
- **THEN** the scoring prompt version changes and new leads carry the new version

### Requirement: Stable cached prefix
Requests SHALL put the fixed instructions and schema before a prompt-cache breakpoint and
serialize per-lead content deterministically, and a Haiku request SHALL stay under 100K
prompt tokens.

#### Scenario: Prefix bytes stable
- **WHEN** two different leads are scored
- **THEN** the bytes before the cache breakpoint are identical
