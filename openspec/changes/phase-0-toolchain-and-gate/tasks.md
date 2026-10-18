## 1. Repository hygiene

- [x] 1.1 Add `.gitattributes` (LF for text, `-text` for the two verbatim skill folders), run `git add --renormalize .`, and confirm each committed verbatim blob hashes to its manifest digest. Note in HANDOFF.md that 3de5377 stored LF blobs.
- [x] 1.2 Delete the six `.agents/skills/source-command-opsx-*` folders and gitignore `.agents/skills/source-command-*/`; add `evals/runs/` to `.gitignore`.

## 2. Toolchain

- [x] 2.1 Add `.python-version`, a PEP 621 `pyproject.toml` (package `adscout` 0.1.0, `requires-python = ">=3.13"`, `uv_build` backend, `Private :: Do Not Upload`, `[project.scripts] adscout`, uv `required-version`) and the dev group (ruff, mypy, pytest, pytest-socket, pytest-cov, pip-audit, PyYAML, pydantic, jsonschema); lock with uv and sync with `uv sync --locked`.
- [x] 2.2 Add `src/adscout/__init__.py` and `cli.py` with `--version` from package metadata; configure ruff (including S and TID), mypy strict with the pydantic plugin, and pytest (`--disable-socket`, coverage report, `pythonpath = ["scripts"]`).
- [x] 2.3 Add smoke tests: the package imports, `adscout --version` prints the metadata version, the metadata carries the upload-guard classifier and no licence, and a test that opens a socket is blocked.

## 3. Gate and checks

- [ ] 3.1 Add `scripts/gate.py` running the twelve steps in order, reporting every step and exiting non-zero on any failure; implement the lockfile, format, lint, type, test and OpenSpec steps (with the missing-CLI hint). Test the orchestrator's keep-going and exit behaviour.
- [ ] 3.2 Constitution copy check with tests for an edited rule, a missing rule, reordered rules, a version-line drift and a "Last amended" mismatch.
- [ ] 3.3 Verbatim digest check with tests for a changed byte and a missing file.
- [ ] 3.4 Secrets scan, `.env` ignore and untracked check, and `.secrets-allowlist`, with tests that build fake keys at runtime for each known format, a generic long-literal assignment, a tracked `.env`, and an allowlisted entry; findings never print the value.
- [ ] 3.5 Commit message check with tests for a valid subject, a bad subject, and an exempt merge commit, using a temporary Git repository.
- [ ] 3.6 Documentation checks (local links, pointer frontmatter, skill name and description) with tests for a broken link, pointer drift and a name/folder mismatch.

## 4. Offline evaluation scaffold

- [ ] 4.1 Add pydantic case and result models under `evals/`, export them to `evals/schemas/case.schema.json` and `result.schema.json`, and add a test that fails when an export differs from its committed file.
- [ ] 4.2 Add the runner (pytest parametrized over cases) writing one record per case and repetition to `evals/runs/<run_id>.jsonl`, with explained nulls and `source: "fixture"`; validate each record with `jsonschema`; never overwrite or delete a run file.
- [ ] 4.3 Add the synthetic scaffold case set (normal, edge and deliberately failing cases) and wire the gate's evaluation step to pass only when normal and edge pass and the deliberately failing case fails; test that a wrongly passing deliberately failing case fails the step.

## 5. Documents and phase close

- [ ] 5.1 Replace every "TBD in Phase 0" with the gate command (PROJECT.md, AGENTS.md, CLAUDE.md, WORKFLOW.md, `openspec/config.yaml`, AI_OPS.md, next-phase skill) and point AI_OPS.md's evaluation rows at `evals/`.
- [ ] 5.2 Fresh-clone acceptance: clone the branch twice, with `core.autocrlf=true` and `false`; run `uv sync --locked` and the gate in each; record the commands and outcomes in HANDOFF.md.
- [ ] 5.3 Run `uv run --locked pip-audit` (owner gate decision of 2026-10-17); record the date, result and any ignored finding with its reason and recheck date in HANDOFF.md.
- [ ] 5.4 Code review of the branch diff against these requirements, tasks and the design's non-negotiables check; fix findings in new commits and record the outcome in HANDOFF.md.
