# Current handoff

Read PROJECT.md and current user instructions. Inspect Git/OpenSpec state before resuming.

## Current checkpoint · 2026-10-19

Branch `phase-2/ai-pipeline`; original change `phase-2-ai-pipeline` remains in progress.
The owner requested an MVP of the remaining project within one usage window and delegated
condensation/simplification. Scope commit `40da88d` records the smaller `local-mvp` change.
This does not waive gates, establish live quality, or complete/archive original Phase 2.
No remote, push, merge, paid call or account creation has occurred.

The local implementation is built: real pipeline code using synthetic sites and scripted
model responses; a loopback workspace for human review, local CRM sync, local sandbox
messages/unsubscribe and simulated deals; generated diagrams and a README. Browser flows
and desktop/narrow layouts are now verified. The owner subsequently requested recruiter
slides and a video; six editable Figma slides, a PDF and a captioned two-minute MP4 were
created privately using actual app captures and the owner's supplied artifact styling.
See [verification and review](docs/local-mvp-verification.md).

## Run the MVP

```powershell
uv run --locked adscout demo
```

Open http://127.0.0.1:8765. The default database is `data/demo.db`; subsequent runs preserve
decisions. `--db data/another-demo.db` starts a separate demo without deleting anything.
Use `--prepare` to populate without serving. See [README](README.md) for the walkthrough.
No credentials needed. The inbox is SQLite, not an email service; all revenue is simulated.

## Implemented behavior

- Package 0.2.0, Python 3.13, uv lock; anthropic/httpx2/langgraph runtime dependencies.
- Real source, enrichment, profile rules, weighted rubric score/router, research team
  (lead plus three workers or single-agent baseline), claim verifier, writer/checker/critic.
  The registry supplies graphs, tool allowlists and generated flow documentation.
- Fake/replay/live model transports, price table, Decimal cost, spend reservation, transient
  retries, one escalation, role prompt/schema versions, call sinks and replay/page cache.
- Polite fetcher: robots, rate limits, egress and site-list refusal, source call records.
  LangSmith tracing variables refused; role contexts exclude private data; ten planted
  injection pages with clean twins tested offline.
- SQLite schema 3: migration 0003 adds reviewed-subject hashes, sandbox messages and
  suppressions, and explicitly simulated USD deals. Backups/checksums and schema/ERD updated.
- Human review binds both subject and body. Stale decisions and tampering cannot authorize
  delivery. Partial research and unresolved critic objections are visible before approval.
  Generic operator identity; draft editing is deferred.
- Existing one CRM writer remains the only CRM write path, preserving person edits.
  Repeated scores use routing sample 1 in both dashboard and CRM.
- One local send function: human approval, unchanged text, synthetic domain, CRM record,
  fixed synthetic sender/footer, unsubscribe and idempotence. No external send adapter.
- Local HTTP UI: fixed 127.0.0.1 bind, strict Host/Origin, CSRF, bounded POST forms,
  escaped content and restrictive CSP. No multi-user/login claim.
- Local span tree and model/source-call export with cost summaries: `adscout trace`,
  `export`, `check`, `runs`, `funnel`, `rescore`; evaluation comparison tooling remains.
- Registry HTML/Markdown, C4 context/container/research component SVG and Mermaid exports,
  ERD, stamps and drift tests. Private artifact republishing remains deferred.

## Verification

- Gate: all 12 steps pass; 518 tests and 90 evaluation tests pass, 94.81% coverage.
  Final consolidated log: ignored `.local/mvp-gate-consolidated.log`.
- Focused tests: 63 database/architecture/diagram/workspace tests passed. Final workspace
  security, flag-display and repeated-score regressions: 9 passed. Ruff lint/format and
  strict mypy (92 source files) pass.
- Initial full gate: 516 passed, one false-positive CRM scanner failure, 94.44% coverage;
  90 evaluation tests pass. Fixed the scanner to inspect actual SQL strings via AST.
  Initial failure and later logs retained separately in ignored `.local/`.
