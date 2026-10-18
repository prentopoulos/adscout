# Agent Builder Skills

A reusable collection of 17 Markdown prompt skills for designing, building and evaluating agent projects. Use them for personal tools, prototypes, applications and team services on the stack you choose. The original skill filenames are preserved so existing references continue to work, including `Architecturebuild.md` and `select_adk_tools.md`.

These are portable instructions you give an AI coding assistant. They are not installed automatically into an assistant's skill directory. Each file includes inputs, a procedure, output artifacts, an example and completion checks.

## Start with your project

1. Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md) and adapt [examples/inventory-assistant.spec.yaml](examples/inventory-assistant.spec.yaml). Choose a project profile, current/target lifecycle stage, capability flags, deployment target, actual tools and model, data rules, budget and success criteria. Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) before deciding that a control does not apply. Inventory planning is only a worked example; replace it with your own domain.
2. Point your assistant at the contract, the relevant skill, your project specification, and the target repository. For example:

   > Read FOUNDATION_CONTRACT.md and resolve_stack_dependencies.md. Apply them to my project specification and repository. Use the existing stack and my stated constraints. Write the requested artifacts inside my project, document assumptions, and continue with reasonable reversible decisions.

3. Run only the skills needed for the current task. A local prototype may need architecture, tool contracts, a prompt and focused evaluation. A hosted service may also need infrastructure, IAM, telemetry and release planning.
4. Use the sequence below when you need a complete workflow. Generated `artifacts/` belong inside the project you are building, not in this reusable library. Reuse current upstream artifacts and rerun affected checks when the design changes.

## Grow from personal prototype to production

Keep the technical security baseline from the first working version. Increase evidence and operating controls as exposure, capabilities and reliance grow; personal ownership never exempts a production system.

1. **Prototype:** enforce the baseline for enabled capabilities, use synthetic fixtures where practical, and record limited scope and unresolved work.
2. **Pilot:** before adding users or external exposure, verify access/data boundaries, limits, monitored failures and a tested stop/revert path.
3. **Production:** before real reliance, verify current baseline, evaluation, deployed configuration, operational ownership, maintenance and appropriate recovery evidence.

Compare [the prototype spec](examples/inventory-assistant.spec.yaml) with [the production target](examples/inventory-assistant.production-target.spec.yaml). Both retain `governance.profile: personal`. The latter activates stronger requirements and deliberately has missing evidence; it must not pass release review yet. These are separate planning examples, not completed implementations.

Architecture validation produces a baseline coverage report and lifecycle plan. Changes to capabilities invalidate affected earlier exemptions and test evidence, even when the profile is unchanged. There is no need to build production infrastructure at the prototype stage, but prototype shortcuts must not silently carry into production.

## Match process to project size

- **Personal:** you are the project owner and may fill all applicable roles. Local files can serve as the tool catalog, architecture decisions and asset registry. Formal approval workflows, cost centers, network-team reviews and organization-specific patterns are optional unless actually required. Existing user authorization remains valid.
- **Team:** use repository conventions, shared ownership and the team's actual review/release process. Only require catalogs or approval evidence that the team has made mandatory.
- **Regulated:** use the supplied applicable controls and evidence requirements. Do not infer legal obligations or certification from this profile alone; identify the governing requirements first.

Profile and application risk are independent. A personal application with payments, sensitive data or destructive write tools still needs controls for those actions. A cloud budget, service account or organization catalog is not a prerequisite for a local tool that does not use it.

No cloud or framework is mandatory. Use local hosting, GCP, Azure, AWS, another provider or an existing platform as appropriate. The tool-selection skill supports native functions, APIs and supported protocol adapters; its retained ADK filename does not require Google ADK. Version-check provider-specific code when implementing it.

## Skills and suggested order

| Order | Area | Skill | Main output |
|---|---|---|---|
| 1 | Architecture | [validate_architecture_spec.md](validate_architecture_spec.md) | Spec and pattern validation report |
| 2 | Architecture | [resolve_stack_dependencies.md](resolve_stack_dependencies.md) | Dependency decisions and proposed spec changes |
| 3 | Architecture | [Architecturebuild.md](Architecturebuild.md) | Logical/deployment views, deployment and sequence diagrams |
| 4 | Infrastructure | [design_iac_blueprint.md](design_iac_blueprint.md) | Resource, module, network and state design |
| 5 | Infrastructure | [apply_finops_governance.md](apply_finops_governance.md) | Allocation rules, cost model and spend controls |
| 6 | Security and governance | [map_rbac_policies.md](map_rbac_policies.md) | Identity and permission matrix |
| 7 | Security and governance | [assess_threat_vectors.md](assess_threat_vectors.md) | Threat register and control tests |
| 8 | Observability and data protection | [design_pii_redaction.md](design_pii_redaction.md) | Data handling and redaction policy |
| 9 | Observability and data protection | [configure_telemetry_schema.md](configure_telemetry_schema.md) | Event schema, measures and dashboards |
| 10 | Tools | [select_adk_tools.md](select_adk_tools.md) | Requirement-to-tool selection manifest |
| 11 | Tools | [generate_tool_schema.md](generate_tool_schema.md) | Tool contracts and runtime adapter mappings |
| 12 | Asset management | [standardize_system_prompt.md](standardize_system_prompt.md) | Versioned system prompt and behavior cases |
| 13 | Repository and delivery | [scaffold_repo_tree.md](scaffold_repo_tree.md) | Repository layout and file responsibilities |
| 14 | Evaluation and release | [generate_eval_metrics.md](generate_eval_metrics.md) | Evaluation plan, dataset contract and judge rubric |
| 15 | Evaluation and release | [define_release_gates.md](define_release_gates.md) | Promotion criteria and evidence requirements |
| 16 | Repository and delivery | [orchestrate_ci_cd.md](orchestrate_ci_cd.md) | Build/test/deploy pipeline design |
| 17 | Asset management | [generate_asset_metadata.md](generate_asset_metadata.md) | Draft discovery-catalog records |

This is a dependency guide, not a requirement to run 17 steps for every project. Tool selection can change IAM, cost, threats and architecture; update those artifacts when necessary. Set evaluation criteria before measuring a candidate. Write operations require the project's actual authorization model, not an automatically added confirmation dialog.

## What the examples mean

The worked example is an advisory inventory assistant: read stock and demand forecasts, calculate potential shortages deterministically, and explain options. The example has no purchase-order or inventory-update tool. Add such capabilities only when your project needs them, with suitable authorization, idempotency and recovery behavior.

All model names, cloud choices, budget values, quality thresholds and governance references are configurable. Unselected configuration stays unresolved until needed. A baseline subcheck may be not applicable only with evidence that its triggering capability is absent within the evaluated scope. Personal use, missing policy or unknown configuration cannot justify that exemption. Required controls and missing results cannot be waived into a pass.

[reference/SOURCES.md](reference/SOURCES.md) explains the scope of the public technical references. This collection is self-contained and has no dependency on private company documents, email attachments or diagrams.
