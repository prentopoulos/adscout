## Context

The repository holds project documents, skills and an empty OpenSpec tree (setup commit
3de5377, Phase 2 cost TBDs in 7b4b3ec). There is no code. The PC has uv 0.13.0 with
uv-managed CPython 3.13.16, Node 22.19.0 and OpenSpec 1.6.0. It has no make, just or Docker.
Git uses `core.autocrlf=true`, and there is no remote.

The setup commit stored the 26 verbatim skill files with LF line endings. Their working copies
are CRLF and match the source manifest, but the committed blobs do not, so a clone without
line-ending conversion would fail the digest check.

Phase 0 grilling ran on 2026-10-17 in two informed-answerer passes. The second pass added a
completeness check and weighed the alternatives for each decision. The owner accepted every
recommendation. Q9, a whole-stack review now, was dropped in favour of a look-ahead rule in
PROJECT.md §4.

## Goals / Non-Goals

**Goals:**
- A fresh clone bootstraps with `uv sync --locked` and passes the gate, both with
  `core.autocrlf=true` and with `core.autocrlf=false`.
- Every gate check is shown to bite: a test plants a violation and expects a failure.
  Violations covered: a drifted rule copy, a changed verbatim byte, a fake key, a test opening
  a socket, lint and type errors, and a bad commit subject.
- The evaluation scaffold writes a run record that validates against its JSON Schema, labelled
  synthetic, with explained nulls.
- No "TBD in Phase 0" placeholder remains.
- The code review under WORKFLOW.md is complete.

These are the phase's acceptance evidence (owner, grilling Q11).

**Non-Goals:** pipeline code, config schema, database, model SDK or calls, network in tests,
CI workflow, Docker and dashboard (owner, grilling Q11). Structural guards for rules whose code
does not exist yet are mapped to their phases below, not built (owner, grilling Q2).

## Decisions

Each line says who decided it. Owner calls are marked **owner**. Settled answers give their
basis (fact, recorded or default), with sources retrieved 2026-10-17.

1. **Python 3.13** (`.python-version` 3.13, `requires-python = ">=3.13"`). Fact: 3.13.16 is
   installed through uv and has security support to 2029-10 (devguide.python.org). The other
   versions lose:
   - 3.14 makes uv download an interpreter;
   - 3.15 (2026-10-09) lacks wheels for duckdb 1.5.6 and PyYAML 6.0.3;
   - 3.12 is older for no gain.
2. **uv with a committed `uv.lock`**, `[tool.uv] required-version = ">=0.13"`, build backend
   `uv_build>=0.13.0,<0.14`. Default: it is already installed, and the lock is cross-platform
   and hashed. poetry, pdm, hatch, pip-tools and pipenv each need an install.
3. **Package and command `adscout`**, src layout, `[project.scripts] adscout =
   "adscout.cli:main"` using argparse (**owner**). The PyPI names `adscout` and `ad-scout` are
   both unclaimed.
4. **Version 0.1.0** in `[project].version`, read through `importlib.metadata`. SemVer 0.y.z,
   with a minor bump per merged phase. The §5 "agent version" tag is defined in Phase 1.
   Default: VCS-derived versions need tags and another build backend.
5. **ruff for lint and format, mypy strict**, both pinned in the dev group and run with
   `uv run`. ruff's rule set includes S (with S105–S107) and TID. mypy runs strict on `src/`,
   `scripts/` and `evals/`, with the pydantic plugin. Default. The alternatives lose:
   - pyrefly 1.4.0 is stable but younger;
   - ty 0.0.89 is beta;
   - pyright needs Node.

   The global ruff 0.16.0 is not used.
6. **pytest** with pytest-socket (`--disable-socket` in `addopts`) and pytest-cov (report
   only, no threshold until Phase 1). Default. unittest lacks fixtures and parametrize.
7. **Gate:** `uv run --locked python scripts/gate.py`, an orchestrator that uses only the
   standard library. Its checks live in `scripts/checks/` as plain functions that pytest
   imports (`pythonpath = ["scripts"]`). They may use dev-group packages (PyYAML for
   `openspec/config.yaml`). Default. just and make are absent, and poethepoet, nox and tox add
   a DSL for one sequence. The steps, in order:
   1. lockfile (`uv lock --locked`);
   2. format;
   3. lint;
   4. types;
   5. tests (unit and smoke);
   6. constitution copy check;
   7. verbatim digests;
   8. secrets scan;
   9. commit messages;
   10. documentation checks;
   11. evaluation scaffold;
   12. OpenSpec validation.

   The gate keeps going after a failure and exits non-zero at the end.
