## Why

AdScout has project documents and skills but no code, toolchain or checks. PROJECT.md §6
Phase 0 builds the foundation every later phase relies on: a reproducible Python environment,
one local gate that enforces the constitution's checkable rules, and an offline evaluation
harness whose records already carry the fields later model evaluations need.

This change implements **PROJECT.md Phase 0** ("Toolchain, lockfile, quality gate, smoke
checks; offline AI evaluation scaffold"). Its decisions come from the Phase 0 grilling of
2026-10-17, recorded in PROJECT.md §4 and in design.md with who made each.

## What Changes

- **Line endings:** a `.gitattributes` keeps the 26 verbatim skill files byte-exact and uses LF
  elsewhere. The setup commit stored those files with LF, so their committed bytes fail the
  source manifest; this change re-commits them once.
- **Skill folders:** the six duplicated `.agents/skills/source-command-opsx-*` folders are
  deleted and their pattern gitignored.
- **Toolchain:** a `pyproject.toml` (PEP 621) for package `adscout` 0.1.0 in src layout on
  Python 3.13, a committed `uv.lock`, an `adscout --version` command, and dev tools pinned in
  the lock.
- **Gate:** `uv run --locked python scripts/gate.py` runs, in order, the lockfile check, format,
  lint, types, unit and smoke tests (sockets blocked, coverage reported), the constitution copy
  check, the verbatim digest check, the secrets scan, the commit message check, the
  documentation checks, the evaluation scaffold run and `openspec validate --all --strict`.
  Every check has a test that plants a violation and expects a failure.
- **Evaluation scaffold:** pytest-based harness under `evals/`, case and result formats as
  committed JSON Schema following the eval-review skill, a synthetic self-test case set with
  one deliberately failing case, and run records kept in gitignored `evals/runs/`.
- **Documents:** every "TBD in Phase 0" placeholder names the gate; AI_OPS.md points at the
  evaluation scaffold.
- **Phase close:** a pip-audit dependency audit, recorded in HANDOFF.md.

## Capabilities

### New Capabilities

- `project-toolchain`: Python package, lockfile, environment bootstrap, version and smoke
  checks.
- `quality-gate`: the single local gate command and every check it runs, including the
  constitution copy check, verbatim digests, secrets scan, no-network tests and commit
  messages.
- `offline-eval-harness`: evaluation case and result formats, the offline runner, run-record
  retention and the scaffold self-test cases.

### Modified Capabilities

None; `openspec/specs/` is empty.

## Non-goals

- Pipeline code, segment or ideal-customer config, seed list or database (Phase 1).
- Any model SDK, model call, prompt or model-cost item (Phase 2).
- Network access in tests, live searches, fetches or enrichment.
- CI workflow (Phase 5), Docker (Phase 6), dashboard or approval UI (Phases 4 and 6).
- Structural guards for rules whose code does not exist yet (the design maps each to its
  phase).
- A licence (publishing gate).

## Impact

- New files: `pyproject.toml`, `uv.lock`, `.python-version`, `.gitattributes`,
  `src/adscout/`, `scripts/gate.py` and `scripts/checks/`, `tests/`, `evals/`, a secrets
  allowlist.
- Changed: `.gitignore`; the "TBD in Phase 0" lines in PROJECT.md, AGENTS.md, CLAUDE.md,
  WORKFLOW.md, `openspec/config.yaml`, AI_OPS.md and the next-phase skill; HANDOFF.md.
- Deleted: six `.agents/skills/source-command-opsx-*` folders (owner call).
- Dependencies (dev group only): ruff, mypy, pytest, pytest-socket, pytest-cov, pip-audit,
  PyYAML, pydantic, jsonschema. No runtime dependencies.
- Constitution: no §5 rule or ⛔ gate is amended. One operator decision is recorded under the
  live-read gate (dependency audits are not live reads), which PROJECT.md § Amending the
  constitution says is not an amendment.
