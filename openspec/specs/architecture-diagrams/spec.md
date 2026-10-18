# architecture-diagrams Specification

## Purpose
C4 diagrams and an entity-relationship diagram kept as code, so the documented
architecture cannot drift from what is built.

## Requirements
### Requirement: One C4 model as code
The architecture SHALL be described by one Structurizr DSL model, `docs/architecture/
workspace.dsl`, following the c4model.com notation guide: each view has a title naming its
type, scope and date and a key, and each element has a name, a type with technology and a
one-line description. Elements not built yet SHALL be tagged `Planned`, drawn dashed and grey,
and say "(planned, Phase N)". The model SHALL NOT name a real publisher.

#### Scenario: Planned elements marked
- **WHEN** the model is read
- **THEN** the model provider, search API, enrichment API, CRM sandbox, tracing service,
  sandbox inbox, approval UI and dashboard each carry the `Planned` tag and their phase

### Requirement: Context and container views
The model SHALL define a system context view and two container views: one titled "built,
Phase 1" that excludes planned elements, and one titled "target" that includes them.

#### Scenario: Built view shows only what exists
- **WHEN** the built container view is exported
- **THEN** it contains the command-line pipeline, the SQLite database and the local fake
  CRM, and no element tagged `Planned`

### Requirement: Exported diagrams kept current
Each view SHALL be exported to SVG and to Mermaid under `docs/architecture/` with the
Structurizr `-playwright` release run locally, never through a hosted editor. A committed
stamp SHALL record the SHA-256 of `workspace.dsl` at the last export, and the gate SHALL fail
when the model has changed since, without needing Java.

#### Scenario: Model edited without re-export
- **WHEN** `workspace.dsl` changes and the exports are not regenerated
- **THEN** the gate fails and says to re-export

### Requirement: Generated ERD
An entity-relationship diagram SHALL be generated as a Mermaid `erDiagram` from a freshly
migrated database's tables and foreign keys by a standard-library script, committed as
`docs/architecture/erd.md`, and the gate SHALL fail when the committed file differs from a
fresh generation.

#### Scenario: Schema changed without regenerating
- **WHEN** a migration adds a table and `erd.md` is not regenerated
- **THEN** the gate fails

