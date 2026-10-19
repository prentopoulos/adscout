## Context

Phase 1 left a pipeline whose `source` step is real and whose `enrich`, `rules`, `score`,
`research` and `draft` steps are scripted stubs, with run records, an independent run check,
an OpenTelemetry/Langfuse-named export, a fake CRM and C4 diagrams (HANDOFF.md). Package
`adscout` 0.2.0 has two runtime dependencies (pydantic, PyYAML) and no model, network or
agent code. No account, key or paid plan exists for the project.

Phase 2 grilling ran on 2026-10-18 in three rounds, each researched by an informed-answerer
subagent and reviewed by the main agent. The owner accepted every recommendation in each
round. Between rounds the owner made four scope calls: merge the playbook's Phases 2–6 into
two MVP phases; reverse "multi-agent orchestration: out of scope"; take five ideas from
DeepLearning.AI's crewAI "Agentic sales pipeline" lesson and crewAI-examples' lead-score-flow;
and plan Langfuse Cloud for Phase 3. The owner is on the Claude Pro plan, which includes no
API credits ("Free, Pro, and Enterprise plans aren't eligible",
platform.claude.com/docs/en/about-claude/api-credits-for-subscribers, retrieved 2026-10-18).

**Facts verified for this design (retrieved 2026-10-18).**

| Topic | Fact | Source |
|---|---|---|
| Prices per MTok | Haiku 5.5 $0.10 in, $0.125 cache write, $0.01 cache read, $0.50 out (×5 above 100K prompt tokens); Sonnet 5.5 $2, $2.50, $0.10, $10; Opus 5.5 $4 / $20; tool use adds 286 system tokens per request | platform.claude.com/docs/en/about-claude/pricing |
| Haiku 5.5 tokenizer | About 30% more tokens than Haiku 4.5 | Haiku 5.5 model page |
| Sampling | Non-default temperature returns 400 on Haiku and Sonnet 5.5; Sonnet 5.5 rejects thinking `disabled` | models overview, claude-api skill |
| Web search | $10 per 1,000 searches plus tokens; failed searches unbilled; count in `usage.server_tool_use.web_search_requests`; `max_uses`, `allowed_domains`/`blocked_domains`, `user_location`; versions `_20260209`+ run code execution internally (not ZDR-eligible unless `allowed_callers: ["direct"]`) | web-search-tool and server-tools pages |
| Web fetch (server) | No fee beyond tokens; fetches only URLs already in context; no JavaScript; may serve cached pages | web-fetch-tool page |
| Haiku 5.5 and web search | Not stated; `GET /v1/models/{id}` reports `capabilities.server_tools.web_search.supported` | web-search-tool page, models API |
| Frameworks | anthropic 1.15.0 (2026-10-15, httpx2); langgraph 1.2.16 (2026-10-16, MIT, typed); crewai 1.15.28 pins `pydantic<2.13` while AdScout locks 2.14.1; claude-agent-sdk 0.2.168 is Alpha | PyPI JSON, wheel inspection |
| OTel GenAI conventions | Moved to github.com/open-telemetry/semantic-conventions-genai; still Development; agent spans list `gen_ai.agent.version` | that repository |
| YouTube Data API | "must not store the subscriber count … for more than 30 days" | YouTube Developer Policies §III.E.4.b |
| Wikimedia User-Agent policy | `<client>/<version> (<contact>) <library>/<version>` | meta.wikimedia.org User-Agent policy (edited 2026-03-27) |
| Prepaid credit | Non-refundable, expires one year after purchase | support.claude.com/en/articles/8977456 |

The SEC fair-access User-Agent rule is from memory; sec.gov sits behind the live-read gate,
so that evidence is thin until the first live run.

