-- 0002_ai_pipeline: the Phase 2 schema (Phase 2 design, "Data model").
-- Tables whose CHECK lists widen are rebuilt with SQLite's procedure: create the new table,
-- copy every row, drop the old one, rename. The runner turns foreign keys off for the
-- migration and runs `PRAGMA foreign_key_check` before it commits. Views are dropped first
-- and recreated last, because a rename refuses while a view names a missing table.
-- No fetched page text or HTML is stored here, except claim quotes of at most 300
-- characters; full pages live only in the gitignored replay cache (design decision 12).

DROP VIEW v_funnel;
DROP VIEW v_lead_journey;

-- Config snapshots gain the site list, media kit and price table a run used.
CREATE TABLE config_snapshots_new (
    content_hash TEXT PRIMARY KEY CHECK (length(content_hash) = 64),
    kind TEXT NOT NULL CHECK (kind IN (
        'segment', 'seed_list', 'stub_script', 'site_list', 'media_kit', 'price_table'
    )),
    segment_id TEXT NOT NULL,
    content_json TEXT NOT NULL CHECK (json_valid(content_json)),
    first_seen_at TEXT NOT NULL
) STRICT;
INSERT INTO config_snapshots_new SELECT * FROM config_snapshots;
DROP TABLE config_snapshots;
ALTER TABLE config_snapshots_new RENAME TO config_snapshots;

-- Runs gain the rescore and eval kinds, the replay source, the hashes of the new config
-- kinds, the run's options (research design, score repeats, spend cap) and its cost table.
CREATE TABLE runs_new (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('pipeline', 'approval', 'crm_sync', 'rescore', 'eval')),
    segment_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'interrupted')),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    error_category TEXT,
    error_detail TEXT,
    validation_outcome TEXT NOT NULL DEFAULT 'not_run'
        CHECK (validation_outcome IN ('pass', 'fail', 'not_run')),
    validation_detail TEXT,
    source TEXT NOT NULL CHECK (source IN ('stub', 'fixture', 'replay', 'live')),
    code_revision TEXT NOT NULL,
    code_dirty INTEGER NOT NULL CHECK (code_dirty IN (0, 1)),
    lock_digest TEXT NOT NULL,
    package_version TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    python_version TEXT NOT NULL,
    platform TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    icp_config_hash TEXT REFERENCES config_snapshots (content_hash),
    seed_list_hash TEXT REFERENCES config_snapshots (content_hash),
    stub_script_hash TEXT REFERENCES config_snapshots (content_hash),
    budgets_json TEXT NOT NULL CHECK (json_valid(budgets_json)),
    null_reasons_json TEXT NOT NULL CHECK (json_valid(null_reasons_json)),
    pid INTEGER NOT NULL,
    host TEXT NOT NULL,
    site_list_hash TEXT REFERENCES config_snapshots (content_hash),
    media_kit_hash TEXT REFERENCES config_snapshots (content_hash),
    price_table_hash TEXT REFERENCES config_snapshots (content_hash),
    options_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(options_json)),
    cost_summary_json TEXT CHECK (cost_summary_json IS NULL OR json_valid(cost_summary_json)),
    CHECK ((status = 'running') = (ended_at IS NULL)),
    CHECK (status != 'failed' OR error_category IS NOT NULL)
) STRICT;
INSERT INTO runs_new (
    run_id, kind, segment_id, status, started_at, ended_at, error_category, error_detail,
    validation_outcome, validation_detail, source, code_revision, code_dirty, lock_digest,
    package_version, agent_version, prompt_version, python_version, platform, schema_version,
    icp_config_hash, seed_list_hash, stub_script_hash, budgets_json, null_reasons_json, pid, host
)
SELECT
    run_id, kind, segment_id, status, started_at, ended_at, error_category, error_detail,
    validation_outcome, validation_detail, source, code_revision, code_dirty, lock_digest,
    package_version, agent_version, prompt_version, python_version, platform, schema_version,
    icp_config_hash, seed_list_hash, stub_script_hash, budgets_json, null_reasons_json, pid, host
