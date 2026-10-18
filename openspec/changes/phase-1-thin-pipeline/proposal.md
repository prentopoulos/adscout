## Why

AdScout has a toolchain and a gate but no pipeline. PROJECT.md §6 Phase 1 builds the thin
end-to-end version first: one segment config, a seed list of real companies, a local database
and a runner that takes five companies through every step with stubs, so Phases 2–4 replace
one step at a time behind contracts that already work.

This change implements **PROJECT.md Phase 1** ("Thin end-to-end pipeline on five seed
companies with stub steps: segment and ideal-customer config, seed list, local database
schema for companies, scores, briefs, drafts, approvals and runs; C4 architecture diagrams as
code"). Its decisions come from the Phase 1 grilling of 2026-10-18, recorded in PROJECT.md
§2–4 and §6 and in design.md with who made each.

## What Changes

- **Segment config:** `config/segments/gaming-hardware-na.yaml` for gaming hardware brands
  that sell to consumers in the US and Canada, validated by a strict model with a committed
  JSON Schema. Size range and score threshold stay empty until Phase 2.
- **Seed list:** `config/seeds/gaming-hardware-na.csv` with five real companies (name and
  domain only), each domain checked on the company's home page under the owner's scoped
  live-read decision. Company-level columns only.
- **Database:** SQLite through the standard library, with numbered SQL migrations, a
  committed schema snapshot, and tables for companies, leads, enrichments, scores, briefs,
  drafts, approvals, a local fake CRM and run records. Lead source fields are immutable,
  enforced by triggers.
- **Pipeline:** a runner that takes a segment's seeds through source and dedupe (real code),
  then enrich, rules, score, research and draft (stubs scripted from a committed file), and
  stops with drafts waiting for approval. A labelled stub approver records decisions bound to
  each draft's hash. CRM sync writes approved leads through the single CRM writer into the
  local fake CRM.
- **Run records:** `runs`, `step_runs` and `lead_step_outcomes` with drop reasons, the full
  system version, and an outcome validated by a separate checker. Exports cited as evidence
  are committed.
- **Commands:** `adscout db upgrade`, `run`, `approve --stub`, `sync`, `runs`, `funnel`,
  `check` and `export`, plus a demo script that chains them.
- **Architecture diagrams:** a Structurizr DSL model with context and container views
  (built and target), exported to SVG and Mermaid, and a Mermaid ERD generated from the
  schema. Gate tests fail when either drifts.
- **Gate:** coverage threshold of 90% on `src/` and `scripts/`.
- **Evaluation scaffold:** records carry the agent version, and the null reasons that said
  "defined in Phase 1" are made true.

## Capabilities

### New Capabilities

- `segment-config`: segment and ideal-customer config, seed list, their validation, schemas
  and content hashes, and the company-level-only guard on their values.
- `pipeline-store`: the local database, migrations, schema snapshot, lead identity and
  immutable source fields, the personal-contact column guard, and retention.
- `pipeline-run`: the runner, step contracts and stubs, source and dedupe, run records and
  drop reasons, the stub approver, the CRM writer and fake CRM, the independent run check,
  export and the commands.
- `architecture-diagrams`: the C4 model and its views, the SVG and Mermaid exports, the
  generated ERD and their drift checks.

### Modified Capabilities

- `quality-gate`: the test step enforces a coverage threshold.
- `offline-eval-harness`: scaffold records fill the agent version instead of leaving it null.
- `project-toolchain`: the version scenario no longer pins 0.1.0; runtime dependencies are
  declared.

## Non-goals

- Network access in the pipeline or tests, model calls, prompts, real enrichment, real
  profile rules or scoring, and the research agent (Phases 2–3).
- HubSpot or any real CRM, sends, contacts, an approval UI (Phase 4).
- Dashboard, revenue or deal tables, Docker (Phase 6); Langfuse export and CI (Phase 5).
- The 20–50 company seed list and its run size (Phase 2, with the live-read gate).
- What counts as a qualified lead, score scale and threshold (Phase 2 grilling).

## Impact

- New: `config/`, `src/adscout/` modules for config, database, pipeline, CRM writer, checks
  and export, SQL migrations and `schema.sql`, `docs/architecture/`, `evidence/runs/`, tests.
- Changed: `pyproject.toml` (pydantic and PyYAML move to runtime dependencies; version 0.2.0
  at close), `uv.lock`, `.gitignore` (`data/`), `scripts/gate.py` (coverage threshold),
  `evals/runner.py` (agent version and null reasons), PROJECT.md, AI_OPS.md, HANDOFF.md.
- Owner's PC: Microsoft OpenJDK 21 and the Structurizr `-playwright` war outside the repo
  (owner, grilling Q10); its first export downloads Chromium.
- Constitution: no §5 rule or ⛔ gate is amended. One operator decision is recorded under
  the live-read gate (the five seed home-page checks), which PROJECT.md § Amending the
  constitution says is not an amendment.
