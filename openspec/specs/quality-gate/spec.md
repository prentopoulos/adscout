# quality-gate Specification

## Purpose
One local command that runs every check a change must pass before it is committed or
merged, including the checks that enforce the constitution's checkable rules.

## Requirements
### Requirement: One local gate command
The project SHALL provide one gate command, `uv run --locked python scripts/gate.py`, that
runs every check in a fixed order, prints each step's name and outcome, keeps going after a
failure so every failing step is reported, and exits non-zero if any step fails.

#### Scenario: All checks pass
- **WHEN** the gate runs on a clean tree that satisfies every check
- **THEN** every step reports pass and the command exits 0

#### Scenario: One check fails
- **WHEN** exactly one step fails
- **THEN** the remaining steps still run, the summary names the failing step and the command
  exits non-zero

### Requirement: Code quality steps
The gate SHALL check, through tools pinned in `uv.lock`, the lockfile, ruff formatting, ruff
lint (including the S105 to S107 hardcoded-secret rules), mypy in strict mode and the pytest
suite with a coverage report and no coverage threshold.

#### Scenario: Lint error
- **WHEN** a source file contains a ruff lint violation
- **THEN** the lint step fails

#### Scenario: Type error
- **WHEN** a source file contains a mypy strict error
- **THEN** the type step fails

### Requirement: No network in tests
The test suite SHALL block socket access for every test.

#### Scenario: Test opens a socket
- **WHEN** a test tries to open a network connection
- **THEN** that test fails with a socket-blocked error

### Requirement: Constitution copy check
The gate SHALL verify that the PROJECT.md §5 rules appear in AGENTS.md and in the
`openspec/config.yaml` context in the same order with the same words, ignoring only line
wrapping and repeated whitespace, and that all three version lines and the PROJECT.md
"Last amended" date match the newest amendment-log row.

#### Scenario: Edited rule in a copy
- **WHEN** one word of one rule differs in AGENTS.md
- **THEN** the copy check fails and names the file and the rule

#### Scenario: Missing or reordered rule
- **WHEN** a copy omits a rule or lists two rules in a different order
- **THEN** the copy check fails

#### Scenario: Version drift
- **WHEN** a copy's version line differs from the newest amendment-log row
- **THEN** the copy check fails

### Requirement: Verbatim digest check
The gate SHALL hash each file listed in the build-safety source manifest and fail when any
digest differs or a listed file is missing.

#### Scenario: Changed byte
- **WHEN** one byte of a verbatim file changes
- **THEN** the digest check fails and names the file

### Requirement: Secrets scan
The gate SHALL scan tracked files and untracked files that are not ignored for known key
formats (Anthropic, OpenAI, HubSpot, Langfuse, AWS, private key blocks) and for long literal
values assigned to names containing KEY, TOKEN, SECRET or PASSWORD, skipping entries in a
committed allowlist that each carry a reason. It SHALL also fail when `.env` is not ignored or
is tracked. A finding SHALL report the file and line, never the matched value.

#### Scenario: Planted fake key
- **WHEN** an untracked, non-ignored file contains a string in a known key format
- **THEN** the scan fails, naming the file and line without printing the value

#### Scenario: Environment file tracked
- **WHEN** `.env` is tracked or not matched by `.gitignore`
- **THEN** the scan fails

#### Scenario: Allowlisted fixture
- **WHEN** a finding matches an allowlist entry with a reason
- **THEN** the scan does not report it

### Requirement: Commit message check
The gate SHALL check the subject of every non-merge commit on the current branch since its
merge-base with `main` against Conventional Commits 1.0.0.

#### Scenario: Bad commit subject
- **WHEN** a branch commit's subject is "updated stuff"
- **THEN** the commit message check fails and names the commit

### Requirement: Documentation checks
The gate SHALL check that local Markdown links resolve, that each `.claude/skills` pointer's
frontmatter matches its canonical `.agents/skills` skill, and that every skill's frontmatter
name matches its folder and has a description.

#### Scenario: Broken link
- **WHEN** a Markdown file links to a local path that does not exist
- **THEN** the documentation check fails and names the file and link

#### Scenario: Pointer drift
- **WHEN** a pointer's description differs from its canonical skill
- **THEN** the documentation check fails

### Requirement: OpenSpec validation
The gate SHALL run `openspec validate --all --strict` from PATH and print the OpenSpec
version, and SHALL fail with an install hint when the CLI is missing.

#### Scenario: CLI missing
- **WHEN** `openspec` is not on PATH
- **THEN** the OpenSpec step fails and prints how to install it