FROM runs;
DROP TABLE runs;
ALTER TABLE runs_new RENAME TO runs;

-- Outcomes gain the score_failed, near_miss and research_failed exits and the
-- critic_unresolved flag.
CREATE TABLE lead_step_outcomes_new (
    outcome_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    step TEXT NOT NULL,
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    seed_row INTEGER CHECK (seed_row >= 2),
    outcome TEXT NOT NULL CHECK (outcome IN ('kept', 'exited')),
    reason TEXT CHECK (reason IN (
        'duplicate', 'excluded', 'out_of_profile', 'missing_key_fields', 'score_failed',
        'near_miss', 'below_threshold', 'research_failed', 'draft_failed', 'rejected'
    )),
    flag TEXT CHECK (flag IN ('research_partial', 'critic_unresolved', 'crm_conflict')),
    detail TEXT NOT NULL,
    implementation TEXT NOT NULL CHECK (implementation IN ('stub', 'real')),
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    FOREIGN KEY (run_id, step) REFERENCES step_runs (run_id, step),
    CHECK ((outcome = 'exited') = (reason IS NOT NULL)),
    CHECK (outcome = 'kept' OR flag IS NULL)
) STRICT;
INSERT INTO lead_step_outcomes_new SELECT * FROM lead_step_outcomes;
DROP TABLE lead_step_outcomes;
ALTER TABLE lead_step_outcomes_new RENAME TO lead_step_outcomes;
CREATE INDEX lead_step_outcomes_by_lead ON lead_step_outcomes (lead_id, run_id);

-- Briefs gain a failed status, the research design, summary points citing claim IDs, gaps,
-- caps, the dropped-claim count and the verifier version. A stub brief keeps its claims in
-- claims_json (always empty); a real brief's claims live in `claims`.
CREATE TABLE briefs_new (
    brief_id INTEGER PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    implementation TEXT NOT NULL CHECK (implementation IN ('stub', 'real')),
    status TEXT NOT NULL CHECK (status IN ('complete', 'partial', 'failed')),
    summary TEXT NOT NULL,
    claims_json TEXT NOT NULL CHECK (json_valid(claims_json)),
    created_at TEXT NOT NULL,
    design TEXT CHECK (design IN ('multi', 'single')),
    summary_points_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(summary_points_json)),
    gaps_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(gaps_json)),
    caps_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(caps_json)),
    dropped_claims INTEGER NOT NULL DEFAULT 0 CHECK (dropped_claims >= 0),
    verifier_version TEXT,
    CHECK (implementation = 'stub' OR (
        design IS NOT NULL AND verifier_version IS NOT NULL AND claims_json = '[]'
    ))
) STRICT;
INSERT INTO briefs_new (
    brief_id, lead_id, run_id, implementation, status, summary, claims_json, created_at
)
SELECT brief_id, lead_id, run_id, implementation, status, summary, claims_json, created_at
FROM briefs;
DROP TABLE briefs;
ALTER TABLE briefs_new RENAME TO briefs;

-- Spans that are not calls: one per lead per step, and one per agent invocation. With the
-- call rows below they form each lead's trace; the trace ID is the lead ID as 32 hex digits.
-- Parent span IDs are not foreign keys, as in OpenTelemetry; `adscout check` verifies them.
CREATE TABLE spans (
    span_id TEXT PRIMARY KEY CHECK (length(span_id) = 16),
    trace_id TEXT NOT NULL CHECK (length(trace_id) = 32),
    parent_span_id TEXT CHECK (parent_span_id IS NULL OR length(parent_span_id) = 16),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    step TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('step', 'invoke_agent')),
    agent_name TEXT,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed')),
    detail TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    FOREIGN KEY (run_id, step) REFERENCES step_runs (run_id, step),
    CHECK ((operation = 'invoke_agent') = (agent_name IS NOT NULL)),
    CHECK ((operation = 'step') = (parent_span_id IS NULL))
) STRICT;

