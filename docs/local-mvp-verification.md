# Local MVP verification · 2026-10-19

Scope: `openspec/changes/local-mvp/` on `phase-2/ai-pipeline`, based on `40da88d`.
This is the reduced local milestone requested by the owner, not completion of the original
live-validation phase. Package remains 0.2.0 until the original phase is closed and merged.

## Implemented

`adscout demo` prepares a persistent SQLite demo and serves the loopback workspace.
Synthetic fixture companies pass through real enrichment/rules/scoring arithmetic,
research verification and writer/critic code with scripted model responses. The person
reviews source quotes, approves/rejects, syncs through the existing CRM writer, places an
approved message into a local inbox, unsubscribes and simulates USD deals. No account,
paid call, external email or hosted service is needed.

Approval binds subject and body; stale/tampered drafts fail. Delivery requires a human
approval, synthetic domain and CRM account. Fixed sender data and a local unsubscribe
link replace checked placeholders. Unique approval delivery and suppression are enforced
inside write transactions. CRM writes preserve person-owned fields. Model agents receive
none of these write functions or private CRM/revenue data.

## Review

The implementing agent reviewed the working diff against the local spec, PROJECT.md §5,
WORKFLOW.md and the original registry/diagram requirements. No separate reviewer agent
was available in this session; this is a manual self-review, not an independent review.

Findings fixed with regression coverage:

1. Approval previously protected only body content. Schema 3 and both consumers now also
   bind the reviewed subject; changed subjects/bodies cannot reach local delivery.
2. Non-ASCII CSRF input could raise an uncaught comparison error. Byte comparisons now
   reject it normally; malformed evidence URLs render as escaped text.
3. Dashboard and CRM could select a later repeated score. They now use sample 1 in the
   latest scoring run, matching the routing rule.
4. Partial research and unresolved critic objections needed a visible review warning;
   the review now shows these before the approval controls.
5. The single-CRM-writer guard matched unrelated writes followed by read-only queries
   elsewhere in a Python file. It now inspects AST string constants and actual SQL write
   prefixes, retaining the one-writer restriction.

Deferred review boundary: the whole original Phase 2 branch still needs its closure review
after the live-study work. No merge or phase archive has occurred.

## Checks

- Focused regression: 63 database, architecture, diagram and local-workflow tests passed;
  the final added score-routing/security cases also passed.
- Strict mypy: 92 source files pass. Ruff lint and formatting pass.
- Gate: all 12 steps pass, 518 tests, 90 evaluation tests and 94.81% coverage. The initial full attempt found the CRM scanner
  false positive (516 passed, one failed, 94.44% coverage); that failure is retained in
  ignored `.local/mvp-gate.log`, with the corrected run separately recorded.
- `uv run --locked pip-audit --skip-editable --progress-spinner off`: no known vulnerabilities
  found on the locked installed dependencies; editable AdScout skipped. The first sandbox
  attempt could not resolve PyPI; the network-authorized audit succeeded.
- Structurizr DSL validated and SVG/Mermaid exports regenerated for context, built/target
  containers and the research component view. Registry HTML/Markdown and ERD regenerated;
  drift tests pass. No private artifact republishing was attempted.
- Actual loopback HTTP smoke: an isolated server bound 127.0.0.1, returned HTTP 200 and the
  review/evidence page to a client in the same process. The raw probe is ignored locally.
  The socket-blocked tests exercise the full POST workflow through the real HTTP handler.

## Browser verification and evidence limits

Chrome navigation to the running loopback server timed out in this tool environment.
A static local-file preview was then explicitly blocked by browser URL policy; no bypass
was attempted. In the subsequent showcase session, Chrome reached the current build on
a fresh loopback port (8767), avoiding an older server on 8765. The actual browser flow
passed: review, approval, CRM sync, sandbox placement, unsubscribe, refused re-delivery,
visible research/critic warnings, simulated deal and rejection. Independent database reads
confirm one sandbox message, one suppression and a simulated won deal of $2,500 USD.
At 390 px, body width is 375 px; the table scrolls inside its 341 px container and review
columns stack. Captures are preserved privately with the recruiter media build.

All model outputs, company pages and demo scores are fixtures, not provider observations.
No live accuracy, billing agreement, model-tier winner, multi-agent improvement, email
deliverability, cloud integration or real revenue has been established. Original paid
runs, owner decisions and publication/deployment gates remain open.