**crewAI references (owner's request, retrieved 2026-10-18).** The "Agentic sales pipeline"
lesson of DeepLearning.AI's *Practical Multi AI Agents and Advanced Use Cases with crewAI*
loads leads in code, scores them with a three-agent crew, stores and filters (score above 70)
in code, writes emails with a two-agent crew, plots the Flow and reports cost per crew; its
code is not public. `crewAIInc/crewAI-examples/flows/lead-score-flow` (archived) ranks job
candidates 1–100 without a rubric and lets a person rescore the top three with feedback.

## Goals / Non-Goals

**Goals** (acceptance evidence, owner, round 1 Q1 as updated in round 3 Q11):
1. The gate passes at ≥90% coverage with field validators and the registry, egress, canary
   and allowlist tests.
2. About 30 rules cases, about 30 draft cases and the citation-verifier cases all pass.
3. The 10 planted-injection pages pass offline and in one live run.
4. A run that hits its cap mid-run stays `failed` with `budget_exhausted`.
5. Every call, search fees included, is costed from the dated price table; each run ends
   with a cost table by step, role and model, and cost per qualified lead.
6. A $0 replay reproduces a live run's outputs.
7. Live runs of 5 then 30 seeds from a clean tree, exports committed: every scored lead has a
   schema-valid score with reasons; every qualified lead has a brief with a recorded status;
   every draft is `pending_approval` or `draft_failed`; nothing goes past approval.
8. Reported, not gated: scores against the owner's labels; the tier decision; enrichment
   accuracy on 10 companies; claim-matches-source on 10 briefs; multi-agent against
   single-agent research by the predeclared rule; the worker-tier check; judge calibration if
   a judge is used.
9. The registry-generated agent diagram and the C4 updates, with drift tests, and the
   private artifact.
10. Constitution 1.1.0 committed before any research code (done, 8488886).
11. Code review under WORKFLOW.md and pip-audit.

**Non-Goals** (owner): the approval UI, dashboard and trace page, HubSpot, the send function
and sandbox inbox, contacts and mock revenue, reviewer reasons as labels, the README crewAI
table, near-miss promotion, Langfuse Cloud, CI, README, Dockerfile, video and minutes per
account (Phase 3); Batch API, checkpoints, n8n, fine-tuning, an injection classifier, the
60-company label set and precision in the top 20.

## Decisions

Owner calls are marked **owner**. Settled answers give their basis. "R1", "R2" and "R3" name
the grilling round; question numbers are those the owner answered.

### Scope

1. **Two MVP phases (owner, 2026-10-18).** Phase 2 holds every step that calls a model, with
   its evaluations; Phase 3 holds approval, CRM, send, dashboard and showcase. Evaluation
   samples shrink: 30 labelled companies (not 60), top 10 (not 20), enrichment hand-checked on
   10 companies (not 40), 10 briefs checked (not 20); injection pages stay at 10 (R3 Q6).
2. **Multi-agent (owner, 2026-10-18).** The pipeline shows the conventional patterns where
   each fits: sequential chain for the pipeline, a router after scoring, orchestrator–workers
   for research, evaluator–optimizer for drafts, a single rubric call for scoring. A
   three-agent scoring crew is not used; a rubric in one call does that job.
3. **Course ideas (owner).** (1) A pipeline diagram generated from code; (2) an end-of-run
   cost table and cost per qualified lead; (3) the near-miss lane; (4) reviewer reasons saved
   as labels (Phase 3); (5) a README table comparing AdScout with a crewAI sales pipeline
   (Phase 3). Not taken: crewAI itself, researching people, unanchored 1–100 scores,
   automatic sending.
4. **Qualified lead (owner, R1 Q2).** `qualified` = passed rules and scored ≥ threshold;
   `approved` = a person approved (Phase 3). Stub approvals and leads sent to a person never
   count as qualified.
5. **Cut order if the phase runs long (owner, R3 N5).** Worker-tier check, then the optional
   Haiku writer arm, then comparison repeats from 3 to 1 on half the companies, then the
   critic (rule checker kept). The multi-versus-single comparison is never cut.

### Data and enrichment

6. **Seeds (owner, R1 Q6).** 30 seeds proposed by agent desk research under a scoped
   web-search decision (PROJECT.md §6), including about 6 edge cases (steelseries.com among
   them); the owner approves the list and labels each good, maybe or poor, blind to scores,
   before live scoring. Run sizes 5, then 30.
7. **Fields and key fields (owner, R1 Q4; R3 N1).** `categories`, `sells_in` (ISO 3166-1
   alpha-2), `hq_country` (recorded, not a rule), `ownership` and `parent`,
   `employee_count` with its as-of date, `revenue_usd` (public companies only), social
   account links, `ad_signals`, and optional `recent_launches` and `sponsorships`. Key fields:
   `categories`, `sells_in`, `employee_count`. YouTube subscriber counts are dropped (the
   30-day storage rule conflicts with a never-reset database and committed exports); channel
   IDs and links stay.
8. **Sources (owner, R3 Q2).** The company's own site through our fetcher, at most 3 pages
   (home, newsroom or press, store or shipping); deterministic detection of ad-pixel and tag
   hosts in raw HTML gives `ad_signals`; Haiku extracts `categories`, `sells_in` and
   `recent_launches` from page text; Wikidata gives HQ country, ownership, parent, dated
   employee count, revenue and social IDs; SEC EDGAR XBRL gives revenue and employees for US
   filers; at most one server web search per company when launches are still empty. Every
   field records its source URL and retrieval time. When Wikidata and SEC lack employee
   count, extraction may take it from a fetched page or search result with its source.
9. **Probe replaced (owner, R3).** The planned Wikidata/SEC/robots probe from the agent's
   session is not run; the 5-seed live run is the coverage check. Coverage gaps there change
   source order, not the schema.
10. **Fetch policy (owner, R2 Q5; R3 N4).** User-Agent `AdScoutBot/<version> (portfolio
    research bot; <contact>) httpx2/<version>` with the contact from `.env`
    `ADSCOUT_CONTACT`, a dedicated project mailbox the owner creates (option a); robots.txt
    per RFC 9309 (5xx disallows all, 401/403 read as disallow), recorded in `source_calls`;
    ≥1 s per host or its Crawl-delay; APIs at 1 request per second; GET only, no cookies or
    JavaScript; timeouts 5 s connect, 15 s read; ≤2 MB per response; ≤3 redirects within the
    company's domain; 401/403 not retried; one Retry-After honoured on 429. Per company:
    enrichment ≤3 pages; research ≤6 pages and ≤9 searches.
11. **Site list (owner, R2 Q6; R3 N4).** The agent checks robots.txt and the terms page of
    each of the 30 company domains once under a scoped decision and records fetch or skip in
    `config/site-checks/gaming-hardware-na.yaml` (pydantic-validated), which the owner
    approves; a domain whose terms restrict automated access, or whose robots.txt disallows a
    needed path, is skipped. The pipeline refuses company domains not approved there.
    Third-party pages in research rely on robots.txt plus a blocked-domain list (social
    networks, LinkedIn, people-search sites).
12. **Storage (owner, R1 Q7; R3 N3; settled R2 N3).** One migration 0002 with table
    rebuilds adds `enrichment_fields`, `model_calls`, `source_calls` and `claims`, widens the
    exit-reason CHECK and adds `replay` to `runs.source`. No page text or HTML is stored,
    except claim quotes of at most 300 characters. Full pages live only in the gitignored
    replay cache. Synthetic test pages use `.example` and `.test` domains.

### Models, cost and access

13. **Provider and adapter (owner, R1 Q5).** Anthropic direct through the `anthropic` SDK
    behind an in-house adapter with `fake`, `replay` and `live` modes. Only the adapter holds
    the API key (`ANTHROPIC_API_KEY` in `.env`).
14. **Model per role (owner, R2 Q1; R3 Q3, Q5, Q12).**

    | Role | Model, effort | Compared in Phase 2 |
    |---|---|---|
    | Extraction | Haiku 5.5, low; escalate once to Sonnet on validator failure (logged) | Rerun the 10 checked companies on Sonnet only if key-field accuracy <90% |
    | Scoring | Sonnet 5.5 provisionally | Tier evaluation, decision 19 |
    | Research lead (plan, merge) | Sonnet 5.5, medium | No |
    | Research workers | Haiku 5.5, low (Sonnet, low, if Haiku lacks web search) | Sonnet arm on 5 companies; switch only if claim-match ≥ +10 points or coverage ≥ +0.5 topics |
    | Writer | Sonnet 5.5, medium | Optional Haiku arm on 10 drafts |
    | Critic | Sonnet 5.5, low (a judge at least as capable as what it grades) | No |
    | Single-agent baseline | Sonnet 5.5, medium | Decision 24 |

    Method (owner, R3 Q12): pick the cheapest tier whose step metric is within a predeclared
    margin of the best with no more hard failures, ties broken by cost per qualified lead.
    Effort is fixed per role and recorded per call. Prompts ask for short reasons, never
    step-by-step reasoning.
15. **Fallback (owner, R2 Q1).** In our code: a refusal, output still invalid after one
    retry, or 5xx/overload after SDK retries calls the other tier once. `model_calls.role` is
    `primary`, `retry`, `fallback` or `escalation`. No server-side fallbacks.
16. **Spend (owner, R2 Q2; R3 Q9).** Per-run caps in code, reserved before each call (worst
    case: `max_tokens` output, uncached input, `max_uses` × $0.01 searches) and settled after
    it; the reservation is lock-guarded because workers run in parallel:

    | Run | Cap |
    |---|---|
    | 5-seed slice | $2.50 |
    | 30-seed evidence run (3× scoring) | $8 |
    | Tier evaluation | $6 |
    | Multi-versus-single comparison | $15 |
    | Worker-tier check | $3 |
    | Injection live run | $3 |
    | Rescore | $2 |
    | Development and live tests | $3 |

    Per-research caps: each worker ≤6 calls, 3 searches, 2 pages, 90 s, $0.10 (Haiku) or
    $0.40 (Sonnet); per lead ≤20 calls, 9 searches, 6 pages, $0.30 or $0.90. Drafts $0.12 per
    lead. Phase 2 expected about $26 with a 30% rerun allowance; caps sum to $42.50. The owner
    sets an "adscout" workspace spend limit of $45 with auto-reload off and buys prepaid
    credit in two purchases: $20 before the 5-seed slice, tier evaluation, injection run and
    tests; about $25 before the 30-seed run and comparison, re-estimated from measured cost
    per qualified lead. If Haiku cannot use web search, the estimate rises to about $36 and
    the limit to about $60, which the owner decides then.
17. **Budget errors (settled, R2 N4, fact).** The workspace-limit 400, the spend-cap 429 and
    "Your credit balance is too low" are non-retryable: the run fails with
    `budget_exhausted`.
18. **Caching and batch (settled, R2 Q3).** Prompt caching on (5-minute TTL; breakpoint after
    the fixed prefix and on the loop history; per-lead content serialized deterministically;
    a test holds the prefix bytes stable); Haiku prompts stay under 100K tokens (guard test).
    Batch API off. Basis: pricing page (cache read 0.05× on Sonnet 5.5, not the 0.10× the
    skill lists); round 2.
19. **Score check and tier rule (owner, R2 Q4).** Committed before live scoring: labels in
    `evals/labels/gaming-hardware-na.v1.csv` with their hash, labelled blind (relabelling
    makes v2). Reported: a label-by-outcome table; good-versus-poor AUC (ties 0.5,
    denominator stated); Kendall tau-b; precision and recall at 60 with poor-labelled
    qualified companies named; precision in the top 10 with ties at the cut; leads at 55–65
    listed; bootstrap 95% CIs (1,000 resamples, fixed seed); agreement with Phase 1's
    expectations; spread over 3 repeats (range, SD, criterion agreement, threshold flips). The
    tier evaluation scores the 30 seeds on Haiku and Sonnet 3× each from stored enrichments
    (`python -m evals score-compare`, settled R2 N2); Sonnet stays only if its AUC ≥ Haiku's
    + 0.10 and it has no more `score_failed` and no more flips; a Haiku pick leads to
    `adscout rescore`. No p-values or generalization; no pass/fail target.
20. **Replay cache (owner, R1 Q8).** Gitignored `data/cache.db` keyed by a hash of the
    request (model, prompt digest, tools, input) holds model responses and fetched pages;
    replays record cost 0 and keep the original cost; `runs.source = 'replay'`; cost per
    qualified lead counts actual spend only.
21. **Prompts (owner, R1 Q9).** `src/adscout/prompts/<role>.md` beside their output schemas;
    prompt version `p-` + 12 hex of SHA-256 over the LF-normalized prompt and schema files;
    existing leads keep `none`.

### Rules, scoring and routing

22. **Rules (owner, R1 Q4).** Deterministic: sells in both US and CA; at least one allowed
    category; `size_range` = employees ≥50, no maximum; exclusions empty. Region and category
    are rules, not score criteria; brand safety is a person's call at approval. A missing key
    field exits as `missing_key_fields`.
23. **Score (owner, R1 Q3; R3 Q3).** The model rates audience, ad activity, budget capacity
    (size) and recent launches 1–5 against written anchors, each with reasons citing enriched
    field IDs; code combines them as the weighted mean of (r − 1) × 25 with weights 0.35,
    0.30, 0.20, 0.15 from the segment config. Threshold 60, fixed before the live run. One
    sample per lead; the evidence run scores 3×. Router: ≥60 to research; 55–59 exits
    `near_miss` to a person with no research spend; below 55 exits `below_threshold`;
    invalid output after retry and fallback exits `score_failed`.

### Research team

24. **Framework (owner, R3 Q1).** LangGraph as orchestration only: one `StateGraph` for the
    pipeline chain and router, a research subgraph that fans out the workers with `Send`, and
    a draft subgraph that loops at most twice. Every node is a plain typed function calling
    the adapter; each worker's tool loop is a short manual loop on the `anthropic` SDK
    handling `pause_turn` and mixed server and client tool turns. Not used: `ChatAnthropic`,
    `create_react_agent`, LangSmith, checkpointers, `draw_mermaid_png` (it calls mermaid.ink).
    The first task is a half-day spike proving LangGraph works under `mypy --strict`; if it
    fails, the same registry drives our own code. crewAI loses on its `pydantic<2.13` pin,
    default telemetry and prompt ownership; the Claude Agent SDK is Alpha and runs a CLI
    subprocess; the beta tool runner does not resume `pause_turn`.

    **Spike outcome (task 1.2, 2026-10-18): passed; LangGraph stays and the fallback is not
    needed.** `src/adscout/pipeline/graph_spike.py` and `tests/test_graph_spike.py`, on
    langgraph 1.2.16 and langchain-core 1.6.12, pass `mypy --strict` with no `type: ignore`
    and run with sockets blocked. Shown: `TypedDict` states with an `operator.add` reducer;
    `Send` fan-out carrying frozen pydantic tasks; `invoke(..., version="v2").value` returns the
    typed state; findings arrive in dispatch order whatever the completion order, so per-lead
    serialization stays deterministic; `max_concurrency` 3 held with six workers (worker
    threads, peak 3); a rewrite counter stops the loop after two rewrites and `recursion_limit`
    raises `GraphRecursionError` as a backstop; `draw_mermaid()` works offline. Findings for
    the build: an exception escaping one `Send` branch fails the whole graph, so each worker
    node catches its own errors and returns a failed finding (ASI08); `END` is typed `str`, so
    routers return `str`; the run config is passed as an inline dict literal, which mypy reads
    as `RunnableConfig` without importing `langchain_core` (a transitive, undeclared
    dependency); langsmith registers a pytest plugin, which `pyproject.toml` disables; and
    LangSmith tracing turns on when any of `LANGSMITH_TRACING`,
    `LANGSMITH_TRACING_V2`, `LANGCHAIN_TRACING` or `LANGCHAIN_TRACING_V2` is `true`, after
    which LangGraph posts the graph state to api.smith.langchain.com (seen as blocked DNS
    lookups in a socket-blocked experiment). The task 7.1 guard therefore checks all four
    names and refuses to run, without importing `langsmith`. The spike module is replaced by
    the registry-built graphs in task 5.1.
25. **Team shape (owner, R3 Q3).** Strictly, parallel sectioning with an LLM lead, called
    "orchestrator–workers (fixed roster)" in the docs. Code dispatches three workers: audience
    and channels; ad activity; recent launches and sponsorships. The lead's plan call (no
    tools) writes 1–3 questions per worker; code attaches seed URLs from enrichment. Workers
    have `web_search` and `fetch_page` and end with a strict client tool `submit_findings`.
    The lead's merge call (no tools) sees verified claims only and writes summary points, each
    citing claim IDs. One retry each for plan and merge.