CREATE UNIQUE INDEX spans_one_step_span_per_lead ON spans (run_id, lead_id, step)
WHERE operation = 'step';

-- One row per model call, written once when the call ends (refused calls included), with
-- usage from the API's usage fields and cost from the dated price table.
CREATE TABLE model_calls (
    call_id TEXT PRIMARY KEY CHECK (length(call_id) = 36),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    step TEXT NOT NULL,
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    role TEXT NOT NULL CHECK (length(role) > 0),
    agent_name TEXT NOT NULL CHECK (length(agent_name) > 0),
    model TEXT NOT NULL,
    effort TEXT CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max')),
    prompt_version TEXT NOT NULL CHECK (prompt_version LIKE 'p-%'),
    call_role TEXT NOT NULL CHECK (call_role IN ('primary', 'retry', 'fallback', 'escalation')),
    mode TEXT NOT NULL CHECK (mode IN ('fake', 'replay', 'live')),
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'refused')),
    error_category TEXT,
    error_detail TEXT,
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
    input_tokens INTEGER CHECK (input_tokens >= 0),
    cache_write_tokens INTEGER CHECK (cache_write_tokens >= 0),
    cache_read_tokens INTEGER CHECK (cache_read_tokens >= 0),
    output_tokens INTEGER CHECK (output_tokens >= 0),
    web_search_requests INTEGER NOT NULL DEFAULT 0 CHECK (web_search_requests >= 0),
    search_fee_usd REAL NOT NULL DEFAULT 0 CHECK (search_fee_usd >= 0),
    cost_usd REAL NOT NULL CHECK (cost_usd >= 0),
    original_cost_usd REAL CHECK (original_cost_usd >= 0),
    reserved_usd REAL NOT NULL CHECK (reserved_usd >= 0),
    price_date TEXT,
    latency_ms INTEGER CHECK (latency_ms >= 0),
    stop_reason TEXT,
    trace_id TEXT NOT NULL CHECK (length(trace_id) = 32),
    span_id TEXT NOT NULL UNIQUE CHECK (length(span_id) = 16),
    parent_span_id TEXT NOT NULL CHECK (length(parent_span_id) = 16),
    operation TEXT NOT NULL DEFAULT 'chat' CHECK (operation = 'chat'),
    null_reasons_json TEXT NOT NULL CHECK (json_valid(null_reasons_json)),
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    FOREIGN KEY (run_id, step) REFERENCES step_runs (run_id, step),
    CHECK (status = 'succeeded' OR error_category IS NOT NULL),
    CHECK ((mode = 'replay') = (original_cost_usd IS NOT NULL)),
    CHECK (mode != 'replay' OR cost_usd = 0)
) STRICT;

CREATE INDEX model_calls_by_lead ON model_calls (lead_id, run_id);

-- One row per outside read (robots.txt, page, Wikidata, SEC EDGAR) and one audit row per
-- server web search; refusals by robots, the site list or the egress rules are rows too.
-- Search fees are charged on the model call that triggered the search, so these cost 0.
CREATE TABLE source_calls (
    call_id TEXT PRIMARY KEY CHECK (length(call_id) = 36),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    step TEXT NOT NULL,
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    kind TEXT NOT NULL CHECK (kind IN ('robots', 'page', 'wikidata', 'sec_edgar', 'web_search')),
    target TEXT NOT NULL CHECK (length(target) > 0),
    mode TEXT NOT NULL CHECK (mode IN ('fixture', 'replay', 'live')),
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'refused')),
    robots_decision TEXT CHECK (robots_decision IN ('allowed', 'disallowed')),
    http_status INTEGER CHECK (http_status BETWEEN 100 AND 599),
    bytes INTEGER CHECK (bytes >= 0),
    content_sha256 TEXT CHECK (content_sha256 IS NULL OR length(content_sha256) = 64),
    results_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(results_json)),
    model_call_id TEXT REFERENCES model_calls (call_id),
    detail TEXT NOT NULL,
    cost_usd REAL NOT NULL DEFAULT 0 CHECK (cost_usd = 0),
    latency_ms INTEGER CHECK (latency_ms >= 0),
    trace_id TEXT NOT NULL CHECK (length(trace_id) = 32),
    span_id TEXT NOT NULL UNIQUE CHECK (length(span_id) = 16),
    parent_span_id TEXT NOT NULL CHECK (length(parent_span_id) = 16),
    operation TEXT NOT NULL DEFAULT 'execute_tool' CHECK (operation = 'execute_tool'),
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    FOREIGN KEY (run_id, step) REFERENCES step_runs (run_id, step),
    CHECK (kind != 'web_search' OR model_call_id IS NOT NULL),
    CHECK (status != 'refused' OR http_status IS NULL)
) STRICT;

