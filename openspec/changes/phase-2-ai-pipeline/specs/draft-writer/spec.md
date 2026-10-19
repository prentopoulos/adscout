## ADDED Requirements

### Requirement: Writer, checker and critic loop
The `draft` step SHALL run a writer that outputs a subject and structured sentences, each with
supports naming a verified claim ID or a media-kit fact ID; then the deterministic rule
checker; then a critic with no tools that returns a verdict and issues. Failed checks or
critic issues SHALL go back to the writer at most twice. A draft failing the rules after two
rewrites SHALL exit as `draft_failed`; a draft passing the rules with the critic still
objecting SHALL be `pending_approval` with the flag `critic_unresolved` and the critic's
notes; otherwise `pending_approval`.

#### Scenario: Critic cannot override the rules
- **WHEN** the fake critic approves a draft the rule checker fails
- **THEN** the draft is rewritten, and after two failed rewrites it exits as `draft_failed`

#### Scenario: Unresolved critic
- **WHEN** the rules pass but the fake critic objects after two rewrites
- **THEN** the draft is `pending_approval` flagged `critic_unresolved` with the notes stored

### Requirement: Deterministic rule checker
The checker SHALL fail a draft when a sentence containing a digit, proper name, date, URL or
superlative lacks a support resolving to this lead's verified claims or a media-kit fact;
when a sentence's numbers are not a subset of its supports' numbers after normalization;
when a proper noun is not in its supports, the company name, the publisher name or the
allowlist; when the subject exceeds 70 characters or the body is outside 60–160 words; when
any of `{{sender_name}}`, `{{sender_title}}`, `{{publisher_postal_address}}` and
`{{unsubscribe_url}}` is missing or repeated; when it contains an email address, phone
number, person name or URL; when it uses a banned phrase; when the company name is not exact;
or when it echoes injection canary text.

#### Scenario: Unsupported number
- **WHEN** a sentence says "reach 2M gamers" and its support says 1.5M
- **THEN** the checker fails the draft and names the sentence

#### Scenario: Draft case set
- **WHEN** the gate runs `evals/cases/drafts.jsonl`
- **THEN** every case's expected pass or fail matches

### Requirement: Fictional publisher media kit
Drafts SHALL write as a fictional publisher defined in `config/media-kit/<publisher_id>.yaml`,
whose facts each carry an ID, text and `simulated: true`, validated by a strict model. Loading
SHALL fail when a fact lacks `simulated: true`.

#### Scenario: Real-looking fact without the label
- **WHEN** a media-kit fact omits `simulated`
- **THEN** loading fails and names the fact
