# Current handoff

Read PROJECT.md and current user instructions. Inspect actual Git/OpenSpec state before resuming.

## Current checkpoint

Agent skills and OpenSpec were set up on 2026-10-17 from the new_project_agent_setup kit.
Fresh project on branch `main`; no phase has started and no OpenSpec change exists. The local
job playbook PDF is the source of the project idea and is gitignored.

## Implemented behavior

None yet. No application code, dependencies, accounts or credentials exist.

## Verification and next action

Setup verification on 2026-10-17: kit validator passed; 26 verbatim copies match the kit
manifest; scoped template scan clean; Claude pointers match their canonical skills; local
Markdown links resolve; `openspec validate --all --strict` reports nothing to validate. No AI
runtime evaluation exists (not_run): there is no system bundle yet.

Next action: clear the context and run `/next-phase` to start Phase 0. Its grilling settles
the stack (PROJECT.md §4 playbook proposal), then Phase 0 builds the toolchain, lockfile, the
local gate with the constitution copy check, smoke checks and the offline evaluation scaffold.
