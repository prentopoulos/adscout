-- Generated from a freshly migrated database; do not edit by hand.
-- Regenerate: uv run python -m adscout.db.snapshot

CREATE TABLE approvals (
    approval_id TEXT PRIMARY KEY CHECK (length(approval_id) = 36),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    draft_id INTEGER NOT NULL UNIQUE REFERENCES drafts (draft_id),
    draft_sha256 TEXT NOT NULL CHECK (length(draft_sha256) = 64),
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    approver_kind TEXT NOT NULL CHECK (approver_kind IN ('stub', 'person')),
    approver TEXT NOT NULL,
    reason TEXT,
    decided_at TEXT NOT NULL,
    CHECK (decision = 'approved' OR reason IS NOT NULL)
) STRICT;

CREATE TABLE "briefs" (
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

CREATE TABLE companies (
    company_id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_run_id TEXT NOT NULL REFERENCES runs (run_id),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE "config_snapshots" (
    content_hash TEXT PRIMARY KEY CHECK (length(content_hash) = 64),
    kind TEXT NOT NULL CHECK (kind IN (
        'segment', 'seed_list', 'stub_script', 'site_list', 'media_kit', 'price_table'
    )),
    segment_id TEXT NOT NULL,
    content_json TEXT NOT NULL CHECK (json_valid(content_json)),
    first_seen_at TEXT NOT NULL
) STRICT;

CREATE TABLE crm_writes (
    operation_id TEXT PRIMARY KEY CHECK (length(operation_id) = 36),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    approval_id TEXT NOT NULL REFERENCES approvals (approval_id),
    target TEXT NOT NULL,
    domain TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('create', 'update', 'no_op')),
    fields_written_json TEXT NOT NULL CHECK (json_valid(fields_written_json)),
    fields_skipped_json TEXT NOT NULL CHECK (json_valid(fields_skipped_json)),
    status TEXT NOT NULL CHECK (status IN ('applied', 'failed')),
    detail TEXT NOT NULL,
    written_at TEXT NOT NULL
) STRICT;

CREATE TABLE drafts (
    draft_id INTEGER PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    implementation TEXT NOT NULL CHECK (implementation IN ('stub', 'real')),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    body_sha256 TEXT NOT NULL CHECK (length(body_sha256) = 64),
    status TEXT NOT NULL CHECK (status IN (
        'pending_approval', 'approved', 'rejected', 'failed_checks'
    )),
    created_at TEXT NOT NULL
, sentences_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(sentences_json)), checks_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(checks_json)), critic_notes_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(critic_notes_json)), publisher_id TEXT, brief_id INTEGER REFERENCES briefs (brief_id)) STRICT;

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

CREATE TABLE enrichments (
    enrichment_id INTEGER PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    implementation TEXT NOT NULL CHECK (implementation IN ('stub', 'real')),
    fields_json TEXT NOT NULL CHECK (json_valid(fields_json)),
    missing_fields_json TEXT NOT NULL CHECK (json_valid(missing_fields_json)),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE fake_crm_account_fields (
    crm_account_id INTEGER NOT NULL REFERENCES fake_crm_accounts (crm_account_id),
    field TEXT NOT NULL,
    value TEXT,
    owner TEXT NOT NULL CHECK (owner IN ('adscout', 'person')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (crm_account_id, field)
) STRICT;

CREATE TABLE fake_crm_accounts (
    crm_account_id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL CHECK (created_by IN ('adscout', 'person')),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE "lead_step_outcomes" (
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

CREATE TABLE leads (
    lead_id TEXT PRIMARY KEY CHECK (length(lead_id) = 36),
    segment_id TEXT NOT NULL,
    company_id INTEGER NOT NULL REFERENCES companies (company_id),
    source TEXT NOT NULL CHECK (length(source) > 0),
    prompt_version TEXT NOT NULL CHECK (length(prompt_version) > 0),
    agent_version TEXT NOT NULL CHECK (length(agent_version) > 0),
    created_run_id TEXT NOT NULL REFERENCES runs (run_id),
    created_at TEXT NOT NULL,
    UNIQUE (segment_id, company_id)
) STRICT;

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

CREATE TABLE "runs" (
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

CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    applied_at TEXT NOT NULL
) STRICT;

CREATE TABLE scores (
    score_id INTEGER PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    implementation TEXT NOT NULL CHECK (implementation IN ('stub', 'real')),
    score REAL,
    reasons_json TEXT NOT NULL CHECK (json_valid(reasons_json)),
    null_reasons_json TEXT NOT NULL CHECK (json_valid(null_reasons_json)),
    created_at TEXT NOT NULL
, criteria_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(criteria_json)), sample INTEGER NOT NULL DEFAULT 1 CHECK (sample >= 1), model_call_id TEXT REFERENCES model_calls (call_id)) STRICT;

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

CREATE TABLE step_runs (
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    step TEXT NOT NULL CHECK (step IN (
        'source', 'enrich', 'rules', 'score', 'research', 'draft', 'approve', 'crm_sync'
    )),
    seq INTEGER NOT NULL CHECK (seq >= 1),
    implementation TEXT NOT NULL CHECK (implementation IN ('stub', 'real')),
    implementation_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_ms INTEGER CHECK (duration_ms >= 0),
    entering INTEGER CHECK (entering >= 0),
    kept INTEGER CHECK (kept >= 0),
    exited INTEGER CHECK (exited >= 0),
    model TEXT,
    input_tokens INTEGER CHECK (input_tokens >= 0),
    output_tokens INTEGER CHECK (output_tokens >= 0),
    cost_usd REAL CHECK (cost_usd >= 0),
    null_reasons_json TEXT NOT NULL CHECK (json_valid(null_reasons_json)),
    PRIMARY KEY (run_id, step),
    UNIQUE (run_id, seq)
) STRICT;

CREATE INDEX enrichment_fields_by_lead ON enrichment_fields (lead_id, run_id);

CREATE INDEX lead_step_outcomes_by_lead ON lead_step_outcomes (lead_id, run_id);

CREATE INDEX model_calls_by_lead ON model_calls (lead_id, run_id);

CREATE INDEX source_calls_by_lead ON source_calls (lead_id, run_id);

CREATE UNIQUE INDEX spans_one_step_span_per_lead ON spans (run_id, lead_id, step)
WHERE operation = 'step';

CREATE TRIGGER claims_append_only BEFORE UPDATE ON claims
BEGIN
    SELECT RAISE(ABORT, 'claims rows are append-only');
END;

CREATE TRIGGER claims_never_deleted BEFORE DELETE ON claims
BEGIN
    SELECT RAISE(ABORT, 'claims rows are append-only');
END;

CREATE TRIGGER leads_never_deleted
BEFORE DELETE ON leads
BEGIN
    SELECT RAISE(ABORT, 'leads are never deleted');
END;

CREATE TRIGGER leads_source_fields_immutable
BEFORE UPDATE OF lead_id, segment_id, company_id, source, prompt_version, agent_version,
    created_run_id, created_at ON leads
BEGIN
    SELECT RAISE(ABORT, 'lead source fields are immutable');
END;

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
