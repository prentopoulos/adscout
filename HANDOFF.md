# Current handoff

Read PROJECT.md and current user instructions. Inspect actual Git/OpenSpec state before resuming.

## Current checkpoint

Phase 1 (thin end-to-end pipeline with stub steps) is complete. OpenSpec change
`phase-1-thin-pipeline` is archived on branch `phase-1/thin-pipeline`, which merges into `main`
with a merge commit on the owner's go-ahead. The code review ran and its findings are resolved
(Verification below).

- Grilling ran on 2026-10-18; the owner accepted every recommendation (Q1–Q16). Decisions are
  in PROJECT.md §2–4 and §6 and in the archived change's design, with who made each.
- First segment: gaming hardware brands in North America (settled with the owner; do not
  reopen).
- Seeds: 8bitdo.com, corsair.com, nzxt.com, razer.com and turtlebeach.com, each checked once on
  its home page under the owner's scoped live-read decision (PROJECT.md §6). steelseries.com
  answered HTTP 403 and was left out.
- The scripted stub outcomes follow one-off desk research the owner asked for (design
  decision 15; sources in `config/stubs/gaming-hardware-na.yaml`): Corsair, Razer and Turtle
  Beach approved and synced; NZXT rejected at approval; 8BitDo below the score threshold. They
  are the agent's judgement, not the owner's labels.

Phase 0 (toolchain, local gate, offline evaluation scaffold) was merged on 2026-10-18 (f5706ec);
its verification record is in commit 8c79625's HANDOFF.md.

## Implemented behavior

- Package `adscout` 0.2.0 (Python 3.13, src layout, `uv.lock`); runtime dependencies pydantic
  and PyYAML.
- Config: `config/segments/<id>.yaml` (strict, nulls with reasons), `config/seeds/<id>.csv`
  (company-level columns only), `config/stubs/<id>.yaml` (scripted stub outcomes; a real
  company's outcome needs a rationale and sources). Values that look like an email address or
  phone number are refused. JSON Schemas in `config/schemas/`.
- Database: SQLite at `data/adscout.db` (gitignored; `--db` or `ADSCOUT_DB`), numbered SQL
  migrations with checksums and a backup before each upgrade, committed
  `src/adscout/db/schema.sql`, triggers that refuse any change or deletion of a lead's source
  fields, views `v_funnel` and `v_lead_journey`, a guard against personal-contact columns.
- Commands: `adscout db upgrade`, `run`, `approve --stub`, `sync`, `runs`, `funnel`, `check`,
  `export`; `scripts/demo.py` chains the whole flow. All offline.
- Pipeline: real `source` step (domain dedupe, exclusions, lead creation with UUIDv7 IDs and
  agent version `<package>+g<commit>[.dirty]`, prompt version `none`), five scripted stub
  steps, a run that stops at approval, a stub approver bound to the draft's SHA-256, and the
  single CRM writer into a local fake CRM (dedupe by domain, owned fields only, person edits
  kept and logged). Each step works outside any transaction and writes in one short one. One
  live run at a time; a dead `running` run is marked `interrupted`; leads of an unfinished run
  re-enter the next run.
- Run records: `runs`, `step_runs`, `lead_step_outcomes` with the system version and explained
  nulls. `adscout check` validates a run from the database alone. `adscout export` writes JSON
  Lines with OpenTelemetry GenAI and Langfuse names (`src/adscout/schemas/run-export.schema.json`).
- Diagrams: `docs/architecture/workspace.dsl` (context, built and target container views),
  SVG and Mermaid exports with a stamp, and `docs/architecture/erd.md` generated from the
  schema. Gate tests fail on drift without needing Java.
- Gate: as in Phase 0, with a 90% line-coverage threshold on `src/` and `scripts/`.

## Phase 1 verification (2026-10-18)

- **Gate:** all 12 steps pass at c957258, the last code commit: 218 tests, coverage of `src/`
  and `scripts/` 94%, 6 scaffold cases.
- **Evidence runs:** from a clean worktree at c957258 (the main tree has the owner's untracked
  `.codex/config.toml`, which marks it dirty), `scripts/demo.py` on the five real seeds wrote
  three runs, each `succeeded`, `code_dirty` 0, agent version `0.1.0+gc957258643cd`, and
  `adscout check` pass. Exports in `evidence/runs/phase-1-20261018T170334Z-{585a29,ba73a2,8e454e}.jsonl`.
  Pipeline: 5 sourced, 1 below threshold at score (8BitDo), 4 drafts; approval: 3 approved,
  1 rejected (NZXT); CRM sync: 3 written to the fake CRM. A separate script validated all 46
  export lines against the committed schema and recomputed every step's counts, the funnel
  chain, the explained nulls and the stub labels from the exports alone: no problems. This is a
  structural check of a stub pipeline, not an AI evaluation (not_run).
- **Dependency audit:** `uv run --locked pip-audit --skip-editable` (pip-audit 2.10.1) on
  2026-10-18: "No known vulnerabilities found" after pydantic and PyYAML became runtime
  dependencies. The review fixes changed no dependency.
- **Code review:**
  - Inline, by the implementing agent, against every spec requirement and the design's
    non-negotiables check: it corrected the design where the build differed (Langfuse release
    instead of the unconfirmed `gen_ai.agent.version`; WebKit, not Chromium), bda1bb3.
  - `/code-review high` of `main...phase-1/thin-pipeline`, run by a separate agent session
    (same model, fresh context, not a human review; it could not run the tests because of the
    temp-folder problem below). It reported 10 findings; all were fixed in c1b7e0c and c957258
    with regression tests: leads of a failed run stuck as duplicates; approval loading the
    unused seed list; tracebacks for migration, SQLite and Git errors; approval and sync
    reading their work before taking the run lock; stub labels and `fail_at_step: source`
    accepted but broken; export null reasons under raw column names; Windows "access denied"
    read as a dead process; duplicated helpers; the write lock held during a step's work.
  - Answered without a change: re-syncing logs a `no_op` CRM write for every approval each
    time, which the spec's "log every write" asks for.

## Findings and limitations

- **Temp folder:** in the agent's shell on this PC, `%TEMP%\pytest-of-Peter` (created
  2026-10-04) denies access, so pytest's `tmp_path` fails there. Runs set
  `PYTEST_DEBUG_TEMPROOT` to a short writable folder; `C:\Users\Peter\AppData\Local\Temp\p`
  worked on 2026-10-18, while the deeper agent scratchpad hit Windows' 260-character path
  limit in the digest tests. Deleting that folder may fix it.
