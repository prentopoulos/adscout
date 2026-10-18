## MODIFIED Requirements

### Requirement: Code quality steps
The gate SHALL check, through tools pinned in `uv.lock`, the lockfile, ruff formatting, ruff
lint (including the S105 to S107 hardcoded-secret rules), mypy in strict mode and the pytest
suite with a line-coverage report over `src/` and `scripts/` that fails below 90%. The
threshold SHALL only be raised, never lowered, unless the owner decides otherwise.

#### Scenario: Lint error
- **WHEN** a source file contains a ruff lint violation
- **THEN** the lint step fails

#### Scenario: Type error
- **WHEN** a source file contains a mypy strict error
- **THEN** the type step fails

#### Scenario: Coverage below threshold
- **WHEN** the tests cover less than 90% of the lines in `src/` and `scripts/`
- **THEN** the test step fails and reports the measured coverage