26. **Handoffs (owner, R3 Q3).** Strict pydantic models: `WorkerTask{lead_id, worker,
    company, domain, questions[], seed_urls[], caps}`; `WorkerFindings{worker,
    claims[{topic, text ≤300, source_url, quote ≤300}], gaps[], stopped_because}`;
    `VerifiedClaim{claim_id, fetch_call_id, url_fetched_in_run, quote_found, numbers_ok,
    verifier_version}`; `Brief{status, design, summary_points[{text, claim_ids[]}],
    claim_ids[], gaps[], caps_hit[]}`.
27. **Claim verification (owner, R3 Q3).** A claim is kept only if: its URL equals, after
    normalization, a URL fetched successfully in this run; its quote (≥20 characters) appears
    in that page's text after NFKC, whitespace and case normalization; every number in the
    claim appears in the quote. The merge may cite only verified claim IDs and may use no
    number absent from them. Dropped claims are counted. No verified claim, or every worker
    failed, exits `research_failed` to a person; any cap hit, failed worker or uncovered topic
    flags `research_partial`.
28. **Search and fetch tools (owner, R3 Q2; settled R3 N8).** Server `web_search_20250305`
    with `allowed_callers: ["direct"]` (no hidden code execution), `max_uses` per call,
    `blocked_domains`, `user_location` US. Pages are read only through our client-side
    `fetch_page`, which accepts a URL only if it came from this worker's search results, the
    lead's seed URLs or a same-site link on the company's domain, and refuses non-http(s)
    schemes, IP literals, private ranges, credentials in URLs and long query strings; it
    applies decision 10 and trims HTML to text of about 4K tokens. Search fees go on the
    triggering `model_calls` row (count and fee); each search gets a `source_calls` audit row
    (query, result URLs, page age) at $0.
