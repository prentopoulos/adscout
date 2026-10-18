## ADDED Requirements

### Requirement: Reproducible environment from the lockfile
The project SHALL declare its metadata in a PEP 621 `pyproject.toml` with
`requires-python = ">=3.13"`, pin every dependency in a committed `uv.lock`, and build the
environment with `uv sync --locked` without installing anything outside the project.

#### Scenario: Fresh clone bootstraps
- **WHEN** a fresh clone runs `uv sync --locked` with uv 0.13 or newer and Python 3.13
- **THEN** the environment is created from `uv.lock` and the command exits 0

#### Scenario: Stale lockfile is rejected
- **WHEN** `pyproject.toml` changes a dependency without updating `uv.lock`
- **THEN** the gate's lockfile step fails and names the lockfile as out of date

### Requirement: Package and command
The project SHALL ship an importable package `adscout` in src layout and an `adscout` console
command whose `--version` prints the version read from the installed package metadata.

#### Scenario: Version command
- **WHEN** a user runs `adscout --version`
- **THEN** it prints `adscout 0.1.0` and exits 0

#### Scenario: Single version source
- **WHEN** `[project].version` in `pyproject.toml` changes and the environment is synced
- **THEN** `adscout --version` prints the new version with no other file edited

### Requirement: Accidental upload guard
The package metadata SHALL carry the `Private :: Do Not Upload` classifier and no licence
field until the owner resolves the publishing gate.

#### Scenario: Metadata guard present
- **WHEN** the gate's tests read the project metadata
- **THEN** the classifier is present and no licence field is declared

### Requirement: Byte-exact verbatim skill files across clones
The repository SHALL store the 26 verbatim skill files listed in the build-safety source
manifest as unconverted bytes, and every other text file with LF line endings.

#### Scenario: Clone with line-ending conversion on
- **WHEN** the repository is cloned with `core.autocrlf=true`
- **THEN** each verbatim file's SHA-256 matches the source manifest

#### Scenario: Clone with line-ending conversion off
- **WHEN** the repository is cloned with `core.autocrlf=false`
- **THEN** each verbatim file's SHA-256 matches the source manifest
