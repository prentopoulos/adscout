# Current handoff

Read PROJECT.md and current user instructions. Inspect actual Git/OpenSpec state before resuming.

## Current checkpoint

Phase 0 (toolchain, local gate, offline evaluation scaffold) is complete on branch
`phase-0/toolchain-and-gate`, OpenSpec change `phase-0-toolchain-and-gate`, and is merged
into `main` only on the owner's go-ahead. Its grilling decisions are in PROJECT.md §4 and the
change's design. The local job playbook PDF is the source of the project idea and is
gitignored.

## Implemented behavior

- Package `adscout` 0.1.0 (Python 3.13, src layout, `uv.lock`); `adscout --version`.
- Gate `uv run --locked python scripts/gate.py`, twelve steps:
  1. lockfile;
  2. format;
  3. lint;
  4. types;
  5. tests with coverage;
  6. constitution copies;
  7. verbatim digests;
  8. secrets;
  9. commit messages;
  10. documentation;
  11. evaluation scaffold;
  12. OpenSpec validation.
- Offline evaluation harness in `evals/`:
  - case and result formats as committed JSON Schema;
  - run records in gitignored `evals/runs/`, never deleted;
  - cited runs in `evals/evidence/`;
  - a synthetic scaffold case set.
- `.gitattributes` keeps the 26 verbatim skill files byte-exact, and every other text file is
  LF. The duplicated Codex `source-command-opsx-*` folders are removed.

## Verification (2026-10-18)

- **Gate:** all 12 steps pass at a7712ad. 65 tests; coverage of `src/` and `scripts/` 88%;
  6 scaffold cases.
- **Fresh clones** of the branch, one with `core.autocrlf=true` and one with `false`: in each,
  `uv sync --locked` and the gate pass all 12 steps. `git ls-files --eol` shows the verbatim
  files as `i/crlf w/crlf` and other files as LF.
- **Planted violations** in a scratch clone:
  - An unused import plus an unannotated function failed format, lint and types.
  - A dependency added without relocking made `uv run --locked` refuse ("The lockfile at
    `uv.lock` needs to be updated"). The lockfile step also failed when the gate ran under the
    venv's Python directly.
  - Every other planted violation (rule copy, verbatim byte, fake keys, socket, commit
    subject, links, wrongly passing deliberately failing case, empty case file) is a unit test.
- **Evidence run:** `evals/evidence/phase-0-20261018T041403Z-d367b0.jsonl` at a7712ad, clean
  tree. 4 cases pass, and the 2 deliberately failing cases fail as required. It is a synthetic
  self-test of the harness, not a model evaluation; no AI runtime evaluation exists yet
  (not_run).
- **Dependency audit:** on 2026-10-18, `uv run --locked pip-audit --skip-editable` (pip-audit
  2.10.1) reported "No known vulnerabilities found". `adscout` was skipped as editable. The
  owner's gate decision for this audit is in PROJECT.md §6.
- **Code review:** an inline review of the branch diff against the specs, tasks and the
  design's non-negotiables check, done by the implementing agent, so it is not independent.
  - Finding fixed in a7712ad: an empty case file passed the evaluation step vacuously.
  - The stale-lockfile scenario wording was corrected to match the behaviour.
  - No independent `/code-review` has been run.

## Findings and limitations

- **Setup commit 3de5377** stored the 26 verbatim skill files with LF line endings, so their
  committed bytes did not match the source manifest. The setup note "26 verbatim copies match"
  held for the working tree only. Fixed in d1cf7cf.
- **Temp folder:** in the agent's shell on this PC, `%TEMP%\pytest-of-Peter` (created
  2026-10-04) denies access, so pytest's `tmp_path` fails there. Runs set
  `PYTEST_DEBUG_TEMPROOT` to a short writable folder. Deleting that folder may fix it. Keep
  the temp root short: Windows' 260-character path limit breaks the digest tests under deep
  folders.
- **Ruff 0.17** also formats Markdown code blocks, so `pyproject.toml` limits ruff to Python
  files.
- **The commit check** compares the branch with `main` or `origin/main`. Commits made directly
  on `main` are not checked, and Git's default `Revert "…"` subjects fail it.
- **The secrets scan** knows this stack's key prefixes. Confirm each prefix when its account
  is created behind the accounts gate.
- **Coverage** has no threshold until Phase 1.

## Next action

After the owner approves the Phase 0 merge: clear the context and run `/next-phase` to start
Phase 1 (thin end-to-end pipeline with stub steps, PROJECT.md §6). Its grilling decides the
database and run-record design, checking them against the Phase 5 tracing and Phase 6
dashboard candidates (PROJECT.md §4).