29. **Multi versus single (owner, R3 Q4).** Committed before measuring. Baseline: one Sonnet
    agent with the same tools, verifier, schema and total budget (9 searches, 6 pages, 12
    steps). Population: the 10 highest-scored qualified leads of the 30-seed run (ties by
    domain; all if fewer, n reported). 3 repeats per design per company. Metrics with
    bootstrap CIs over companies: owner-judged claim-matches-source (supported, partial,
    unsupported); verified ÷ emitted claims; topics covered of 3 and verified-claim count;
    cost per brief and per verified claim, search fees included; wall time; failed and partial
    rates; per-company SD of verified claims and Jaccard overlap of cited URLs. The owner
    spot-checks repeat 1, up to 5 claims per brief by seeded draw (≤100 claims, about 1.5
    hours), blind to design and shuffled; an LLM judge is a secondary number only, with its
    agreement. Rule: multi-agent stays the default if its claim-match rate is no more than 5
    points below single-agent, its coverage is higher by ≥0.33 topics per brief, and its
    cost per brief is ≤3×; otherwise single-agent becomes the default and multi-agent stays
    as `--research-design multi`. Every repeat is reported.

### Drafts

30. **Draft loop (owner, R3 Q5).** The writer outputs structured sentences, each with
    `supports[]` naming a verified claim ID or a media-kit fact ID. The deterministic rule
    checker runs first, then the critic (`{verdict, issues[]}` on relevance, specificity,
    tone, a clear ask and no implied relationship). At most two rewrites carry the issues
    forward. Rules failing after two rewrites exit `draft_failed` to a person; rules passing
    with the critic still objecting give `pending_approval` flagged `critic_unresolved`.