CREATE INDEX source_calls_by_lead ON source_calls (lead_id, run_id);

-- Each enriched field with its provenance; invalid values are kept as dropped, with the
-- validator's reason (design decisions 7, 8). No YouTube subscriber counts.
CREATE TABLE enrichment_fields (
    field_id INTEGER PRIMARY KEY,
    enrichment_id INTEGER NOT NULL REFERENCES enrichments (enrichment_id),
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    field TEXT NOT NULL CHECK (field IN (
        'categories', 'sells_in', 'hq_country', 'ownership', 'parent', 'employee_count',
        'revenue_usd', 'social_accounts', 'ad_signals', 'recent_launches', 'sponsorships'
    )),
    value_json TEXT NOT NULL CHECK (json_valid(value_json)),
    source_url TEXT NOT NULL CHECK (source_url LIKE 'http://%' OR source_url LIKE 'https://%'),
    source_kind TEXT NOT NULL CHECK (source_kind IN (
        'company_site', 'wikidata', 'sec_edgar', 'web_search'
    )),
    method TEXT NOT NULL CHECK (method IN ('parsed', 'extracted')),
    source_call_id TEXT REFERENCES source_calls (call_id),
    model_call_id TEXT REFERENCES model_calls (call_id),
    retrieved_at TEXT NOT NULL,
    as_of TEXT,
    status TEXT NOT NULL CHECK (status IN ('valid', 'dropped')),
    status_detail TEXT,
    created_at TEXT NOT NULL,
    CHECK (status = 'valid' OR status_detail IS NOT NULL),
    CHECK (method = 'parsed' OR model_call_id IS NOT NULL),
    CHECK (
        status = 'dropped' OR field NOT IN ('employee_count', 'revenue_usd') OR as_of IS NOT NULL
    )
) STRICT;

CREATE INDEX enrichment_fields_by_lead ON enrichment_fields (lead_id, run_id);

-- Every claim a research agent emitted, kept or dropped by the verifier (design decision 27).
-- claim_key is the ID the merge and the writer cite, unique within the brief. A claim that
-- names a person is kept only as a count: its text and quote are withheld (PROJECT.md §5).
CREATE TABLE claims (
    claim_id INTEGER PRIMARY KEY,
    brief_id INTEGER NOT NULL REFERENCES briefs (brief_id),
    claim_key TEXT NOT NULL CHECK (length(claim_key) BETWEEN 1 AND 16),
    agent_name TEXT NOT NULL CHECK (length(agent_name) > 0),
    topic TEXT NOT NULL CHECK (topic IN ('audience_channels', 'ad_activity', 'launches')),
    text TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 300),
    source_url TEXT NOT NULL,
    quote TEXT NOT NULL CHECK (length(quote) <= 300),
    fetch_call_id TEXT REFERENCES source_calls (call_id),
    url_fetched_in_run INTEGER NOT NULL CHECK (url_fetched_in_run IN (0, 1)),
    quote_found INTEGER NOT NULL CHECK (quote_found IN (0, 1)),
    numbers_ok INTEGER NOT NULL CHECK (numbers_ok IN (0, 1)),
    names_individual INTEGER NOT NULL DEFAULT 0 CHECK (names_individual IN (0, 1)),
    carries_link INTEGER NOT NULL DEFAULT 0 CHECK (carries_link IN (0, 1)),
    verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
    drop_reason TEXT,
    verifier_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (brief_id, claim_key),
    CHECK (
        verified = (
            url_fetched_in_run AND quote_found AND numbers_ok
            AND NOT names_individual AND NOT carries_link
        )
    ),
    CHECK ((verified = 1) = (drop_reason IS NULL)),
    CHECK (verified = 0 OR (fetch_call_id IS NOT NULL AND length(quote) >= 20)),
    CHECK (names_individual = 0 OR quote = '')
) STRICT;

