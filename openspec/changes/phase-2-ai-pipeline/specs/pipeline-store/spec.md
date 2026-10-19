## ADDED Requirements

### Requirement: Phase 2 tables
Migration `0002` SHALL add `enrichment_fields`, `model_calls`, `source_calls` and `claims`,
add the brief's design, caps and verifier version and the draft's sentences with supports
and critic notes, widen the exit-reason, flag, run-kind and run-source CHECK lists, and keep
every Phase 1 row and trigger.

#### Scenario: Upgrade from Phase 1
- **WHEN** `adscout db upgrade` runs on a Phase 1 database
- **THEN** it takes a backup, applies `0002`, keeps every existing row, and the leads
  immutability triggers still refuse changes

### Requirement: No page text stored
The database SHALL store no fetched page text or HTML except claim quotes of at most 300
characters; full pages SHALL live only in the gitignored replay cache.

#### Scenario: Oversized quote refused
- **WHEN** code inserts a claim whose quote is 301 characters
- **THEN** the database refuses the row
