# Current handoff

Read PROJECT.md and current user instructions. Inspect actual Git/OpenSpec state before resuming.

## Current checkpoint

Phase 0 (toolchain, local gate, offline evaluation scaffold) is complete on branch
`phase-0/toolchain-and-gate`, OpenSpec change `phase-0-toolchain-and-gate` (archived), and is
merged into `main` only on the owner's go-ahead. A `/code-review` of the branch ran on
2026-10-18 and its findings are resolved (Verification below). Its grilling decisions are in
PROJECT.md §4 and the change's design. The local job playbook PDF is the source of the
project idea and is gitignored.

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
  12. OpenSpec validation, with OpenSpec's usage telemetry turned off.
- Offline evaluation harness in `evals/`:
  - case and result formats as committed JSON Schema;
  - the evaluation step runs every `evals/cases/*.jsonl` file; a malformed or repeated case
    fails the load, and malformed inputs are recorded as errors, not failures;
  - run records in gitignored `evals/runs/`, never deleted;
  - cited runs in `evals/evidence/`;
  - a synthetic scaffold case set.
- `.gitattributes` keeps the 26 verbatim skill files byte-exact, and every other text file is
  LF. The duplicated Codex `source-command-opsx-*` folders are removed.

## Verification (2026-10-18)

- **Gate:** all 12 steps pass at 293a781, the last code commit. 93 tests; coverage of `src/`
  and `scripts/` 90%; 6 scaffold cases. (Before the review fixes: a7712ad, 65 tests, 88%.)
- **Fresh clones** of the branch at a7712ad, one with `core.autocrlf=true` and one with
  `false` (the line-ending setup has not changed since): in each,
  `uv sync --locked` and the gate pass all 12 steps. `git ls-files --eol` shows the verbatim
  files as `i/crlf w/crlf` and other files as LF.
- **Planted violations** in a scratch clone at a7712ad:
  - An unused import plus an unannotated function failed format, lint and types.
  - A dependency added without relocking made `uv run --locked` refuse ("The lockfile at
    `uv.lock` needs to be updated"). The lockfile step also failed when the gate ran under the
    venv's Python directly.
  - Every other planted violation (rule copy, verbatim byte, fake keys, socket, commit
    subject, links, wrongly passing deliberately failing case, empty case file) is a unit test.
- **Evidence run:** `evals/evidence/phase-0-20261018T045448Z-6ea193.jsonl` at 293a781, clean
  tree, evaluators version 2. 4 cases pass, and the 2 deliberately failing cases fail as
  required. A separate script checked each record against the committed schema, recomputed
  each outcome and input hash from the case file, and found every null explained. It is a
  synthetic self-test of the harness, not a model evaluation; no AI runtime evaluation exists
  yet (not_run). The earlier run, `phase-0-20261018T041403Z-d367b0.jsonl` at a7712ad
  (evaluators version 1), stays as its record.
- **Dependency audit:** on 2026-10-18, `uv run --locked pip-audit --skip-editable` (pip-audit
  2.10.1) reported "No known vulnerabilities found". `adscout` was skipped as editable. The
  review fixes changed neither `uv.lock` nor `pyproject.toml`, so the audit still applies. The
  owner's gate decision for this audit is in PROJECT.md §6.
- **Code review:**
  - First, an inline review by the implementing agent against the specs, tasks and the
    design's non-negotiables check. It fixed, in a7712ad, an empty case file passing the
    evaluation step vacuously, and corrected the stale-lockfile scenario wording.
  - Then `/code-review` of `main...phase-0/toolchain-and-gate`, run by a separate agent
    session (same model, fresh context, not a human review). It reported 15 findings, plus 7
    candidates cut by its cap, and reproduced most findings against the old code.
  - Fixed, each with regression tests:
    - 298de4a: the gate's OpenSpec calls sent a usage event on every run.
    - 7869c47: the secrets scan missed names that only contain a secret word, UTF-16 files
      and staged copies, and miscounted lines at U+2028.
    - 6898a60: the evaluation harness could lose a record or let a malformed input pass as a
      deliberately failing case. Case loading was loose, ran only `scaffold.jsonl` and split
      lines at U+2028. Null metrics carried no reason, and the input hash was taken after
      evaluating.
    - 9007e45: the link check misparsed angle brackets, parentheses, indented fences, HTML
      comments and reference links; it accepted ignored files and wrong-case paths; and bad
      frontmatter YAML crashed it.
    - 293a781: the commit check crashed on a subject containing U+2028.
  - Answered without a change: the record's `validation.outcome` repeats the evaluator's
    verdict. In the scaffold the evaluator is the independent check: deterministic code that
    recomputes the invariant from the case data, separate from whatever produced that data.
    Phase 0 has no producing step, so status and validation agree. Revisit this when Phase 1
    pipeline steps get a status of their own.
  - Not changed:
    - No date-time format check for records: it needs a new dependency
      (`rfc3339-validator`), and pydantic's `AwareDatetime` already enforces the format on
      write.
    - The gate imports PyYAML at load: `uv run --locked` syncs the dev group first.
    - Commit types stay lowercase; the `Revert "…"` limitation is listed below.
    - Cleanups: git and the lockfile hash run once per case, and the scaffold runs twice per
      gate. Revisit when case counts grow in Phase 5.

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
  is created behind the accounts gate. It now matches any name containing KEY, TOKEN, SECRET
  or PASSWORD, so a long identifier such as a `primary_key` value can be flagged; accept such
  a finding in `.secrets-allowlist` with a reason.
- **The link check** fails on links to gitignored files, such as the local playbook PDF.
- **OpenSpec telemetry:** the gate turns it off. Direct `openspec` commands run by agents and
  skills (`openspec list`, `openspec status` and others) still send a usage event to
  edge.openspec.dev unless `OPENSPEC_TELEMETRY=0` or `DO_NOT_TRACK=1` is set. Setting it for
  the user account or in `.claude/settings.json` is the owner's call; not set as of
  2026-10-18.
- **Coverage** has no threshold until Phase 1.

## Next action

After the owner approves the Phase 0 merge: clear the context and run `/next-phase` to start
Phase 1 (thin end-to-end pipeline with stub steps, PROJECT.md §6). Its grilling decides the
database and run-record design, checking them against the Phase 5 tracing and Phase 6
dashboard candidates (PROJECT.md §4).
