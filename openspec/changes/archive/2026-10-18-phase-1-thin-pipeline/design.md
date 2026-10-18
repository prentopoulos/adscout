## Context

Phase 0 left a package `adscout` 0.1.0 with only `--version`, a twelve-step gate, and an
offline evaluation harness. There are no runtime dependencies (pydantic, PyYAML and
jsonschema are dev-only), no config, no database and no diagrams. The PC has Python 3.13.16
(bundled SQLite 3.53.1, no `uuid.uuid7`), the Anaconda `sqlite3` CLI 3.39.3, Java 11, Node
22.19.0 and OpenSpec 1.6.0, and no Docker, Structurizr, mermaid-cli or Graphviz.

Phase 1 grilling ran on 2026-10-18 in two rounds with one informed-answerer pass. The owner
accepted every recommendation (Q1–Q16) and kept the first segment as PROJECT.md's example,
gaming hardware, after weighing others. The answerer's Q5, Q10b, Q11c, Q12, N4 and N6 were
settled; they appear below with their basis.

**Seed checks (owner's live-read decision, 2026-10-18).** The agent opened each candidate's
home page once with a page fetch tool:

| Company | Domain | What the page showed |
|---|---|---|
| Corsair | corsair.com | "Copyright © 1996 - 2026 CORSAIR"; gaming peripherals, components and PCs; Canadian store |
| Razer | razer.com | "Copyright © 2026 Razer Inc."; peripherals, controllers, laptops; United States site |
| Turtle Beach | turtlebeach.com | "© 2026 Turtle Beach"; gaming headsets, controllers, flight sticks |
| NZXT | nzxt.com | "© 2026 - NZXT"; prebuilt gaming PCs and components; United States region |
| 8BitDo | 8bitdo.com | "8BitDo" header, no copyright line; controllers and keyboards; "Now In Target Stores Nationwide" |

SteelSeries (steelseries.com) answered HTTP 403 and was not retried, so it is not a seed. A
403 says nothing about the domain; it may join the Phase 2 list.

**Desk research for the stub script (owner's request, 2026-10-18).** After reviewing the
spec, the owner asked for the scripted outcomes to follow what each seed would likely get in
the real world. The agent ran six web searches on the five seeds, retrieved 2026-10-18:

| Company | Finding | Source |
|---|---|---|
| Corsair | Public; 2025 revenue $1,472.5M, up 12% | SEC 8-K exhibit 99.1, sec.gov/Archives/edgar/data/1743759/000119312526048668/crsr-ex99_1.htm |
| Razer | Taken private in 2022 (94.74% of shareholders in favour); passed US$1B revenue in FY2020; sponsors North American esports teams | vulcanpost.com/786487; businesswire.com/news/home/20210324005217; gamesbeat.com (Denial Esports) |
| Turtle Beach | Public; 2025 revenue $319.9M; weak fourth quarter blamed on soft North American gaming-accessory demand | SEC 8-K exhibit 99.1, sec.gov/Archives/edgar/data/1493761/000119312526104292/tbch-ex99_1.htm |
| NZXT | Private, revenue not published; agreed a $3.45M class-action settlement over its Flex PC rental program without admitting wrongdoing, pending court approval | techspot.com/news/112053; consumeraffairs.com (Flex class action) |
| 8BitDo | Private, Shenzhen, founded 2013; third-party estimate of $5–25M revenue and 250–500 staff (unverified) | owler.com/company/8bitdo |

## Goals / Non-Goals

**Goals** (acceptance evidence, owner, grilling Q1):
1. `adscout run`, `approve --stub` and `sync` take the five seeds end to end, and the
   committed export of each run comes from a clean tree.
2. `adscout check` passes on those runs: per step kept + exited = entering, counts never
   rise, stub rows labelled, immutable fields present, CRM writes only for approved leads.
3. Schema tests: lead IDs present and unique; UPDATE and DELETE of immutable fields refused;
   triggers present after migration; a fresh migration equals `schema.sql`.
4. A deliberately failed run is kept with status `failed` and all its rows.
5. Invalid config and seed files are rejected, naming the field.
6. The C4 views are exported to SVG and Mermaid; the ERD is generated; both drift checks bite.
7. The gate passes with the 90% coverage threshold; pip-audit runs at close.
8. The code review under WORKFLOW.md is complete.

**Non-Goals** (owner, grilling Q1): network or live reads by the pipeline, model calls, real
enrichment, rules or scoring, HubSpot, sends, contacts, an approval UI, the dashboard,
revenue or deal tables, Langfuse export, Docker, CI, the 20–50 seed list, and the
qualified-lead definition.

## Decisions

Owner calls are marked **owner**. Settled answers give their basis, with sources retrieved
2026-10-18. Question numbers are those the owner answered.

1. **Phase scope (owner, Q1).** All eight steps exist. `source` (load, normalize, dedupe,
   exclusions) is real code. `enrich`, `rules`, `score`, `research` and `draft` are stubs
   scripted from a committed file, so every exit happens; pass-through stubs would make the
   conservation check trivially true. Approval is a labelled stub approver; CRM sync goes
   through the single CRM writer into a local fake CRM.
2. **Segment (owner, Q2).** `gaming-hardware-na`: peripherals, PC components, prebuilt
   gaming PCs and console accessories from brands that sell to consumers in the US and
   Canada. Headquarters is recorded but is not a rule, because many large brands in this
   market are based in Europe or Asia. Size range and score threshold are null until Phase 2.
3. **Seeds (owner, Q3 and Q16).** Five real companies, name and domain only, in
   `config/seeds/gaming-hardware-na.csv` with `name, domain, source, added_by, added_on,
   notes`. The agent proposed them; the owner delegated the domain check to the agent under a
   scoped live-read decision (PROJECT.md §6), recorded above. Tests use synthetic companies on
   RFC 2606 names (`.example`, `.test`). The 20–50 list waits for Phase 2 and the live-read
   gate's run size.
4. **Database (owner, Q4).** SQLite through the standard-library `sqlite3`: WAL, foreign keys
   on every connection, STRICT tables, and SQL views (`v_funnel`, `v_lead_journey`) as the
   read interface for the Phase 6 dashboard. Look-ahead: Metabase supports SQLite officially
   and Streamlit's docs start with it; WAL lets a dashboard or approval UI read while the
   pipeline writes; Langfuse keeps its own stores, so Phase 5 is unaffected. DuckDB allows
   one read-write process per file and has only a community Metabase driver; Postgres needs an
   install; Looker Studio reads neither file engine. Features newer than SQLite 3.39 are
   avoided so the owner's CLI can open the file.
5. **Migrations (settled, default).** Hand-written SQL in
   `src/adscout/db/migrations/NNNN_name.sql`, each in one transaction, recorded in
   `schema_migrations` with its SHA-256; an edited applied migration fails. A committed
   `schema.sql` snapshot (tables, indexes, triggers, views) is compared with a fresh migration
   by a test, because a SQLite table rebuild silently drops its triggers. A backup through the
   SQLite backup API precedes each upgrade. SQLAlchemy 2.1.5 with Alembic 1.20.0 adds runtime
   dependencies, and Alembic's SQLite batch mode does not copy CHECK constraints; yoyo
   (2024-08) is stale; `user_version` alone has no checksum. Basis also recorded: PROJECT.md
   §4 lists SQL among the skills the tools should show.
6. **Lead identity and source fields (owner, Q5).**
   - `companies` is global, keyed by normalized domain. A lead is one company within one
     segment, `UNIQUE(segment_id, company_id)`, created on first sourcing; later runs record
     `duplicate` at `source`. Evaluations and experiments use another database file.
   - Lead IDs are UUIDv7 (RFC 9562) as 36-character text, from a small standard-library
     helper until Python 3.14's `uuid.uuid7()`. Their 32-hex form is a valid trace ID for
     Langfuse. Run IDs keep the harness format `YYYYMMDDTHHMMSSZ-xxxxxx`.
   - Immutable: lead ID, segment ID, company, source (`seed_list:<segment_id>@<hash>`),
     prompt version, agent version, creating run and creation time. `BEFORE UPDATE OF` and
     `BEFORE DELETE` triggers `RAISE(ABORT)`; the code has no update path. Triggers do not
     guard against `DROP TABLE`, which only a migration could do.
   - Agent version `<package version>+g<12-char commit>` with `.dirty` for an uncommitted
     tree (PEP 440 local label). Evidence runs require a clean tree. A Phase 6 container
     without Git needs a build-time stamp.
   - Prompt version is the literal `none` while no prompt runs; Phase 2 defines the
     prompt-set digest.
7. **Run records (owner, Q6).** The database is the only record; there is no JSONL stream
   beside it.
   - `runs`: ID, kind (`pipeline`, `approval`, `crm_sync`), times, status (`running`,
     `succeeded`, `failed`, `interrupted`), error category, validation outcome and detail,
     process ID and host, and the system version listed in the pipeline-run spec, with
     budgets and null reasons as JSON.
   - `step_runs`: step, sequence, implementation (`stub`/`real`) and version, times,
     duration, status, entering, kept and exited, and model, input and output tokens and
     cost, null with reasons for stubs.
   - `lead_step_outcomes`: run, lead, step, outcome, exit reason or flag, detail, times.
   - Columns are snake_case. A mapping table in the export module ties them to OpenTelemetry
     GenAI names (`gen_ai.request.model`, `gen_ai.usage.input_tokens`,
     `gen_ai.usage.output_tokens`) and to Langfuse (run → `langfuse.session.id`, agent
     version → `langfuse.release`, cost → `gen_ai.usage.cost`). `gen_ai.agent.version` is not
     used: the current conventions (checked 2026-10-18) did not confirm it. The GenAI
     conventions are Development status, so that table is the one place to update.
   - `adscout export` writes JSONL with those names, validated against
     `src/adscout/schemas/run-export.schema.json`. Exports cited as evidence go in
     `evidence/runs/`, extending the owner's Phase 0 rule for evaluation runs.
   - Minutes per account is computable from the timings but reported null in Phase 1 ("stub
     timing is not a measurement"); its definition is a Phase 5 decision.
   - A second run is refused while another run's process is alive; a stale `running` row is
     marked `interrupted`. Writes use `BEGIN IMMEDIATE`.
8. **Contacts (owner, Q7).** No contacts table in Phase 1. The schema guard and the
   config/seed value guard enforce "no personal contact data" now. Recorded for Phase 4: a
   `contacts` table with `synthetic INTEGER NOT NULL CHECK (synthetic = 1)`, emails limited
   to RFC 2606 names (`.example`, `.test`, `.invalid`, `example.com/.net/.org`), names from
   a fixed fictional list; consent and unsubscribe fields come with the send rules.
9. **Config format (owner, Q8).** YAML loaded with `yaml.safe_load`, validated by strict
   pydantic models; pydantic and PyYAML move to `[project].dependencies`. JSON Schemas in
   `config/schemas/` with a drift test. Hashes are SHA-256 of canonical JSON of the validated
   content, under the eval record's names `icp_config_hash` and `seed_list_hash`; each
   hashed snapshot is stored in a `config_snapshots` table. TOML lost only on familiarity.
10. **Commands (owner, Q9 and Q15).** argparse subcommands: `adscout db upgrade`, `run
    --segment <id> [--seeds PATH] [--db PATH]`, `approve --stub`, `sync`, `runs`, `funnel
    <run_id>`, `check <run_id>`, `export <run_id>`. `approve` and `sync` follow from the run
    split (Q15). `scripts/demo.py` chains upgrade, run, approve, sync, check and funnel on one
    database file.
11. **Database file (settled, default).** `data/adscout.db`, gitignored with `-wal`, `-shm`
    and `data/backups/`; `--db` or `ADSCOUT_DB` overrides; tests use `tmp_path`. No reset or
    drop command. Cited runs survive through committed exports; losing the file loses
    uncited runs. Basis also recorded: §5 "Preserve failed runs" and the Phase 0 retention
    rule. `.local/` stays for private notes.
12. **Step order (owner, Q13).** `source, enrich, rules, score, research, draft`, then the
    `approve` and `crm_sync` runs. The playbook puts profile rules before enrichment on one
    slide and after it on another; rules on region, category and size need enriched fields,
    since seeds hold only name and domain. Step names are a CHECK list in the schema.
13. **Exit vocabulary (owner, Q14).** Exit reasons: `duplicate`, `excluded`,
    `out_of_profile`, `missing_key_fields` (to a person), `below_threshold` (nurture list),
    `draft_failed` (to a person), `rejected`. Flags on kept leads: `research_partial`,
    `crm_conflict`. The qualified-lead definition, and so cost per qualified lead, is
    decided in Phase 2 grilling.
14. **Run split at approval (owner, Q15).** A pipeline run ends with drafts
    `pending_approval`; it does not wait for a person. Approval is its own recorded decision
    bound to the draft's SHA-256, with approver kind `stub` in Phase 1, so the Phase 4 send
    function can refuse stub approvals ("a shared CLI flag is not proof of an authenticated
    approver", agent-runtime reference). CRM sync is its own run over approved drafts.
15. **Stub script from desk research (owner, 2026-10-18, after the spec review).**
    `config/stubs/gaming-hardware-na.yaml` scripts each seed's path from the desk research
    above, and records per seed the expected outcome, the rationale and its source URLs with
    retrieval dates:
    - corsair.com, razer.com and turtlebeach.com: approved and synced;
    - nzxt.com: passes to a draft and is rejected at approval (brand-safety hold after the
      class-action settlement);
    - 8bitdo.com: exits at `score` as `below_threshold` (smallest marketing footprint; the
      revenue figure is an unverified estimate).

    No seed realistically exits at `rules` (all five sell in the US and Canada and fit the
    categories, and the size range is unset) or as a CRM `duplicate` (no CRM data exists).
    Database rows state no company fact: each stub reason reads "stub: scripted from desk
    research (config/stubs/gaming-hardware-na.yaml, 2026-10-18); not a pipeline assessment".
    Stub briefs carry no claims and stub drafts state no company fact. These expectations are
    the agent's desk-research judgement, not the owner's labels; Phase 2 can compare its real
    scores against them. A separate synthetic fixture covers every reason and flag, including
    the CRM conflict.
16. **CRM writer and fake (owner, Q1).** `src/adscout/crm/writer.py` is the only module that
    writes CRM tables. The fake has `crm_accounts` (by domain), `crm_account_fields` (value
    and owner `adscout` or `person`) and `crm_writes` (operation ID, operation, fields,
    status). The writer dedupes by domain, writes only AdScout-owned fields, skips
    person-edited fields with a logged conflict, and is idempotent. Phase 4 adds the real
    sandbox adapter behind the same interface; the fake stays as its offline test double.
17. **Step contracts (settled, default).** Each step is a typed function over pydantic
    models; stored outputs (score with reasons, brief claims each with `source_url`, draft)
    get JSON Schemas the stubs fill. Score scale and range checks wait for Phase 2's rubric.
    Basis: next-phase skill §3. What would change it: a different Phase 2 output shape (one
    migration).
18. **Diagram export (owner, Q10).** Microsoft OpenJDK 21 installed beside Java 11, and
    `structurizr-2026.09.19-playwright.war` downloaded outside the repo; the current war
    requires Java 21 and only the `-playwright` builds export SVG (docs.structurizr.com/
    binaries). The JDK is Microsoft's zip unpacked into the owner's user folder (no
    installer, no PATH change). The first export downloads Playwright's WebKit browser.
    Exports: SVG per view and Mermaid. A committed `docs/architecture/export-stamp.json`
    holds the SHA-256 of `workspace.dsl` and of every export, ignoring line endings; a gate
    test compares them, so the gate needs no Java. No hosted playground.
19. **Diagram content (owner, Q11).** One model of the whole planned system; planned
    elements tagged `Planned` (dashed, grey, "(planned, Phase N)"); a context view, a
    container view "built, Phase 1" and a container view "target". The person is "Ad sales
    researcher at a publisher"; no real publisher is named (§1).
20. **ERD (settled, recorded and default).** `scripts/erd.py` (standard library) migrates a
    temporary database and writes a Mermaid `erDiagram` from `PRAGMA table_info` and
    `foreign_key_list` to `docs/architecture/erd.md`; a test fails on drift. Recorded:
    PROJECT.md §4 (Mermaid for README diagrams, ERD once a schema exists); Structurizr has no
    ERD. No SVG render, which would need mermaid-cli and a Chrome download.
21. **Coverage (settled, default).** `--cov-fail-under=90` on `src/` and `scripts/`, line
    coverage; last measured 90.46% at Phase 0's close; Phase 0 deferred the threshold here
    (HANDOFF.md). It only ratchets up.
22. **Eval scaffold (settled, recorded).** Records fill `agent_version` with the decision 6
    format, and the null reasons that say "defined in Phase 1" or "arrives in Phase 1" become
    true reasons (for example "scaffold cases have no segment"). Basis: §5 accurate labels.
23. **AI design choices (owner, Q12).** This design records:
    - autonomy: a workflow with one agentic step (research);
    - pattern per step: chained steps for enrich and score, rules plus a model rubric for
      scoring, a ReAct agent for research, evaluator-optimizer for drafts;
    - hosting: local, single user, on the owner's PC;
    - security check: Phase 1 reads no private data, takes no outsider-influenced input and
      has no outbound effect; recheck in Phase 3, when fetched pages arrive.

    Model tiers, access route and fallback stay TBD for Phase 2 (PROJECT.md §4); the agent
    framework (provider SDK loop or LangGraph) for Phase 3, the first phase with an agent
    loop. AI_OPS.md is corrected to match.

No AI behavior changes in Phase 1: no model, prompt or tool runs. The run record already names
the system bundle (code revision, lock digest, agent and prompt versions, config and seed
hashes), so Phase 2's first model call binds to a complete version.

## Data model

Migration `0001_initial.sql` creates `schema_migrations`, `config_snapshots`, `companies`,
`leads`, `runs`, `step_runs`, `lead_step_outcomes`, `enrichments`, `scores`, `briefs`,
`drafts`, `approvals`, `crm_accounts`, `crm_account_fields`, `crm_writes`, the leads
immutability triggers, and the views `v_funnel` and `v_lead_journey`. Every output row
references its lead and the run that wrote it and carries `implementation` (`stub` or `real`).
The committed ERD is generated from this schema.

## Rule, check and phase map

Updates the Phase 0 map for the rules Phase 1 touches. OWASP entries are from the Top 10 for
LLM Applications 2025.

| §5 rule | Check built in Phase 1 | Later |
|---|---|---|
| No fabricated results; labels; preserve failed runs | Stub labels on every row; null reasons; failed and interrupted runs kept; independent run check | Each phase |
| Synthetic personal data only (LLM02) | Schema column guard; config and seed value guard | Contacts table and fixture checks, Phase 4 |
| One CRM writer, dedupe, owned fields, logged (LLM06) | Writer contract tests on the fake CRM; no other module writes CRM tables | Real sandbox adapter, Phase 4 |
| Lead ID and immutable source fields | Triggers plus schema tests | — |
| No message to a real person (LLM06) | Approvals bound to draft hash, approver kind recorded | Send function refuses stub approvals, Phase 4 |

## Non-negotiables check

- **Secrets:** Phase 1 holds none and needs none; no adapter has a credential.
- **No fabrication:** every stub row is labelled `stub`; stub reasons say they are not
  pipeline assessments; stub briefs carry no claims; nulls carry reasons; failed runs are
  kept; the run check is independent of the runner. The seed table above reports what each
  page showed, including the 403, and every desk-research finding carries its source and
  retrieval date, with estimates marked unverified.
- **⛔ gates:**
  - Live reads: the pipeline and tests make no network call. The home-page checks and the
    desk-research searches ran under the owner's scoped decisions of 2026-10-18 (PROJECT.md
    §6). pip-audit at close runs under the Phase 0 decision.
  - Spend: none. The JDK, Structurizr war and Playwright browser are free downloads the owner
    authorized (Q10).
  - Accounts, sends, publishing, deployment: untouched. No hosted diagram editor.
- **No message to a real person:** no send path exists; approvals record their kind.
- **Synthetic personal data:** no contact table; guards above.
- **Research agent read-only:** no agent exists yet; recheck in Phase 3.
- **Brief citations and grounded drafts:** stub briefs have no claims; stub drafts state no
  company fact.
- **One CRM writer:** decision 16.
- **Lead ID and immutable source fields:** decision 6.
- **Revenue simulated:** no revenue data in Phase 1.

## Risks / Trade-offs

- **[Scripted outcomes for real companies read as verdicts]** → Each outcome rests on cited
  desk research kept in the stub script; database reasons say "not a pipeline assessment";
  the funnel output prints the `stub` label; the 8BitDo estimate is marked unverified.
- **[Desk research goes stale]** → Each source carries its retrieval date; Phase 2 replaces the
  script with real enrichment and scoring.
- **[WAL on a network or container-mounted file]** → WAL needs a local filesystem. Phase 6
  runs the dashboard beside the pipeline or reads a snapshot.
- **[Triggers do not survive a table rebuild]** → The `schema.sql` snapshot test includes
  triggers.
- **[OTel GenAI names may change]** → One mapping table in the export module.
- **[Agent version needs Git]** → Fine locally; Phase 6 adds a build-time stamp for the
  container.
- **[A lost database file loses uncited runs]** → Accepted; cited runs are committed as
  exports, and upgrades back up first.
- **[Diagram export needs Java 21 and a Playwright browser]** → Only for re-export; the gate checks the
  stamp without Java.

## Migration Plan

New database only; nothing to migrate. Rollback is reverting the branch; `data/` is
gitignored and kept.

## Open Questions

- What counts as a qualified lead, and the score scale and threshold: Phase 2 grilling.
- Minutes per account: its definition is decided in Phase 5. Before then the owner times
  their own manual research on the five seeds under a short written routine (owner, Q16).
- The posting lists automation tools (n8n, Make, Zapier), but the n8n variant is deferred
  (PROJECT.md §2). The owner raised whether to cover it; a later phase decides.
- The CRM sandbox product (HubSpot or Salesforce): Phase 4 grilling.
