# Design infrastructure-as-code blueprint

## Purpose and inputs

Act as the platform infrastructure designer. Map compute, model, data, integration and operating requirements to the project's chosen deployment target. Generate the smallest sufficient provisioning design, including network integration only where applicable.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile, control-applicability rules and existing owner authorization. Inputs: specification, validation, dependencies, component inventory, existing infrastructure conventions, and applicable cost/security constraints. Module catalogs and network-team reviews are conditional project inputs.

## Procedure

1. Identify the actual deployment target: local process/container, existing hosting platform, GCP, Azure, AWS or another provider. Reuse the existing stack. If no infrastructure provisioning is needed, record IaC as not applicable and document reproducible local setup instead.
2. Select supported provisioning tools from project constraints, such as Terraform, Pulumi, a provider-native format or an existing deployment system. Verify resource capabilities and versions for the selected provider before generating code. A service with a similar name is not automatically equivalent across providers.
3. Map each required component to a verified module or a proposed resource design with inputs, outputs, region if applicable, dependency edges, environment and owner. Reference existing shared resources explicitly. Leave required unknown IDs unresolved; personal projects can maintain their own modules rather than requiring an external catalog.
4. For IaC, design protected state, access, concurrency/locking, encryption, plan review, drift checks and recovery according to the chosen backend. Keep secret values out of committed configuration and account for sensitive values that may enter state. For a local project, specify configuration files, secret access and installation/start/stop behavior instead.
5. Specify applicable ingress, egress, DNS, authentication, TLS trust and permitted destinations. If a private network, corporate proxy, VPN or security gateway is involved, produce an integration brief with source/destination, protocols, routing, certificate behavior, credentials, limits, connectivity tests and an accountable contact. Otherwise mark external network review not applicable; do not create a fictional coordination dependency.
6. Include resource/request limits, logs, storage lifecycle, backups and deletion protection where justified. Reconcile autoscaling with downstream quotas and cost. Distinguish stateless application rollback from irreversible state migration or resource replacement.
7. Define configuration/plan validation, isolated environment checks and release prerequisites. For implementation already authorized by the user, follow the actual project workflow and environment constraints. Generating the blueprint alone does not apply infrastructure or send coordination messages.

## Capability mapping guide

| Requirement | Design question |
|---|---|
| Local utility/prototype | Can a local process, file store and existing model endpoint satisfy it? |
| Request-driven service | Does the chosen hosting platform support the required auth, latency, scale and networking? |
| Batch work | Can a job or scheduler run it to completion with bounded retries? |
| Stateful background worker | Which durable state, work ownership and restart guarantees are needed? |
| Managed agent runtime | Are framework compatibility, data handling, tools and networking supported? |
| Kubernetes | Does a real requirement justify cluster operation and its cost? |
| Model access | Local inference or an approved hosted route; a dedicated endpoint is optional |
| Sessions/retrieval | Provision only stores selected by the dependency plan |
| Secrets/artifacts/telemetry | Use the target environment's suitable mechanisms and lifecycle controls |

Product-specific mappings belong in the generated artifact after selecting the provider. No cloud product is a default requirement of this library.

## Outputs and example

Write `artifacts/iac-blueprint.yaml` with applicability, resource/module mappings or local setup, input/output contracts, state/network/environment design, limits and unresolved dependencies. Write `artifacts/network-integration.md` with the integration brief, or a concise not-applicable explanation. Write the shared result envelope using stem `design_iac_blueprint`.

For the [local inventory example](examples/inventory-assistant.spec.yaml), begin with one local runtime, scoped fixture readers and filtered development events. Memory is disabled; no session database or cloud resources are required. Resolve a model and tool contracts before claiming the application runs. Reassess network, residency, identity and cost when changing to hosted sources or inference.

## Completion checks

Every selected component has a provisioning/setup owner or existing-service reference. The implementation format matches the deployment target. State, network, identity, cost and recovery are covered where applicable. Unnecessary corporate coordination, cloud resources and approval dependencies are absent; real required gaps remain visible.

## Progression to production

Make prototype-only ingress, identity, persistence and recovery assumptions explicit. Before a production target, validate actual network exposure, privilege separation where present, state recovery and the selected release configuration against the baseline; a local/cloud label alone does not establish protection.
