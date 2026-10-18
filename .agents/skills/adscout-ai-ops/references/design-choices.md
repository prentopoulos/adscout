# Choose the system's shape before building it

Use when designing a new AI feature or phase, or when changing its autonomy, pattern,
framework, model tier, hosting or model access. Record each choice and its reason in the
OpenSpec design; the other references cover operating what is chosen here.

## Autonomy

1. Pick the lowest rung that meets the requirement: plain code; a single model call; a
   workflow where code fixes the steps and the model does each one; an agent that chooses
   tools in a loop; several agents. Each rung up adds cost, latency, variance and actions
   the system takes on its own.
2. Use an agent only where the number or order of steps depends on what is found. Most
   products are workflows with one agentic step. Climb a rung only when evaluation shows the
   fixed structure, not prompts, tools or data, causes the failures.
3. Irreversible, external or regulated actions (sending, paying, deleting, changing access)
   stay behind a workflow step and the project's approval policy, whatever rung is chosen.

## Pattern

- Workflow patterns: prompt chaining for fixed steps with checks between them; routing when
  inputs differ in kind or difficulty; parallel calls for independent parts or voting;
  orchestrator-workers when subtasks are known only after seeing the input; evaluator-
  optimizer when a stated quality bar can be checked and revision helps.
- Agent loops: tool calling (ReAct) is the default. Plan-then-execute when a plan must be
  visible or approved; reflection only with an objective failure signal such as tests or a
  validator; generated code as the action only inside an isolated execution environment.
- Multi-agent only for parallel work, context that one window cannot hold, or roles needing
  different permissions or models. Prefer sub-agents called as tools; apply global step and
  budget caps, validate outputs between agents and keep one trace across them.

## Framework

Decide in this order: the team's language; the cloud the organization is committed to;
whether runs must pause, resume or be audited (durable state); then the shape of the work.
A provider SDK with a short loop is valid for one agent with few tools. Keep business logic in
plain typed functions, shared tools behind a stable interface such as MCP, prompts in
versioned files and evaluations calling one entry point, so the framework stays replaceable.
Verify the chosen framework's current API in its documentation before writing code.

## Model tier per job

Assign a tier per step, not per product: frontier for planning, judging and hard reasoning;
a workhorse tier for most tool loops; a fast tier for routing, extraction and summarizing
tool output; open-weight self-hosted only when data residency, offline use or sustained
volume requires it. A judge should be at least as capable as the model it grades. Reasoning
effort settings are a second dial within one model. Prove each assignment by running the same
evaluation cases on two tiers and comparing quality, cost per successful task and latency.

## Hosting and model access

Decide hosting in this order, stopping at the first constraint that applies: data that must
stay inside a network; runs that last long or wait on people (durable execution or
checkpoints); an organization-wide cloud commitment (its managed runtime or containers);
short event-driven work (functions behind a queue); otherwise one container on a managed
service. Package in a container from the first phase so moving between these is a deployment
change. Reach models directly, through the cloud provider, through a gateway when several
providers or shared budgets are involved, or self-hosted. Configure a fallback model and
include it in evaluations, since providers have outages and retire models.

## Design-time security check

List what the system can read that is private, which inputs an outsider can influence
(web pages, email, uploads, tickets, third-party tool descriptions) and every way it can send
data out or change state. When one session combines all three, remove one: restrict egress,
give untrusted content to a step with no tools, narrow the data, or require approval for the
outbound action. Record the result with the threat review in build-safety.

Done when the design names the rung, pattern, framework, tier per step, hosting, model access
with fallback, and the security check result, each with a reason or an explicit TBD.
