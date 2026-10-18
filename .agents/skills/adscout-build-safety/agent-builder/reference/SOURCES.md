# Technical references and portability

These prompts are project-neutral engineering guidance. Their examples, layouts, thresholds and schema are proposed local conventions. Use current documentation for the actual stack when implementing code. Product availability or public documentation does not establish compatibility with your selected versions or compliance with your requirements.

## Optional public references

- [Google ADK documentation](https://adk.dev/): agent/tool/runtime concepts for projects that select ADK. Other frameworks and custom orchestration are supported by the skill procedures.
- [Google Cloud agent hosting guidance](https://docs.cloud.google.com/run/docs/ai-agents): one hosted runtime option when evaluating GCP.
- [Google Cloud budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets): provider-specific budget behavior. Treat notification mechanisms and enforced usage limits as separate controls; verify the selected provider's behavior.
- [ADK evaluation documentation](https://github.com/google/adk-docs/blob/main/docs/evaluate/index.md): one framework's integration of response and tool-trajectory evaluation.
- [ADK security documentation](https://github.com/google/adk-docs/blob/main/docs/safety/index.md): one framework's treatment of agent security controls.

These links were carried forward from the source draft's September 9, 2026 review; they have not been freshly checked during this generalization. They are optional platform references, not required dependencies or frozen release specifications. Use official documentation for whichever provider/framework your project chooses.

## Project-owned sources

Prefer the current repository, explicit owner requirements, API contracts and verified project policies. A small project can keep architecture decisions, tool manifests, acceptance criteria and release evidence in version control. Shared catalogs and external policy portals are used only when the project has them and needs them.

Keep private source documents and credentials in the target project's approved storage. This library contains no private email, original company architecture images, internal portal links or company-specific policy requirements.