8. **Constitution copy check.** It extracts:
   - the bullets between PROJECT.md's `**Version …**` line and `### Amending`;
   - the bullets under AGENTS.md `## Non-negotiables`;
   - the `- ` lines after `Version …` in the parsed `context` of `openspec/config.yaml`.

   It joins continuation lines, collapses whitespace and compares the lists exactly, then
   checks the version lines and "Last amended" against the newest amendment-log row. Default.
   The alternatives lose:
   - a byte-exact comparison fails by design, because config.yaml has one bullet per line;
   - generating the copies would rewrite owner-amended files.
9. **Line endings.** `.gitattributes` holds:
   - `* text=auto eol=lf`;
   - `.agents/skills/adscout-build-safety/agent-builder/** -text`;
   - `.agents/skills/grilling/** -text`.

   Then `git add --renormalize .` runs once, and the digest step re-checks the manifest. Fact:
   `git ls-files --eol` shows `i/lf w/crlf` for the verbatim files, and the HEAD blob of
   `grilling/SKILL.md` hashes to 10ff989e…, not the manifest's d8067332…. SETUP.md forbids
   normalizing those files, and per-machine `core.autocrlf` does not reach other clones.
10. **Secrets scan**, written in the repo (**owner** for the Phase 0 scope, grilling Q2;
    mechanism is a default). It covers:
    - tracked files plus untracked files that are not ignored (`git ls-files -co
      --exclude-standard`);
    - prefixes `sk-ant-`, `sk-proj-`, `pat-na1-`/`pat-eu1-`, `sk-lf-`/`pk-lf-`, `AKIA`, and
      `-----BEGIN … PRIVATE KEY`;
    - KEY/TOKEN/SECRET/PASSWORD assignments of 20 or more literal characters;
    - a committed `.secrets-allowlist` (path, line hash, reason);
    - a check that `.env` is ignored and untracked.

    Findings print the file and line only. Tests build fake keys at runtime, so the test
    sources never contain one. The alternatives lose:
    - detect-secrets 1.5.0 (2024-05-06) is stale, has no Anthropic, HubSpot or Langfuse
      detectors and flags lockfile hashes;
    - gitleaks, betterleaks and trufflehog are binary installs on the owner's PC;
    - ggshield needs a GitGuardian account.
11. **Commit messages.** Every non-merge commit in `main..HEAD` matches
    `type(scope)!: subject`, where the type is one of feat, fix, docs, chore, refactor, test,
    build, ci, perf, style or revert. Recorded: WORKFLOW.md § Delivery. commitizen and
    commitlint add a dependency or Node.
12. **Documentation checks.** Local Markdown links resolve, outside code fences and excluding
    external URLs. Pointer frontmatter equals the canonical skill's, and each skill's
    frontmatter name equals its folder. Recorded: WORKFLOW.md § Verification by scope lists
    these as manual checks.
13. **OpenSpec step** runs `openspec` from PATH (`openspec.cmd` on Windows), prints its
    version, and fails with an `npm install -g @fission-ai/openspec` hint when it is missing.
    OpenSpec stays at 1.6.0; upgrading is an owner call. Default. Running npx would download
    it on every run.