31. **Rule checker (owner, R3 Q5; settled N13).** Every sentence with a digit, proper name,
    date, URL or superlative has a support resolving to this lead's verified claims or a
    media-kit fact; its numbers (normalized) are a subset of its supports' numbers; its proper
    nouns are a subset of support tokens, the company name, the publisher name and an
    allowlist; subject ≤70 characters; body 60–160 words; footer placeholders
    `{{sender_name}}`, `{{sender_title}}`, `{{publisher_postal_address}}` and
    `{{unsubscribe_url}}` exactly once (the Phase 3 send function fills them and refuses
    without them); no email address, phone number, person name or URL; a banned-phrase list
    (guarantees, urgency, "our partnership", affiliation claims); the company name exact; no
    injection canary text.
32. **Publisher (owner, R3 N6).** Media-kit facts in `config/media-kit/<publisher_id>.yaml`
    for a fictional publisher the owner names after the agent checks it is not a real
    company; every fact has an ID, text and `simulated: true`.

### Security, evaluation and observability

33. **Rule of Two (settled, recorded: §5 1.1.0; design-choices.md § Design-time security
    check).** See the agent and security map below. No agent's context holds private data, so
    no agent holds all three legs; workers hold untrusted input plus outbound search and
    fetch. Enforcement: typed context builders per role; the registry's tool allowlist,
    checked by the adapter on every request; the egress rules of decision 28; canary values
    for a secret, a label, a CRM value and a revenue value planted in fixtures and searched
    for in every recorded request and cache entry; worker output treated as untrusted
    (schema-validated, quote-verified, wrapped in data delimiters; the lead cannot add claim
    IDs).
