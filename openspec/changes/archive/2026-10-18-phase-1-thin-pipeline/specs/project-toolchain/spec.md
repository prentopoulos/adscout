## MODIFIED Requirements

### Requirement: Package and command
The project SHALL ship an importable package `adscout` in src layout and an `adscout` console
command whose `--version` prints the version read from the installed package metadata. The
package's runtime dependencies SHALL be declared in `[project].dependencies` and locked in
`uv.lock`.

#### Scenario: Version command
- **WHEN** a user runs `adscout --version`
- **THEN** it prints `adscout ` followed by `[project].version` and exits 0

#### Scenario: Single version source
- **WHEN** `[project].version` in `pyproject.toml` changes and the environment is synced
- **THEN** `adscout --version` prints the new version with no other file edited

#### Scenario: Runtime dependency declared
- **WHEN** a module under `src/adscout/` imports a third-party package
- **THEN** that package is listed in `[project].dependencies`
