## 1. Foundations

- [x] 1.1 Add `anthropic` and `langgraph` (and `httpx2` if not already direct) as runtime dependencies, relock, extend the declared-dependency test, run pip-audit on the new set, and set PROJECT.md §6 Phase 2 to In progress with the first implementation commit
- [x] 1.2 LangGraph spike: a typed two-node graph with a `Send` fan-out and a bounded loop under `mypy --strict` and the socket block; record the outcome in design.md, and if it fails switch the registry to drive our own orchestration (decision 24)
- [x] 1.3 Migration `0002` (Phase 2 tables, widened CHECK lists, `replay` source, quote length limit) with table rebuilds; regenerate `schema.sql` and the ERD; upgrade-from-Phase-1 and trigger tests
- [x] 1.4 Segment config: size range, threshold 60, near-miss band, criteria with anchors and weights; regenerate the JSON Schema; config tests

## 2. Model access

- [x] 2.1 Dated price table `config/prices/anthropic.yaml` (models, cache, long-prompt and search prices, retrieval date) and the cost function with tests
- [x] 2.2 Adapter with fake, replay and live modes; key handling; `model_calls` rows with usage, trace fields and call roles; budget errors as `budget_exhausted`
- [x] 2.3 Lock-guarded spend reservation and per-run caps; cap-hit-mid-run and parallel-reservation tests
- [x] 2.4 Retry, fallback and escalation in our own code, with tests
- [x] 2.5 Record-and-replay cache in `data/cache.db`; replay runs at cost 0 with original cost kept; the $0 replay test
- [x] 2.6 Prompt files and digests in `src/adscout/prompts/`; stable cache-prefix and Haiku 100K guard tests

## 3. Enrichment

- [x] 3.1 Polite fetcher (User-Agent, robots.txt, pacing, limits, redirects, retries) on an in-process transport with fixture sites; `source_calls` rows
- [x] 3.2 Site-list model and `config/site-checks/` loader; live refusal of unapproved domains
- [x] 3.3 Wikidata and SEC EDGAR clients against recorded fixtures; pixel and tag detection; Haiku extraction; field validators; the real `enrich` step with key-field exits

## 4. Rules and scoring

- [x] 4.1 Real `rules` step and `evals/cases/rules.jsonl` (about 30 cases, all passing)
- [x] 4.2 Real `score` step: rubric prompt with anchors, structured output, code combination, cited-field check, router (`near_miss`, `below_threshold`, `score_failed`), `--score-repeats` (the step takes repeats; the `adscout run` flag is wired with the real pipeline in 5.1)
- [x] 4.3 `adscout rescore` and `python -m evals score-compare`

## 5. Research team

- [ ] 5.1 Agent registry and the pipeline, research and draft graphs built from it
- [x] 5.2 Worker loop: pinned `web_search` with direct callers, `max_uses`, blocked domains and location; `fetch_page` with the provenance and egress rules; `submit_findings`; per-worker and per-lead caps
- [x] 5.3 Lead plan and merge calls and the strict handoff models
- [x] 5.4 Claim verifier, `claims` storage and the verifier case set
- [x] 5.5 Brief outcomes (`research_failed`, `research_partial`) and `--research-design single` (the step takes the design; the `adscout run` flag is wired with the real pipeline in 5.1)

## 6. Drafts

- [ ] 6.1 Media-kit model and `config/media-kit/<publisher_id>.yaml` for the owner-named fictional publisher, after checking the name is not a real company (model, loader and a synthetic fixture done; the real file waits for the owner's publisher name)
- [x] 6.2 Writer with supported sentences, the deterministic rule checker and `evals/cases/drafts.jsonl` (about 30 cases, all passing)
- [x] 6.3 Critic and the rewrite loop with `draft_failed` and `critic_unresolved`

## 7. Security

- [ ] 7.1 Context builders per role, adapter tool-allowlist enforcement, the no-write-tool test, the canary test and the `LANGSMITH_TRACING` guard
- [ ] 7.2 Ten planted-injection pages with clean twins and their offline tests through the code paths
- [ ] 7.3 Check the OWASP Agentic item names against the official 2026 document and update the design's map

## 8. Observability and diagrams

- [ ] 8.1 Export mapping updated for the moved OTel GenAI conventions and `gen_ai.agent.version`; trace fields exported
- [ ] 8.2 End-of-run cost table by step, role and model with cost per lead and per qualified lead
- [ ] 8.3 `adscout trace`
- [ ] 8.4 `scripts/diagrams.py` generating `agents.md` and `agent-flow.html` with stamp and drift tests; C4 model with the research team view, re-exported; republish the private artifact from the generated page

## 9. Seeds, sites, labels and plans

- [ ] 9.1 Desk research for 30 seeds (about 6 edge cases) under the owner's scoped web-search decision; `config/seeds/gaming-hardware-na.csv` with provenance; owner approval
- [ ] 9.2 robots.txt and terms check of the 30 company domains under the owner's scoped decision; `config/site-checks/gaming-hardware-na.yaml`; owner approval
- [ ] 9.3 Owner labels the 30 seeds blind; commit `evals/labels/gaming-hardware-na.v1.csv` with its hash
- [ ] 9.4 Commit the plans in `evals/plans/` (score check and tier rule, worker tier, research design) before any live call they cover

## 10. Live runs (each behind its ⛔ gate)

- [ ] 10.1 Owner: Anthropic Console account, "adscout" workspace with a $45 limit and auto-reload off, $20 prepaid credit, key and contact in `.env`, web search enabled, project mailbox; then the free models-API check of Haiku web search support (decision 41)
- [ ] 10.2 5-seed live slice (cap $2.50) from a clean tree; review source coverage and cost per qualified lead; re-estimate the second purchase
- [ ] 10.3 Injection live run (cap $3): all ten pages pass
- [ ] 10.4 Tier evaluation (cap $6) by its plan; `adscout rescore` if Haiku wins
- [ ] 10.5 Owner: second prepaid purchase (about $25, re-estimated)
- [ ] 10.6 30-seed evidence run with 3× scoring (cap $8) from a clean tree; exports committed; $0 replay reproduces it; score check against the owner's labels
- [ ] 10.7 Research design comparison (cap $15) and worker-tier check (cap $3) by their plans; the owner's blind spot-check of up to 100 claims; enrichment hand-check of 10 companies against their cited sources

## 11. Verification and close

- [ ] 11.1 Gate (coverage at least 90%) and pip-audit; record results in HANDOFF
- [ ] 11.2 Code review under WORKFLOW.md (`/code-review` on `main...phase-2/ai-pipeline`, requirements and non-negotiables check); fix or answer each finding
- [ ] 11.3 Update AI_OPS.md capability rows and evidence, and HANDOFF.md with checks, limitations and the next action
- [ ] 11.4 Bump the version to 0.3.0, archive the change, sync specs, set Phase 2 Done, rerun validation and the gate (the merge follows on the owner's go-ahead)
