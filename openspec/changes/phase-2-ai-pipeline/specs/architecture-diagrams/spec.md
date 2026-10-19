## ADDED Requirements

### Requirement: Agent-flow diagram generated from the registry
`scripts/diagrams.py` SHALL generate, from the agent registry alone and with no network call,
`docs/architecture/agents.md` (Mermaid with a colour per pattern, trust-zone groups and edge
labels naming the handoff types) and `docs/architecture/agent-flow.html` (one self-contained
page of inline SVG with no external scripts, showing each step and agent, its pattern, model,
tools and caps, the typed handoffs, the trust zones and a key). The export stamp SHALL cover
both files, and the gate SHALL fail when either differs from a fresh generation.

#### Scenario: Registry changed without regenerating
- **WHEN** a worker's page cap changes in the registry and the diagrams are not regenerated
- **THEN** the gate fails and says to regenerate

#### Scenario: No network to draw
- **WHEN** the diagrams are generated under the socket block
- **THEN** generation succeeds

### Requirement: Research team in the C4 model
The C4 model SHALL show the model provider and web search as built in Phase 2, a component
view of the research team (lead, three workers, verifier, fetcher) and the draft loop, and
keep Phase 3 elements tagged `Planned`.

#### Scenario: Phase 2 elements not planned
- **WHEN** the model is read after this change
- **THEN** the model provider and web search carry no `Planned` tag, and the approval UI,
  dashboard, CRM sandbox, sandbox inbox and tracing service are tagged Phase 3
