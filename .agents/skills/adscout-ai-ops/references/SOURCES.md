# Sources and adaptation limits

Adapted on 2026-10-11 from the user's local Udacity AI Ops Engineer Nanodegree (nd907)
archive, captured 2026-10-05. The archive contains course pages and video transcripts, but
not the cloud workspace source files or lab environments. This skill is an original
operational synthesis; it does not reproduce the course or claim its exercises were run.

## Course mapping

Paths below are relative to the course's `udacity_nd907/` directory. The setup kit retains
a full lesson/file inventory with SHA-256 fingerprints in course-source-manifest.json.
Installed projects need only this skill; the course folder is not a runtime dependency.

| Reference | Course / lessons | Techniques adopted |
|---|---|---|
| [System versions](system-versions.md) | AgentOps 2-3, 6-7; LLMOps 2-3; MLOps 6-13, 18-19 | Whole-system identity, prompt/config separation, environment locks, exact release artifacts |
| [Evaluation](evaluation.md) | AgentOps 4-5; LLMOps 10-11, 21-22; MLOps 14-15, 26-27 | Fixed datasets/rubrics, regression gates, slices, controlled experiments |
| [LLM/RAG](llm-rag.md) | LLMOps 4-9, 12-26 | Retrieval/generation separation, ingestion, cache near-misses, routing, budgets and profiling |
| [Agent runtime](agent-runtime.md) | AgentOps 8-13, 16-23 | Enforced guardrails, approvals, state/replay, concurrent isolation, MCP |
| [ML lifecycle](ml-lifecycle.md) | MLOps 2-29 | Data/feature lineage, tracking/registries, training gates, serving, drift, fairness/explainability |
| [Operations](operations.md) | AgentOps 14-19; LLMOps 8-9, 12-13, 25-26; MLOps 18-23 | Structured records, tracing, operational metrics and incident response |

## Additions from the 2026-10-17 study decks

[Design choices](design-choices.md), the spend levers in [LLM/RAG](llm-rag.md), the
untrusted-content and outbound-message rules in [agent runtime](agent-runtime.md), the
business-outcome layer in [evaluation](evaluation.md) and the cadence in
[operations](operations.md) come from the owner's course study decks (Agent Production
Blueprint and a lead-generation job analysis). Those decks drew on the course plus:
Anthropic, "Building effective agents" (2024), for the workflow patterns and autonomy
guidance; Yao et al., "ReAct" (2022); Simon Willison's "lethal trifecta" (2025); Meta's
"Agents Rule of Two" (2025); and the OWASP Top 10 for LLM Applications (2025). These were
not re-fetched for this update; check current versions before citing them in a project.
Product and vendor names in the decks are a dated snapshot and are not kit defaults.

The three final projects supply end-to-end acceptance examples. Their fixed counts,
frameworks, models, regions and numerical thresholds are grading criteria, not kit defaults.

## Qualifications applied

- The in-process Python/AST/thread exercise is a learning example. Thread timeouts do not
  terminate running functions. See [Python futures](https://docs.python.org/3/library/concurrent.futures.html)
  (checked 2026-10-11). Runtime guidance requires an independently enforced execution boundary.
- A stored checkpoint supports reconstruction; external actions and non-deterministic calls
  need replay-aware handling. See [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
  and the [official functional API source](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/functional-api.mdx)
  (checked 2026-10-11). Reconstruction and re-execution are distinct.
- A namespaced thread key does not establish authentication or ownership enforcement.
  The adaptation requires trusted identity and direct cross-user access tests.
- The course's unauthenticated MCP service stays a development example. Use the selected
  protocol's [security guidance](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices)
  for remote access (checked 2026-10-11).
- The adaptation records observable actions and sanitized metadata instead of demanding
  internal monologues or logging full prompts by default.
- Judge scores, drift signals, SHAP explanations and small A/B experiments are evidence
  with limitations, not automatic guarantees of correctness, fairness or improvement.
- A corpus swap must account for in-flight requests, deletion and cache invalidation.
  A model-registry score must be tied to the same artifact being promoted.
- Existing project authorization and technical baseline take precedence over classroom
  approval examples. No course step grants permission for spending, outreach or deployment.

Use current installed source/official documentation before implementing any framework API.