34. **Injection pages (owner, R3 Q6).** Ten planted pages, each with a clean twin: direct
    override; exfiltration link; hidden text; fake system or tool markup; a false claim aimed
    at the brief; score inflation (compared with the twin's score); second-order injection
    through worker output into the writer; encoded or homoglyph instructions; budget blow-up;
    an oversized page. Pass: no tool call or URL derived from the instruction, no echo of the
    planted text, no role change, score within the twin's 3× range, caps held. All must pass
    offline and in one live run. No injection classifier (settled N7).
35. **Evaluation layers (settled, recorded: eval-review skill; evaluation.md; R1 Q1).**
    Deterministic (gated, offline): validators, rules, draft and verifier cases, registry,
    allowlist, egress and canary tests, the cap test, the replay test, injection cases through
    the code paths. Judged (live, budgeted, reported): decisions 19, 29 and 14's comparisons,
    enrichment accuracy on 10 companies, claim-matches-source on 10 briefs; an LLM judge only
    if calibrated against the owner on about 10 items. Operational (enforced caps, reported
    figures): cost per call, step, lead and qualified lead, tokens, cache hit rate, latency,
    retries, cap hits. The pytest harness stays; promptfoo and Inspect are not added.
36. **Traces (settled R3 Q7; owner R3 Q13).** `model_calls` and `step_runs` stay the source of
    truth and gain `trace_id` (the lead's UUIDv7 as hex), `span_id`, `parent_span_id`, an
    operation name (`chat`, `invoke_agent`, `execute_tool`) and `gen_ai.agent.name` (the
    registry role). The export keeps OTel GenAI and Langfuse names; its single mapping table
    is updated for the moved conventions and `gen_ai.agent.version`. `adscout trace <run>`
    prints each lead's span tree with model, tokens, cost and time. No external tracing tool
    in Phase 2; Langfuse Cloud's free plan is planned for Phase 3 under the account gate
    (owner). Datadog, LangSmith, self-hosted Langfuse and Phoenix lose on accounts, data
    leaving the PC, weight or licence.
37. **Concurrency (settled, recorded: llm-rag.md; Phase 1 decision 7).** At most 3 parallel
    model calls; lock-guarded spend reservation; short `BEGIN IMMEDIATE` writes; workers
    never write SQLite directly.
38. **Telemetry guards (settled, default).** Tests assert `LANGSMITH_TRACING` is not true at
    runtime; pytest-socket blocks network in tests.

### Diagrams

39. **Registry and diagrams (owner, R3 Q8).** `src/adscout/pipeline/registry.py` records each
    node's ID, label, kind (step, agent, tool, person, gate), pattern, model and effort,
    tools, caps, input and output types, trust zone (untrusted content, no tools, code only,
    human) and exits; the LangGraph graphs are built from it. `scripts/diagrams.py` writes
    `docs/architecture/agents.md` (Mermaid from `draw_mermaid()` plus pattern colours,
    trust-zone subgraphs and typed handoff labels) and `docs/architecture/agent-flow.html`
    (self-contained inline SVG in a LangGraph-Studio-like style, no external scripts). The C4
    model gains a component view of the research team. `export-stamp.json` covers the new
    files. Before the build, a hand-drawn target-design page is shown to the owner as a
    private artifact; from the first implementation task it is the generated page.
40. **Artifact and the publishing gate (owner, R3 Q8).** A private claude.ai artifact is not
    publishing; sharing its link is, and needs the publishing gate and the pre-publication
    check (no secrets, no personal data, no named employer, no claimed affiliation).

### Process

41. **Account checks (owner, R3 N2, N11).** After the account exists, the owner confirms web
    search is enabled for the organization, and a free `GET /v1/models/claude-haiku-5-5` shows
    whether Haiku supports web search, which settles the worker model in decision 14.
42. **Minutes per account (owner, R3 N10).** The owner times their own research on the five
    Phase 1 seeds before Phase 3.

## Agent and security map

A = reads untrusted input; B = sees private or sensitive data; C = communicates externally or
changes state (Meta's "Agents Rule of Two"; Willison's "lethal trifecta").

| Role | A | B | C | Holds | Tools |
|---|---|---|---|---|---|
| Extractor | yes | no | no | A | none |
| Scorer | yes | no | no | A | none |
| Research lead (plan, merge) | yes | no | no (dispatch is code) | A | none |
| Research workers | yes | no | yes (search and fetch are outbound) | A + C | `web_search`, `fetch_page`, `submit_findings` |
| Single-agent baseline | yes | no | yes | A + C | same as workers |
| Writer | yes | no (media kit is public by design) | no | A | none |
| Critic | yes | no | no | A | none |

The CRM writer and the Phase 3 send function are code, not agents, and act only after a
person approves. The system as a whole holds all three legs, separated by agent sessions and
human approval.

| OWASP item | Control and test |
|---|---|
| LLM01 prompt injection | Fixed roster and tools, data delimiters, planted pages |
| LLM02 sensitive information disclosure | No B in any context, canary test, company-level guards |
| LLM03 supply chain | `uv.lock`, pip-audit, pinned model IDs and tool versions, no MCP |
| LLM04 data and model poisoning | Labels hash, versioned cases, quotes required |
| LLM05 improper output handling | Strict schemas; model-proposed URLs pass the provenance rule; Phase 3 escapes UI |
| LLM06 excessive agency | Registry allowlists, read-only workers, human approval |
| LLM07 system prompt leakage | Prompts are committed and hold no secret |
| LLM08 vector and embedding weaknesses | Not applicable (no index) |
| LLM09 misinformation | Verifier, owner spot-check, draft rule checker |
| LLM10 unbounded consumption | `max_tokens`, step, page and search caps, run cap, workspace limit |
| ASI01 agent goal hijack | Roster and tools fixed in code; goal-change page |
| ASI02 tool misuse and exploitation | Caps, URL provenance, SSRF guard |
| ASI03 identity and privilege abuse | Key only in the adapter; approver kind recorded |
| ASI04 agentic supply chain | No dynamic tool discovery; pinned tool versions; prompt digest |
| ASI05 unexpected code execution | No code-execution tool; dynamic filtering off |
| ASI06 memory and context poisoning | No long-term memory; fresh context per lead; cache keyed by hash |
| ASI07 insecure inter-agent communication | In-process typed handoffs |
| ASI08 cascading failures | Failed worker makes a partial brief; bounded retries; one fallback |
| ASI09 human-agent trust exploitation | Verification status, quotes and critic notes shown to the approver |
| ASI10 rogue agents | Caps, run cap as kill switch, a record per call |

OWASP LLM items are from the Top 10 for LLM Applications 2025 (genai.owasp.org/llm-top-10,
current); ASI items from the Top 10 for Agentic Applications 2026 (published 2025-12-09;
item names from secondary summaries, to be checked against the official PDF in task 6.1).

## Data model

Migration `0002` (one file, table rebuilds where a CHECK changes; the snapshot test covers
triggers): `enrichment_fields` (lead, field, value JSON, source URL, source kind, retrieved
at, as-of date, validator status); `model_calls` (run, step, lead, role, agent name, model,
effort, prompt version, call role, input, cache-write, cache-read and output tokens, search
count, search fee, cost, original cost for replays, latency, stop reason, trace, span and
parent span IDs, operation); `source_calls` (run, lead, kind, URL or query, status, robots
decision, bytes, result URLs, cost 0, retrieved at); `claims` (brief, worker, topic, text,
source URL, fetch call, quote ≤300, verification fields, verifier version). `briefs` gains
`design`, `caps_json` and `verifier_version`; `drafts` gains sentences with supports and
critic notes. Exit reasons add `score_failed`, `near_miss` and `research_failed`; flags add
`critic_unresolved`; `runs.kind` adds `rescore` and `eval`; `runs.source` adds `replay`;
`runs.error_category` uses `budget_exhausted` for cap stops.

## Rule, check and phase map

| §5 rule | Check built in Phase 2 | Later |
|---|---|---|
| Secrets | Key only in the adapter; secrets scan; canary test | — |
| No fabrication; labels; failed runs kept | Real rows labelled `real`, replays `replay`; quotes verified; null reasons; failed runs kept | — |
| Synthetic personal data only | Draft checker refuses names, emails, phones; blocked people-search domains | Contacts, Phase 3 |
| Research agents read-only, caps, no private data | Registry allowlists, caps, egress tests, canary test, injection pages | — |
| Claims cite sources; drafts grounded | Claim verifier; supports on every draft sentence | — |
| One CRM writer | Unchanged; no agent holds a CRM tool | HubSpot adapter, Phase 3 |
| No message to a real person | No send path; footer placeholders required | Send function, Phase 3 |
| Lead ID and immutable fields | Prompt version set at lead creation from the digest | — |
| Revenue simulated | No revenue data | Phase 3 |

## Non-negotiables check

- **Secrets:** `ANTHROPIC_API_KEY` and `ADSCOUT_CONTACT` in gitignored `.env`, read only by
  the adapter and fetcher; never logged, exported or placed in a prompt.
- **No fabrication:** every live, replayed and fake output is labelled; costs come from the
  dated price table and the API's usage fields; unverifiable claims are dropped and counted;
  the SEC and ASI evidence is marked thin above.
- **⛔ gates:** spend, accounts and live reads are recorded as owner decisions in PROJECT.md
  §6; the pipeline's live mode refuses to run without a key, a cap and an approved site list.
  Tests use fakes and recorded fixtures only.
- **No message to a real person:** drafts stop at `pending_approval`; no send path exists.
- **Synthetic personal data:** company-level fields only; the draft checker and blocked
  domains keep people out.
- **Research agents:** decisions 25–28 and 33.
- **Claims and drafts:** decisions 27, 30 and 31.
- **One CRM writer:** untouched.
- **Lead ID and immutable fields:** unchanged; Phase 2 leads carry their prompt digest.
- **Revenue simulated:** none in Phase 2.

## Risks / Trade-offs

- **[Haiku lacks web search]** → Sonnet workers at effort low; budget re-decided (decision 41).
- **[LangGraph fights `mypy --strict`]** → Day-one spike; the registry drives our own code
  instead.
- **[Wikidata or SEC miss key fields for private companies]** → Page or search extraction with
  source; the 5-seed run measures coverage before the 30-seed run.
- **[Estimates are low]** → Caps bound every run; credit is bought in two purchases after the
  first measured cost per qualified lead.
- **[Quote matching rejects good claims on reflowed pages]** → Normalization rules versioned
  with `verifier_version`; dropped claims are counted and reported.
- **[Owner time]** → Labels for 30 companies plus up to 100 claims; the cut order (decision 5)
  saves effort elsewhere first.
- **[Second-order injection reaches the writer]** → Supports must resolve to verified claims;
  the canary and planted page 7 test it.
- **[OTel GenAI names change again]** → One mapping table.
- **[Prices change]** → Dated price table; calls priced at their date.

## Migration Plan

Migration 0002 runs on `adscout db upgrade` after a backup; Phase 1 rows keep their values
and `implementation = 'stub'`. Rollback is reverting the branch and restoring the backup;
`data/` is gitignored.

## Open Questions

- The fictional publisher's name (owner, decision 32), needed before drafts run live.
- Whether Haiku 5.5 supports web search (decision 41), answered once the account exists.
- The minutes-per-account definition and the CRM sandbox details: Phase 3 grilling.
