# Map RBAC policies

## Purpose and inputs

Act as the identity and access designer. Translate human and service identities into a least-privilege permission model at cloud, application, tool, and data boundaries.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: `spec`, component/data-flow inventory, IaC blueprint, source and tool contracts, identity standards, role catalog, and environment boundaries. Exact cloud role IDs require verification against the target service and approved applicable project policy.

For a single-user local project, document the OS/process/file boundary and tool scope. Remote-user roles and separate cloud service identities are conditional on introducing those boundaries; the example matrix below illustrates a possible hosted/team extension.

## Procedure

1. Enumerate human users, runtime identities, build/deploy identities, evaluation jobs, ingestion workers, registry publishers, auditors, and approved external agents. Create separate principals for distinct trust boundaries and environments; identify any shared identity and justify it.
2. Map each operation to the resource, minimum permission, resource scope, conditions, identity propagation, and approval owner. Distinguish an agent's cloud identity from the end user's entitlement to a particular inventory location, project group, document, or action.
3. Prefer short-lived workload authentication and approved federation. Identify secret references only for systems that require credentials. Restrict impersonation and privilege assignment to the necessary principal/resource scope. Confirm deploy permission does not imply unrestricted permission to act as any service account.
4. Enforce authorization server-side on every tool invocation and data request, including retries and delegated calls. Bind user scope to authenticated server context, not model-generated parameters. Apply RAG document ACLs before returning passages; filtering only the final answer is inadequate.
5. Separate read, advisory calculation, and operational write permissions. A human's ability to view a recommendation does not grant the agent permission to execute it. Define elevation, revocation, access review, and break-glass processes only where required by supplied policy.
6. Produce positive and negative access cases across roles, resources, environments, and session boundaries. Cover expired credentials, spoofed user scope, direct backend invocation, and overbroad deployment impersonation.

## Outputs

- `artifacts/rbac-matrix.yaml`: principal role, actual principal reference or null, resource, action, proposed/verified permission, condition, environment, evidence and owner.
- `artifacts/access-tests.md`: allowed/denied cases and expected enforcement location; implementation status clearly marked.
- Shared result envelope using skill stem `map_rbac_policies`.

## Inventory assistant worked example

| Principal role | Proposed permitted access | Boundary |
|---|---|---|
| Inventory planner | View recommendations for authorized inventory locations | Application + source entitlement |
| Agent runtime | Invoke approved model route and read scoped inventory/forecast APIs | Workload identity + per-request user authorization |
| Evaluation job | Read synthetic or approved evaluation data | Evaluation environment only |
| Build job | Build and publish candidate artifacts | Artifact repository only |
| Deployment job | Deploy the reviewed artifact as the specific runtime principal | Target environment and exact runtime identity |

The runtime receives no inventory-record write privilege. Cloud IAM may protect the API invocation while application/source authorization separately protects individual inventory records.

## Completion checks

Every data-flow operation has an accountable identity and enforcement point. Role IDs are verified or explicitly unresolved. Negative cases cover cross-user, cross-environment and privilege-escalation paths. No `Owner`/`Editor`-style broad role is used as a shortcut for unidentified permissions.

## Progression to production

Invalidate a local single-user exemption before remote access, additional users or tenants are enabled. Test the real enforcement boundary and trusted identity propagation; retaining one project owner does not make shared user data single-user data.
