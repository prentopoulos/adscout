## 1. Toolchain

- [ ] 1.1 Move pydantic and PyYAML to `[project].dependencies`, relock, and add a test that every third-party import under `src/adscout/` is a declared dependency
- [ ] 1.2 Add `--cov-fail-under=90` to the gate's test step, with a test that the threshold is present; gitignore `data/`
- [ ] 1.3 Set PROJECT.md §6 Phase 1 to In progress with the first implementation commit

## 2. Segment config and seeds

- [ ] 2.1 Segment config and seed row models (strict, null reasons), safe YAML and CSV loaders, domain normalization, and the email/phone value guard, with tests for every segment-config scenario
- [ ] 2.2 Export `config/schemas/segment.schema.json` and `seed-row.schema.json` with drift tests; canonical-JSON content hashes with the comment-edit and value-edit tests
- [ ] 2.3 Write `config/segments/gaming-hardware-na.yaml` and `config/seeds/gaming-hardware-na.csv` (the five checked seeds with provenance notes)

## 3. Database

- [ ] 3.1 Connection helper (foreign keys, WAL, `ADSCOUT_DB` and `--db`), migration runner with the checksum table, backup before upgrade, and `adscout db upgrade`
- [ ] 3.2 Migration `0001_initial.sql` with every table, CHECK lists, immutability triggers and views; committed `schema.sql` with the fresh-migration test
- [ ] 3.3 Schema tests: foreign keys, immutable-field UPDATE and DELETE refused, triggers present, personal-contact column guard, unknown exit reason refused
- [ ] 3.4 UUIDv7 helper and agent-version helper (`+g<commit>`, `.dirty`) with tests

## 4. Pipeline run

- [ ] 4.1 Step contracts (pydantic input and output models) and the runner: run and step records, timings, null reasons, status, error category, failed-run handling, stale-run interruption and the concurrent-run refusal
- [ ] 4.2 Real `source` step: seed loading, domain dedupe against the seed list, existing leads and the CRM, exclusions; lead creation with immutable fields and config snapshots
- [ ] 4.3 Stub steps for enrich, rules, score, research and draft driven by `config/stubs/gaming-hardware-na.yaml` (outcomes, rationale and sources from the design's desk research), plus a synthetic fixture script that exercises every exit reason and flag; `adscout run`
- [ ] 4.4 Stub approver bound to the draft SHA-256 and `adscout approve --stub`
- [ ] 4.5 CRM writer and local fake CRM (dedupe by domain, owned fields only, person-edited fields kept with a logged conflict, idempotent) and `adscout sync`, with the CRM-writer scenarios and a test that no other module writes CRM tables

## 5. Checks, summaries and export

- [ ] 5.1 Independent run check over SQL only and `adscout check`, with the conservation, monotonic-funnel, labelling, immutable-field and approval tests
- [ ] 5.2 `adscout runs` and `adscout funnel`
- [ ] 5.3 `adscout export` with the OpenTelemetry/Langfuse mapping table, the committed export schema, and the dirty-tree refusal for `evidence/runs/`
- [ ] 5.4 `scripts/demo.py` chaining upgrade, run, approve, sync, check and funnel, with a test that runs it offline on synthetic seeds
- [ ] 5.5 Eval scaffold: fill `agent_version` and rewrite the "Phase 1" null reasons; update the scaffold test

## 6. Architecture diagrams

- [ ] 6.1 Install Microsoft OpenJDK 21 beside Java 11 and download the Structurizr `-playwright` war outside the repo (owner-approved, Q10); record versions in HANDOFF
- [ ] 6.2 Write `docs/architecture/workspace.dsl` (context, built and target container views, Planned tags), validate it, export SVG and Mermaid, and commit the export stamp with its drift test
- [ ] 6.3 `scripts/erd.py` generating `docs/architecture/erd.md` with its drift test
- [ ] 6.4 Update the showcase skill's C4 reference with the Java war export commands

## 7. Verification and close

- [ ] 7.1 From a clean tree, run the demo on the five seeds into a fresh database, run `adscout check`, and commit the three runs' exports under `evidence/runs/`
- [ ] 7.2 Run the gate (all steps, coverage at least 90%) and pip-audit; record results in HANDOFF
- [ ] 7.3 Run the WORKFLOW.md code review (`/code-review` on `main...phase-1/thin-pipeline`, plus requirements and non-negotiables check); fix or answer each finding
- [ ] 7.4 Update AI_OPS.md capability rows and evidence pointers, and HANDOFF.md with checks, limitations and the next action
- [ ] 7.5 Bump the version to 0.2.0, archive the change, sync specs, set Phase 1 Done, rerun validation and the gate; merge on the owner's go-ahead
