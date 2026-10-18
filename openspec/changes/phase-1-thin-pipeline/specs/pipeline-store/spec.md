## ADDED Requirements

### Requirement: Local SQLite database
The pipeline SHALL store its data in one SQLite file, by default `data/adscout.db`
(gitignored together with its `-wal` and `-shm` files and `data/backups/`), overridable with
`--db` or the `ADSCOUT_DB` environment variable. Every connection SHALL turn on foreign keys
and use WAL journal mode, and every table SHALL be STRICT.

#### Scenario: Foreign keys enforced
- **WHEN** code inserts a lead whose company does not exist
- **THEN** the insert fails with an integrity error

#### Scenario: Database path override
- **WHEN** `ADSCOUT_DB` names a file and no `--db` is given
- **THEN** every command uses that file

### Requirement: Versioned migrations
Schema changes SHALL be applied only by numbered SQL migration files, each in one
transaction, recorded in a `schema_migrations` table with its number, name, SHA-256 and time
applied. `adscout db upgrade` SHALL copy an existing database to `data/backups/` through the
SQLite backup API before applying any migration, and SHALL refuse to run when an applied
migration's file has changed.

#### Scenario: Fresh database
- **WHEN** `adscout db upgrade` runs on a missing file
- **THEN** it creates the database, applies every migration in order and records each one

#### Scenario: Edited migration
- **WHEN** a migration that was already applied is edited
- **THEN** `adscout db upgrade` fails and names the migration, changing nothing

#### Scenario: Re-run is a no-op
- **WHEN** `adscout db upgrade` runs on an up-to-date database
- **THEN** it applies nothing, takes no backup and exits 0

### Requirement: Schema snapshot
A committed `schema.sql` SHALL hold the tables, indexes, triggers and views of a freshly
migrated database, and the gate SHALL fail when a fresh migration differs from it.

#### Scenario: Trigger lost in a rebuild
- **WHEN** a migration rebuilds the leads table and does not recreate its triggers
- **THEN** the snapshot test fails

### Requirement: Lead identity
A company SHALL be stored once, keyed by its normalized domain. A lead SHALL be one company
within one segment, unique on segment and company, created once when the company is first
sourced for that segment. Each lead SHALL get a UUIDv7 (RFC 9562) lead ID at creation.

#### Scenario: Same company, second run
- **WHEN** a second run sources a company that already has a lead in the segment
- **THEN** no new lead is created and the run records the outcome "duplicate" for it

#### Scenario: Time-ordered IDs
- **WHEN** two lead IDs are generated one after the other
- **THEN** both are valid version-7 UUIDs and the later one sorts after the earlier one

### Requirement: Immutable lead source fields
Every lead SHALL carry, at creation and non-null, its lead ID, segment ID, company,
source, prompt version, agent version, creating run and creation time. The database SHALL
refuse any UPDATE of these fields and any DELETE of a lead. The agent version SHALL be the
package version with a PEP 440 local label of the 12-character Git commit (for example
`0.2.0+g1a2b3c4d5e6f`) and `.dirty` appended when the tree has uncommitted changes. While no
prompt exists, the prompt version SHALL be the literal `none`.

#### Scenario: Update refused
- **WHEN** any statement updates a lead's source or agent version
- **THEN** the database raises an integrity error and the row is unchanged

#### Scenario: Delete refused
- **WHEN** any statement deletes a lead
- **THEN** the database raises an integrity error

#### Scenario: Phase 1 versions
- **WHEN** a lead is created from a clean tree in Phase 1
- **THEN** its prompt version is `none` and its agent version has no `.dirty` suffix

### Requirement: No personal contact columns
The schema SHALL NOT contain a column for personal contact data. A test SHALL fail when any
column name in a migrated database matches a personal-contact pattern (email, phone, first,
last or full name, person, contact, linkedin), except in a future `contacts` table whose
design is recorded for Phase 4.

#### Scenario: Contact column added
- **WHEN** a migration adds a column named `contact_email` to the companies table
- **THEN** the schema guard test fails and names the table and column

### Requirement: Records are never deleted
No command SHALL delete or reset rows, runs or the database file. Failed and interrupted runs
SHALL keep every row they wrote.

#### Scenario: No reset command
- **WHEN** the command list is printed
- **THEN** it contains no command that drops, resets or deletes data
