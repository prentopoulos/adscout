# Scaffold the repository tree

## Purpose and inputs

Act as the repository architect. Determine a maintainable file layout from the requested agent pattern and stack, with clear ownership of domain logic, runtime integration, tests, infrastructure and governance artifacts.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: `spec`, resolved architecture, tool contracts, prompt manifest, project repository conventions and declared delivery platform. The default output is a scaffold plan; create actual application files only when that implementation is part of the caller's request.

## Procedure

1. Inspect the target repository before proposing changes. Reuse its package manager, application boundaries, CI conventions, licenses and ownership rules. Identify conflicts instead of overwriting files.
2. Choose layout by the declared language/framework and agent pattern. Keep a simple agent in one application package. Introduce separate orchestration/worker packages only when the dependency graph justifies them.
3. Separate deterministic business rules from model orchestration and external adapters. Give each tool a typed contract and implementation boundary. Keep prompts versioned, runtime configuration validated, secrets external, and environment-specific IaC configuration isolated.
4. Include evaluation fixtures, contract/access tests, deployment/runbook documentation, and registry metadata. Use synthetic fixtures and sanitized example configuration. Keep generated artifacts, caches and credentials out of version control unless specifically required for review.
5. Provide a path manifest with purpose, owner role, source skill, generation status, dependencies and tests. Define local startup/evaluation commands only when the actual framework version and project tooling support them. Otherwise describe required command behavior without inventing working scripts.
6. For a requested scaffold implementation, create only justified directories and working minimal files, then check imports/configuration using the pinned stack. Mark any stub explicitly and do not describe an empty tree as a running application.

## Example Python layout

```text
project/
  README.md
  pyproject.toml
  <chosen-package-manager-lockfile>
  .env.example
  .gitignore
  src/project_agent/
    agent.py              # Framework agent entry point
    service.py            # Authenticated API/runtime adapter
    config.py             # Validated non-secret configuration
    domain/               # Deterministic business and freshness rules
    tools/                # Typed contracts and scoped source adapters
    policies/             # Authorization/redaction/budget integration
    telemetry/            # Filtered event emission
  prompts/
  tests/
    unit/
    contracts/
    access/
  evals/
    datasets/
    rubrics/
    config/
  infra/
    modules/
    environments/
  ci/                     # Relocate to actual CI provider convention
  catalog/
  docs/
    architecture.md
    operations.md
    release.md
```

This is one language-specific example, not a required stack or code already present. For other languages, preserve responsibilities while using native package, test and source conventions. Add `retrieval/` only for RAG/hybrid, durable worker code only for async work, and multi-agent handoff modules only for a multi-agent design.

## Outputs and inventory assistant example

Write `artifacts/repo-scaffold.md`, `artifacts/repo-file-manifest.yaml`, and the shared result envelope under stem `scaffold_repo_tree`. For the inventory assistant, place inventory arithmetic in `domain/`, tool adapters in `tools/`, and the advisory prompt under `prompts/`. A UI package is justified only if building the inventory-list/detail experience is explicitly in scope.

## Completion checks

Every selected capability has an implementation home and validation location. The layout avoids unnecessary services, respects existing files, and distinguishes proposed paths, generated files, stubs and verified behavior.

## Progression to production

Give domain rules, tool boundaries, validated configuration and relevant checks stable homes from the prototype. Record production gaps with owners and recheck triggers; add deployment/operations structure when needed instead of baking prototype bypasses into shared runtime logic.
