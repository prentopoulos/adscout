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

CREATE TABLE briefs (
    brief_id INTEGER PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    implementation TEXT NOT NULL CHECK (implementation IN ('stub', 'real')),
    status TEXT NOT NULL CHECK (status IN ('complete', 'partial')),
    summary TEXT NOT NULL,
    claims_json TEXT NOT NULL CHECK (json_valid(claims_json)),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE companies (
    company_id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_run_id TEXT NOT NULL REFERENCES runs (run_id),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE config_snapshots (
    content_hash TEXT PRIMARY KEY CHECK (length(content_hash) = 64),
    kind TEXT NOT NULL CHECK (kind IN ('segment', 'seed_list', 'stub_script')),
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

CREATE TABLE lead_step_outcomes (
    outcome_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    step TEXT NOT NULL,
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    seed_row INTEGER CHECK (seed_row >= 2),
    outcome TEXT NOT NULL CHECK (outcome IN ('kept', 'exited')),
    reason TEXT CHECK (reason IN (
        'duplicate', 'excluded', 'out_of_profile', 'missing_key_fields', 'below_threshold',
        'draft_failed', 'rejected'
    )),
    flag TEXT CHECK (flag IN ('research_partial', 'crm_conflict')),
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

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('pipeline', 'approval', 'crm_sync')),
    segment_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'interrupted')),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    error_category TEXT,
    error_detail TEXT,
    validation_outcome TEXT NOT NULL DEFAULT 'not_run'
        CHECK (validation_outcome IN ('pass', 'fail', 'not_run')),
    validation_detail TEXT,
    source TEXT NOT NULL CHECK (source IN ('stub', 'fixture', 'live')),
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

CREATE INDEX lead_step_outcomes_by_lead ON lead_step_outcomes (lead_id, run_id);

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
