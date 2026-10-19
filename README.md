# AdScout

Which brands fit a publisher's audience, and what should the first pitch say?
AdScout enriches companies, ranks their fit, produces cited research and drafts a pitch
for a person to review. The local MVP carries that draft through human approval, a CRM
sandbox, a sandbox inbox and a funnel dashboard with simulated revenue.

## Try it

From this checkout, with Python 3.13 and uv installed:

```powershell
uv run --locked adscout demo
```

Open **http://127.0.0.1:8765**. No account or API key is needed. The first run creates
`data/demo.db`; later runs reuse it and preserve your decisions. Stop the server with Ctrl+C.
Use `--db data/another-demo.db` for a separate demo. Never delete a working database to rerun.

1. Select **Alpha Gear** and inspect its draft and source quotes.
2. Click **Approve draft**, then **Sync approved to local CRM**.
3. Click **Place in sandbox** and inspect the local message and its unsubscribe link.
4. Click **Simulate $2,500 won** to see the simulated-revenue feedback loop.
5. Review **Hotel Gear**, whose critic remains unresolved, or reject it with a reason.

All demo companies are synthetic, model responses are scripted and company pages are
fixtures. The pipeline's real code performs validation, scoring arithmetic, research
verification and draft checks. Demo scores are not evidence of live model quality.
The CRM and inbox are SQLite sandboxes; **no email is sent**. Revenue is simulated.

## Inspect a run

```powershell
uv run --locked adscout runs --db data/demo.db
uv run --locked adscout funnel RUN_ID --db data/demo.db
uv run --locked adscout trace RUN_ID --db data/demo.db --lead alpha.test
uv run --locked adscout export RUN_ID --db data/demo.db
uv run --locked adscout check RUN_ID --db data/demo.db
```

To inspect another existing segment, use `adscout serve --segment SEGMENT --db PATH`.
The workspace is local and single-user; bind address is fixed to 127.0.0.1.

## How it works

```mermaid
flowchart LR
    S[Seed companies] --> E[Enrich and validate]
    E --> Q[Rules and fit score]
    Q --> R[Research team and claim verifier]
    R --> D[Writer, rule checker and critic]
    D --> H[Human review]
    H --> C[Local CRM sandbox]
    C --> I[Local sandbox inbox]
    C --> F[Funnel and simulated revenue]
```

The research lead and three read-only workers use bounded tools; the writer and critic
use verified research and media-kit facts. Model and source calls record usage, cost and
trace IDs. A spend reservation precedes paid calls. Human approval binds both subject and
body; changing either invalidates local delivery. Unsubscribe blocks future sandbox sends.

- [Generated agent flow](docs/architecture/agent-flow.html)
- [Agent registry diagram](docs/architecture/agents.md)
- [C4 model](docs/architecture/workspace.dsl)
- [Data model](docs/architecture/erd.md)
- [Operations and evidence](AI_OPS.md)
- [Current checkpoint](HANDOFF.md)

## Verification and limits

```powershell
uv run --locked python scripts/gate.py
```

The gate checks formatting, strict types, tests with sockets blocked, at least 90% coverage,
secrets, documentation, specifications and deterministic evaluation cases. Provider quality
and billing need separate authorized live evaluations. The local MVP does not claim those
results. A sandbox message is local simulated delivery, not proof of email deliverability.

Private recruiter slides and a captioned two-minute walkthrough are prepared; their
script and demo disclosures are in [the walkthrough](docs/walkthrough.md).

Deferred: the 30-company labelled study, live model/design comparisons, cloud CRM/inbox
and tracing, container packaging and hosted CI. Existing live adapters
remain behind the account, source-access and spend gates in [PROJECT.md](PROJECT.md).

This repository is private and has no publication licence yet. Python dependencies and
their licences are recorded by the locked environment; third-party skills retain their
own notices. AdScout is not affiliated with any company or publisher named in its inputs.
