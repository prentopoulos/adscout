---
name: next-phase
description: Start or resume a bounded AdScout OpenSpec phase, selecting relevant build and domain skills, implementing authorized tasks, verifying evidence, and closing only complete changes.
---

# AdScout next phase

Read [PROJECT.md](../../../PROJECT.md), [WORKFLOW.md](../../../WORKFLOW.md), and
[HANDOFF.md](../../../HANDOFF.md). Current user instructions govern the checkpoint.
Installing or reviewing skills does not itself implement the application.

## 1. Recover the actual checkpoint

Inspect working tree, branch and recent commits before changing Git state. Preserve staged,
unstaged and untracked work; resume a relevant branch without automatic stash/reset.
Use `openspec list --json`, then `openspec status --change NAME --json`. Read returned
artifact paths and active tasks. Planning artifacts marked done do not mean code exists.

Choose review/setup, authorized implementation, new phase, or verified closure:
- A review-only or skills-adoption request stays at that boundary until completed.
- An existing authorized phase resumes its current task IDs after reconciling stale facts.
- A new capability needs a scoped proposal and feasibility investigation where needed.
- A completed slice inside an unfinished phase stays a slice; leave later tasks open.

State the selected change, branch, mode and next tasks briefly. Ask only when different
plausible scopes would materially change the work.

A new phase starts in a fresh session (WORKFLOW.md § Fresh session per phase). If this session
already closed a phase, recommend clearing the context first; go on only if the owner asks.

## 2. Apply relevant skills and prerequisites

Use [adscout-build-safety](../adscout-build-safety/SKILL.md) for architecture/dependencies,
tool or adapter contracts, external calls, data handling, prompts/model behavior, run recording,
cost or phase readiness. It routes to the full 17-workflow collection. Load only workflows
needed for the slice.
Read [adscout-ai-ops](../adscout-ai-ops/SKILL.md) for system versioning, evaluation, retrieval, state, training and operations.
Use [adscout-eval-review](../adscout-eval-review/SKILL.md) for fit scores, evaluation
results, cost per qualified lead and funnel or revenue figures.
When a user-facing interface is actually in scope, read [design-skills.md](design-skills.md):
it routes to impeccable, ui-ux-pro-max, the tasteskill, 21st.dev and design-eval, and sets their
limits. Architecture diagrams are C4 as code (Structurizr DSL, Mermaid in READMEs), drawn to
the c4model.com notation guide as the showcase skill describes: create them in Phase 1 and
update them when a phase changes components, data flow or schema. Decks, walkthrough videos
and READMEs also follow the showcase skill. Load the Figma skills before any Figma tool.
Framework/API work uses current official docs or installed source. A skill recommendation
does not justify adding its framework to the application.

Distinguish technical checks, product decisions, and action authorization. Technical passes
can be established from evidence; missing evidence stays missing. Reuse accepted decisions
and existing implementation authorization. PROJECT.md §5–6 are the constitution and override
the other project documents; only the owner amends them, in a separate commit
(PROJECT.md § Amending the constitution). All PROJECT.md `⛔` gates remain operator-resolved:
surface the relevant gate and stop its dependent action; never satisfy or waive it. Unresolved
external access or budget gates do not block local development. No Git remote: do not run git push or gh.

Before proposing a new phase or capability, grill on the phase's design tree with
[grilling](../grilling/SKILL.md): goal and non-goals, acceptance evidence, PROJECT.md `TBD` items
it depends on, the §5 rules and `⛔` gates it touches or would amend, and open feasibility. Resuming an authorized phase skips
grilling unless a new material decision appears. Each round:

1. Map the tree from the project documents and checkpoint, and fix the round's frontier
   questions with their options.
2. Hand the frontier to the **informed answerer**, a subagent briefed by
   [informed-answerer.md](informed-answerer.md). It researches and answers every question and
   marks each an **owner call** or **settled**. Spawn it once per grilling (Claude Code: Agent,
   `general-purpose`) and continue that same agent each round. In a harness without subagents,
   run its pass as a separate step and tell the user.
3. Review its report: reopen the source behind each settled answer yourself, and re-apply the
   owner-call test from that file. Any answer may become an owner call; an owner call becomes
   settled only when you show its triggers do not hold and name its basis.