- Dependency audit: `uv run --locked pip-audit --skip-editable --progress-spinner off`:
  no known vulnerabilities found; editable AdScout skipped. No dependency changed for MVP.
- Actual loopback HTTP smoke in an isolated process: HTTP 200 with review and evidence
  content. Full POST workflow tested through the real handler with sockets blocked.
  Earlier Chrome loopback timeouts and the blocked file preview are retained in the record.
  The subsequent browser pass used the current build on a fresh loopback port (8767),
  avoiding an older server still bound to 8765. Actual approval, CRM sync, inbox placement,
  unsubscribe plus refused re-delivery, review warnings, simulated deal and rejection pass.
  At 390 px, body width is 375 px and the table scrolls inside its 341 px container.
- Manual self-review against local spec and constitution completed; findings/regressions
  recorded in `docs/local-mvp-verification.md`. No independent reviewer available here.
  Original whole-phase closure review is still open.

## Deferred original work and decisions

Original task 6.1: real-seed media kit waits for owner publisher name; the fixture kit is
enough for demo. Task 8.4 local generation/exports/tests are built; private republishing is
not done. Tasks 9–10 (30 seeds, sites, labels, precommitted plans and paid studies) and
original full-phase review/version/archive remain open. Original task 11.3's capability
map and handoff are updated for this local checkpoint, not evidence of live completion.

Before any original live study: owner approval of rubric anchors, seed/site lists, labels,
publisher, account/credit/key/contact and relevant PROJECT.md gates. Resolve the research
comparison's unequal step caps (single 12 versus team 20) before its plan is committed.
The person-name detector is heuristic and needs owner scrutiny on live claims. No tier
winner, multi-agent advantage or measured business outcome has been established.

Deferred from original Phase 3: cloud CRM/inbox/tracing, hosted CI and Docker. Recruiter
slides and video are prepared privately; the MP4 is not committed or published. The timed
script is `docs/walkthrough.md`; final files and verification are in ignored
`.local/showcase/deliverables` and `.local/showcase/delivery.json`.
No real outreach or personal-contact data is available. Publication and exposure gates
remain unresolved. The local inbox is for software tests, not approval of an email service.

## Environment and recovery

- The owner's untracked `.codex/config.toml` remains untouched; it makes ordinary checkout
  runs dirty. Do not stage, ignore or erase it. Clean-tree live evidence needs another checkout.
- In this tool environment, use `.local/tmp` for TEMP, TMP and PYTEST_DEBUG_TEMPROOT, and
  `.local/uv-cache` for UV_CACHE_DIR. Default temp/cache permissions can break SQLite tests.
- Structurizr exports use the already-installed JDK 21 and WAR under the local tools folder.
  Existing Playwright browsers live under the default Playwright cache;
  pass that as PLAYWRIGHT_BROWSERS_PATH rather than redownloading. Re-export before stamping.
- Preserve failed runs, databases and caches. A dead local run is marked interrupted on
  retry. Another-host running records require operator investigation. Old code cannot
  downgrade schema 3; preserve the migration backup when investigating a regression.

## Earlier phase evidence

Phase 0 merged at f5706ec. Phase 1 code review fixes and gate at c957258: 218 tests,
94% coverage and six scaffold cases. Three clean-tree Phase 1 stub runs and exports in
`evidence/runs/phase-1-20261018T170334Z-{585a29,ba73a2,8e454e}.jsonl` passed independent
checks (5 sources, 4 drafts, 3 approvals/CRM writes). They establish pipeline structure,
not AI behavior. Detailed historical evidence is retained in Git history.

## Exact next action

The local browser check is complete. The owner can review the private recruiter deck/PDF
and captioned video. Next choose whether to resume deferred live validation or keep the
offline MVP as the portfolio cut. Do not merge/archive original Phase 2 because the demo works;
its original gated tasks and whole-branch closure review remain open.
