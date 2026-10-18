# Version the complete system

Use when changing behavior-bearing components or preparing a release. Complements Agent
Builder asset metadata and release gates; reuse the project's existing version record.

## Procedure

1. Identify the bundle: code revision (and dirty-tree patch digest if applicable), prompt
   content digest, model/provider ID and snapshot when available, generation settings, tool
   implementation/schema revisions, authorization policy, runtime config, dependency lock
   digest, evaluator/dataset revisions, and data/index/feature versions when used. Record
   artifact/image digests where applicable. Secret values never belong in the bundle.
2. Resolve mutable model aliases and registry tags to concrete versions at load time and
   log what actually loaded. If a provider cannot expose an immutable snapshot, record that
   limitation and schedule behavior rechecks. A Git commit alone is not a system version.
3. Separate prompt templates, tool schemas and non-secret settings from orchestration.
   Validate required variables and environment selection. Missing variables or incompatible
   schemas fail explicitly. Avoid changing Git branches inside a serving process.
4. Tie each evaluation and runtime record to the bundle ID. A change to corpus, embedding
   model, policy, routing, cache namespace or evaluator invalidates affected evidence even
   when application code is unchanged.
5. For a release, evaluate the candidate and test the packaged artifact that will run.
   Promote the same artifact; record environment differences. A successful pre-build test
   does not establish that packaging included the right model, prompts or configuration.
6. Keep a known-good compatible bundle and an exercised stop/revert procedure. Include
   state-schema, tool-contract, index and cache compatibility. Test migration/restore or
   forward recovery when rolling back code cannot undo state or external actions.

## Minimum evidence

A record linking one candidate to its exact components, check outputs and previous compatible
bundle. Demonstrate a clean environment can load the intended assets. Missing immutable
provider versions limit repeatability; recorded inputs do not guarantee identical LLM output.

Use [RELEASE_RECORD.md](../assets/RELEASE_RECORD.md) only if the project lacks an equivalent.