4. Present the owner calls in grilling's format, each with a `Why you:` line naming its
   triggers in plain words, then the settled answers as one numbered list (answer, basis,
   source) the user can reopen by number. A round with no owner calls flows straight on to the
   next frontier.

Grilling is done when the frontier is empty, every question is owner-answered or settled with a
cited basis, and the user confirms the full decision list. Record each decision in PROJECT.md
and the proposal/design with who made it: the owner, or the settled basis and source. When the
user reopens a settled answer or says an owner call did not need them, add a line to the
calibration examples in informed-answerer.md in the phase's spec commit.

Use available OpenSpec propose/update guidance to keep proposal, design, specs and tasks
coherent. Preserve existing spec-first history. For a new phase create a reviewable spec-only
`docs:` commit; with a remote, push the branch and open a draft PR (WORKFLOW.md § Pull
requests and code review). Pause where the user requested review or a material decision is unresolved;
already authorized implementation does not need repeated permission for routine refinements.

## 3. Implement the authorized slice

Use the OpenSpec apply workflow. Select task IDs and completion criteria before changing
behavior. Keep deterministic domain logic and validation separate from external adapters,
persistence and presentation. Use synthetic fixtures. Tests need no credentials or network
unless the task is an authorized live integration whose gate is resolved.
Model calls, search/fetch, enrichment, CRM and sending each sit behind one adapter with an
offline fake; tests use the fakes and recorded fixtures. The send function and the CRM
writer are the only outside write paths, and the research agent never receives either (§5).

Update the phase to In progress with its first implementation commit. Use Conventional
Commits per task or coherent task group. Mark tasks complete only after their required
behavior/checks pass. Scope changes and unresolved failures remain visible in tasks/handoff.
Do not treat the roadmap in PROJECT.md as an instruction to build all later phases now.

## 4. Verify the changed boundary

- Skills/planning: frontmatter, local links, routing consistency, source digests where
  carried over, strict OpenSpec validation, whitespace and candidate-file inspection.
  Do not claim runtime verification from these checks.
- Runtime: run `TBD in Phase 0` once implemented. Before Phase 0 finishes, inspect
  actual checks rather than assuming this command exists. Run meaningful regression/contract
  tests for the change.
- Results and claims: check outputs independently of the code that produced them. No
  exception does not prove correctness; a timeout or empty result does not prove a negative.
- Model/agent behavior: evaluate against cases fixed before measuring. An LLM judge cannot
  establish deterministic correctness. For AI products, bind results to the complete system
  version and apply current AI_OPS capability/evidence requirements; retain per-case
  regressions, insufficient samples and missing usage as visible gaps.
- UI: verify changed flows in the actual local interface with synthetic cases.
- Live adapters: apply unresolved operator gates plus budget, timing, failure and sensitive
  output checks. Offline mocks establish contracts, not live results.
- Code review: before a code change is marked ready to merge, run the review in WORKFLOW.md
  and resolve its findings. A review complements the gate and tests; it does not replace them.

Record commands, outcomes, revision/environment and material untested cases. Reuse evidence
when its scope/revision remain valid. Retain failures; don't rerun selectively for a win.

## 5. Close only what is complete

For a full phase, verify all tasks/requirements and required checks. Archive on its branch
using OpenSpec, synchronize main specs, validate again, and commit archive plus phase Done
as `chore:`. Merge only after the gate is green, the code review is resolved and the user
gives the go-ahead: with a remote, push, mark the PR ready and merge it with a merge commit;
without one, merge locally with `--no-ff`. Preserve unfinished work and unrelated files.
Delete a branch, locally and on any remote, only after verifying it is merged.
That is the clean checkpoint: stop, and tell the owner to clear the context and run
`/next-phase` for the next phase (WORKFLOW.md § Fresh session per phase).

For a partial milestone, record its completion and remaining tasks; do not archive or mark
the whole phase Done. Local verification is not hosted CI, cloud execution or deployment.

Keep personal schedules and correspondence in ignored `.local/` notes.

Update HANDOFF with current branch/change, selected scope, implemented behavior, checks,
limitations and the exact next task, worded to stay true after the merge. Nothing the next
session needs may live only in the conversation. Keep the roadmap in PROJECT, task ownership
in OpenSpec.
