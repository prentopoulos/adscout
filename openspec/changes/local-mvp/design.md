## Context

The pipeline already runs offline with scripted model responses and fixture company sites.
The owner delegates simplification to finish the rest as a local MVP in this session.
This authorization replaces another grilling round for routine MVP choices. No constitution
or operator gate is amended. This milestone remains on phase-2/ai-pipeline until reviewed.

## Decisions

1. Use the existing Python stack, SQLite and a standard-library loopback HTTP server.
   The person reviews one draft at a time; all writes are explicit POST forms with a
   per-process CSRF value, strict Host/Origin checks and bounded request bodies.
2. Human approval binds both subject and body to the screen the person reviewed. Stale
   forms, rejected drafts and later changes cannot authorize CRM or sandbox delivery.
   Reviewer identity is the local OS/session boundary, stored as a generic local operator.
   Editing drafts is deferred; reject and regenerate rather than silently bypass checks.
3. Reuse the one CRM writer. Its SQLite target is visibly a local sandbox, not HubSpot.
4. The single send function writes only to a SQLite sandbox inbox for synthetic .test
   companies after human approval. It fills sender/footer placeholders and a local
   unsubscribe URL; the link suppresses later sends. Delivery is idempotent per approval.
   No SMTP, external recipient or send tool exists. This is local simulated delivery.
5. Simulated deals use integer USD cents and explicit stages; only CRM-synced leads can
   have deals. All amounts and aggregates are labelled simulated. No conversion-lift claim.
6. Use the existing fixture publisher for the demo. A branded real-seed kit, owner labels,
   live runs, paid comparisons, private artifact republishing and cloud adapters are deferred.
7. Finish the registry diagrams and C4 model locally. No public artifact or remote repository.

## Acceptance evidence

The offline demo generates real code-path outputs with fake model answers; a person can
approve or reject, sync, deliver to the local sandbox, unsubscribe, and view simulated
revenue. Tests exercise stale approval, duplicate delivery, suppression, rejected and
non-synthetic delivery, unsafe web requests and escaped content. Run the full local gate,
inspect the actual browser, and record a scoped code review before presenting completion.
