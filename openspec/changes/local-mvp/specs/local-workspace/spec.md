## ADDED Requirements

### Requirement: Human review
The local workspace SHALL show drafts with cited research and their source mode. Human
decisions SHALL bind the reviewed subject and body, reject stale forms, and be recorded.

#### Scenario: Changed draft
- **WHEN** a submitted approval digest differs from the stored subject and body
- **THEN** no approval is recorded

### Requirement: Sandbox delivery
One send function SHALL deliver only approved, unchanged synthetic-company drafts to a
local inbox, with sender identification, a functioning local unsubscribe link, suppression
and idempotence. It SHALL never contact an email service or external recipient.

#### Scenario: Unsubscribed lead
- **WHEN** a lead has used its unsubscribe link
- **THEN** subsequent sandbox delivery is refused

### Requirement: Local dashboard
The workspace SHALL show the funnel, scores, review status, CRM sandbox state, recorded
model cost and simulated deals. Simulated revenue SHALL be labelled wherever displayed.

#### Scenario: No CRM record
- **WHEN** a simulated deal is requested for a lead absent from the CRM sandbox
- **THEN** the operation is refused

### Requirement: Reproducible local demo
A single command SHALL populate a persistent local demo database using fixture inputs
and scripted model responses, then serve the workspace on 127.0.0.1. Repeating it SHALL
preserve existing decisions and not duplicate the seeded demo.

#### Scenario: Existing demo
- **WHEN** the demo command runs again on the same successful demo database
- **THEN** it reuses its data without overwriting decisions