-- Phase 2 drafts: structured sentences with supports, rule-check results, critic notes.
ALTER TABLE drafts ADD COLUMN sentences_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(sentences_json));
ALTER TABLE drafts ADD COLUMN checks_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(checks_json));
ALTER TABLE drafts ADD COLUMN critic_notes_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(critic_notes_json));
ALTER TABLE drafts ADD COLUMN publisher_id TEXT;
ALTER TABLE drafts ADD COLUMN brief_id INTEGER REFERENCES briefs (brief_id);

-- Phase 2 scores: per-criterion ratings with reasons, the repeat number and the call.
ALTER TABLE scores ADD COLUMN criteria_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(criteria_json));
ALTER TABLE scores ADD COLUMN sample INTEGER NOT NULL DEFAULT 1 CHECK (sample >= 1);
ALTER TABLE scores ADD COLUMN model_call_id TEXT REFERENCES model_calls (call_id);

-- Records of what models and outside sources returned are written once and never changed.
CREATE TRIGGER model_calls_append_only BEFORE UPDATE ON model_calls
BEGIN
    SELECT RAISE(ABORT, 'model_calls rows are append-only');
END;
CREATE TRIGGER model_calls_never_deleted BEFORE DELETE ON model_calls
BEGIN
    SELECT RAISE(ABORT, 'model_calls rows are append-only');
END;
CREATE TRIGGER source_calls_append_only BEFORE UPDATE ON source_calls
BEGIN
    SELECT RAISE(ABORT, 'source_calls rows are append-only');
END;
CREATE TRIGGER source_calls_never_deleted BEFORE DELETE ON source_calls
BEGIN
    SELECT RAISE(ABORT, 'source_calls rows are append-only');
END;
CREATE TRIGGER claims_append_only BEFORE UPDATE ON claims
BEGIN
    SELECT RAISE(ABORT, 'claims rows are append-only');
END;
CREATE TRIGGER claims_never_deleted BEFORE DELETE ON claims
BEGIN
    SELECT RAISE(ABORT, 'claims rows are append-only');
END;

-- The views of 0001, recreated unchanged.
CREATE VIEW v_funnel AS
SELECT
    s.run_id,
    r.kind AS run_kind,
    r.segment_id,
    s.seq,
    s.step,
    s.implementation,
    s.status,
    s.entering,
    s.kept,
    s.exited
FROM step_runs AS s
JOIN runs AS r ON r.run_id = s.run_id;

CREATE VIEW v_lead_journey AS
SELECT
    l.lead_id,
    l.segment_id,
    c.name AS company_name,
    c.domain,
    l.created_at,
    (
        SELECT o.step || ':' || o.outcome || coalesce(':' || o.reason, '')
        FROM lead_step_outcomes AS o
        WHERE o.lead_id = l.lead_id
        ORDER BY o.outcome_id DESC
        LIMIT 1
    ) AS latest_outcome,
    (
        SELECT d.status FROM drafts AS d
        WHERE d.lead_id = l.lead_id
        ORDER BY d.draft_id DESC
        LIMIT 1
    ) AS draft_status,
    EXISTS (
        SELECT 1 FROM crm_writes AS w
        WHERE w.lead_id = l.lead_id AND w.status = 'applied'
    ) AS in_crm
FROM leads AS l
JOIN companies AS c ON c.company_id = l.company_id;
