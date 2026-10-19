-- Local-only MVP. No network mail or external CRM adapter.
ALTER TABLE approvals ADD COLUMN approved_subject_sha256 TEXT
    CHECK (approved_subject_sha256 IS NULL OR length(approved_subject_sha256) = 64);

CREATE TABLE sandbox_messages (
    message_id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL UNIQUE REFERENCES approvals (approval_id),
    lead_id TEXT NOT NULL REFERENCES leads (lead_id),
    destination TEXT NOT NULL CHECK (destination = 'sandbox@adscout.test'),
    sender TEXT NOT NULL CHECK (sender = 'AdScout Demo Publisher (synthetic)'),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE sandbox_suppressions (
    lead_id TEXT PRIMARY KEY REFERENCES leads (lead_id),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE simulated_deals (
    lead_id TEXT PRIMARY KEY REFERENCES leads (lead_id),
    stage TEXT NOT NULL CHECK (stage IN ('pipeline', 'won', 'lost')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents BETWEEN 0 AND 100000000),
    currency TEXT NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    simulated INTEGER NOT NULL DEFAULT 1 CHECK (simulated = 1),
    updated_at TEXT NOT NULL
) STRICT;