14. **Evaluation harness on pytest** under `evals/` (**owner**, grilling Q3).
    - **Formats:** case and result formats are pydantic models exported to committed
      `evals/schemas/*.schema.json` (Draft 2020-12). A test fails when an export differs from
      its committed file.
    - **Validation:** records are validated with `jsonschema`, independently of the pydantic
      code that wrote them.
    - **Field names:** model and token fields borrow OpenTelemetry GenAI names
      (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`);
      no OpenTelemetry dependency is added.
    - **Runs:** pytest parametrizes over the cases. Each test asserts the expected outcome
      (pass for normal and edge, fail for deliberately failing), and the record keeps the raw
      status.
    - **Alternatives:**
      - Inspect AI 0.3.281 is the strongest for model evaluations, but nothing exists to
        evaluate before Phase 2, so it is reconsidered then.
      - promptfoo and DeepEval send telemetry by default.
15. **Run records** go in gitignored `evals/runs/<run_id>.jsonl`, one file per run, never
    deleted or overwritten. Runs cited as phase evidence are committed under
    `evals/evidence/` (**owner**, grilling Q5).
16. **Dependency audit.** `uv run --locked pip-audit` runs at phase close, outside the gate,
    with the result in HANDOFF.md. A finding blocks the merge unless it is ignored with a
    reason and a recheck date (**owner**, grilling Q12; gate decision in PROJECT.md §6).
    The alternatives lose:
    - `uv audit` is a preview feature;
    - safety needs an account;
    - osv-scanner is a binary install.
17. **Skill folders.** Delete the six `.agents/skills/source-command-opsx-*` folders, which
    are byte-identical to `~/.agents/skills`. Gitignore `.agents/skills/source-command-*/`, and
    keep the `openspec-*` folders in `.agents/skills` and `.codex/skills` (**owner**, grilling
    Q4).
18. **Other defaults:**
    - No pre-commit hook, because the gate runs before each task commit.
    - No CI until Phase 5, which is recorded in PROJECT.md §6.
    - No licence; the `Private :: Do Not Upload` classifier stays in until the publishing
      gate.
    - Decisions live in PROJECT.md and the OpenSpec designs, with no ADR folder.
    - All check code opens files with `encoding="utf-8"`.

Recorded elsewhere: each later stack piece is decided in its phase, with a look-ahead check
against what it constrains (**owner**, grilling Q10; PROJECT.md §4). Minutes per account joins
the §3 targets (**owner**, grilling Q6).

## Rule, check and phase map

Each §5 rule, the check that enforces it and the phase that builds that check, with the
OWASP Top 10 for LLM Applications 2025 entry it addresses.

| §5 rule | Check | Phase | OWASP |
|---|---|---|---|
| Secrets in `.env`, never printed or committed | Secrets scan, `.env` ignore check, ruff S105–S107 | 0 | LLM02 |
| No fabricated results; labels; preserve failed runs | Run records with source and nulls with reasons; retained `evals/runs/` | 0 (harness), each phase | LLM09 |
| Operator resolves ⛔ gates | Process rule; gate decisions recorded in PROJECT.md §6 | All | — |
| No message to a real person; one send path with refusals | Send-function refusal tests; import ban on mail and HTTP-post libraries outside it | 4 | LLM06 |
| Synthetic personal data only | Schema and fixture checks on contact fields | 1 | LLM02 |
| Research agent read-only, capped, web content untrusted | Tool-list test, step and page caps, planted-injection cases | 3 | LLM01, LLM06, LLM10 |
| Every brief claim cited; drafts use only brief and media-kit facts | Citation and draft rule checks | 3–4 | LLM09 |
| One CRM writer, dedupe, owned fields, logged | CRM-writer contract tests; import ban outside it | 4 | LLM06 |
| Lead ID and immutable source fields | Schema test | 1 | — |
| Revenue simulated and labelled | Dashboard and data label checks | 6 | — |

## Non-negotiables check

- **Secrets:** Phase 0 holds no secret and needs none. The scan and the `.env` check enforce the
  rule from now on.
- **No fabrication; preserve failed runs:**
  - gate output is printed as measured;
  - evaluation records carry `source: "fixture"` and explained nulls;
  - scaffold cases are labelled synthetic and not described as model evaluation;
  - run files are never deleted.
- **⛔ gates:**
  - Spend, accounts, sends and deployment are untouched.
  - Live reads: tests have no network, and the only network use is the phase-close
    pip-audit, under the recorded owner decision.
  - Publishing: no remote and no push, and the classifier guards against an upload.
- **Remaining rules:** they govern code that does not exist yet and are mapped above.

AI behavior: none changes in Phase 0. The result format names the system bundle fields
(code revision, lock digest, case-set and evaluator versions, model, prompt and agent
versions), so later model evaluations bind to a complete version from the start.

## Risks / Trade-offs

- **[Renormalizing rewrites every text blob once]** → It lands in its own first commit, and the
  fresh-clone test with both `core.autocrlf` settings proves the result.
- **[The home-made secrets scan misses unknown key formats]** → Each provider's prefix is
  confirmed when its account is created behind the accounts gate. A maintained binary scanner
  stays an owner opt-in.
- **[`evals/runs/` grows with every gate run]** → Files are small, and the owner chose
  retention over cleanup. A later phase can add an archive step if size matters.
- **[pytest-socket can block local IPC some libraries use]** → No such library is in Phase 0.
  A later need is allowed per test with a reason.
- **[The gate depends on a global OpenSpec CLI]** → The step prints the version and an install
  hint, and fails rather than skipping.

## Open Questions

None for Phase 0. The model cost and access items stay TBD for Phase 2 (PROJECT.md §4).