- **Untracked `.codex/config.toml`** (the owner's, not committed) makes the main tree dirty, so
  evidence runs come from a clean worktree. Committing or ignoring it is the owner's call.
- **Diagram tooling (owner-approved, 2026-10-18):** Microsoft OpenJDK 21.0.12.1 unzipped to
  `C:\Users\Peter\tools\jdk-21.0.12.1+1` (zip SHA-256 matched Microsoft's published
  `192441a9…5ce07f`; no installer, no PATH change; Java 11 stays the default), and
  `C:\Users\Peter\tools\structurizr\structurizr-2026.09.19-playwright.war` (no checksum is
  published; SHA-256 `7b717f14…077d90` as downloaded). The first SVG export downloaded
  Playwright's WebKit to `%LOCALAPPDATA%\ms-playwright`. Commands are in the showcase skill's C4
  reference and the header of `docs/architecture/workspace.dsl`.
- **Target container view** is legible but its planned-system lines cross some labels near the
  pipeline; arranging it by hand belongs with the Phase 6 showcase work.
- **A `running` run recorded on another host name** (for example after renaming the PC) blocks
  every new run, and no command clears it; it would need a manual SQL update.
- **The agent version needs a Git checkout;** a Phase 6 container needs a build-time stamp.
- **The secrets scan** matches any name containing KEY, TOKEN, SECRET or PASSWORD; two
  OpenTelemetry token-count attribute names in `src/adscout/export.py` are allowlisted with a
  reason. Confirm each provider's key prefix when its account is created.
- **The commit check** compares the branch with `main`; commits made directly on `main` are not
  checked, and Git's default `Revert "…"` subjects fail it.
- **The link check** fails on links to gitignored files, such as the local playbook PDF.
- **Ruff 0.17** also formats Markdown code blocks, so `pyproject.toml` limits ruff to Python
  files.
- **OpenSpec telemetry:** the gate and `.claude/settings.json` turn it off; other terminals and
  harnesses send a usage event unless `OPENSPEC_TELEMETRY=0` is set there.
- **Open for later phases** (Phase 1 design, Open Questions): what counts as a qualified lead and
  the score scale and threshold (Phase 2); the minutes-per-account definition (Phase 5), with
  the owner timing their own research on the five seeds before then; whether to cover the
  posting's automation tools (the deferred n8n variant); the CRM sandbox product (Phase 4).

## Next action

If `phase-1/thin-pipeline` is not yet merged into `main`, ask the owner for the merge
go-ahead, merge with `git merge --no-ff`, confirm it landed and delete the branch. Then clear the
context and run `/next-phase` to start Phase 2 (enrichment with field validation, profile rules
and LLM fit scoring, PROJECT.md §6). Its grilling must answer the model cost and access items in
PROJECT.md §4 and the qualified-lead definition before the first model call.
