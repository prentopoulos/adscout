# Control agent execution and recover state

Use when tool authority, runtime state, code execution, concurrency or external tools change.
Apply the existing baseline B02-B08 at the enforcing boundary; prompts complement these controls.

## Tool and approval boundaries

Validate typed arguments/results and enforce tool allowlists and permissions outside the model.
Identity and roles come from trusted application context. Validate both read and write paths.
Bound tool results, calls, retries and the whole run; test denial and exhaustion directly.

Where the project's policy requires review, persist a proposed action before executing it.
Bind the decision to actor/tenant, canonical action arguments or digest, policy revision,
scope and expiry. Show the concrete effect to the reviewer. Test approved, rejected, expired,
modified, duplicate and unauthorized decisions. Revalidate immediately before execution.
Standing authorization remains valid within its scope; these patterns do not require a new
confirmation for every call. A model-generated approval field or shared CLI flag is not
proof of an authenticated approver.

For writes, persist an operation ID and execution status. Use backend idempotency and
reconciliation after an ambiguous timeout. A resumed workflow must not duplicate a purchase,
email, database write or other external effect.

## Untrusted content and outbound effects

Apply the design-time check in [design choices](design-choices.md) to the actual runtime:
a session that reads private data and untrusted content must not also hold an unapproved
way to send data out or change state. Treat links, images and HTTP requests as outbound
channels. Plant instructions in test inputs (pages, emails, files, tool descriptions) and
verify the system neither follows nor repeats them.

When an agent messages people (email, SMS, social posts, chat to customers):

- Identify the anti-spam, privacy and consumer-protection rules for each sender and
  recipient region (for example CASL and Quebec's Law 25 in Canada, CAN-SPAM in the US,
  GDPR in Europe). Record the owner's or legal team's consent and content rules as a
  PROJECT gate before the first automated send; these notes are not legal advice.
- Enforce required content (sender identity, contact details, a working opt-out) and
  opt-out handling in the send function, not in the prompt. Refuse sends without an approval
  reference where the policy requires one.
- Ground every factual claim about the recipient in recorded, cited inputs. Respect sending
  limits and verification of addresses; deliverability damage is an incident.
- Tests and demonstrations send only to a sandbox destination with synthetic recipients.

## Checkpoints and replay

- Add durable state only when resumption or memory is needed. Version the state schema and
  bind checkpoints to system version and trusted owner/session. Apply retention, deletion,
  access and backup rules separately from ordinary telemetry.
- Distinguish read-only reconstruction, offline replay with recorded tool outputs, and live
  re-execution. Default debugging to reconstruction or isolated replay. Live execution uses
  current authorization, budget and effect reconciliation.
- Test crash-before-write, crash-after-write-before-checkpoint, resumed approval and missing/
  incompatible checkpoints. Define recovery when a tool or model version is unavailable.
- Checkpoint persistence does not freeze external systems or make stochastic output identical.
  Preserve the original failure, change one factor and link the diagnostic run to it.
  See the [LangGraph persistence documentation](https://docs.langchain.com/oss/python/langgraph/persistence).

## Concurrent users and workers

Derive tenant/user/session keys from authenticated identity with unambiguous encoding.
Enforce ownership on every read, write, list, resume, delete and cache/retrieval path.
A namespace is a lookup mechanism, not authorization; reject user-supplied ownership claims.
Guest sessions need isolated identities if supported.

Test simultaneous different users, forged session IDs, same-session concurrent updates,
lost updates and duplicate job delivery. Choose locking, version checks or serialization for
state updates, with bounded queues and per-user fairness. A local SQLite demo is not evidence
of multi-worker capacity; measure the chosen store under the intended concurrency.

## Generated code execution

Prefer typed deterministic analysis tools when they meet the requirement. If generated code
is necessary, use an independently constrained execution environment: least privilege,
minimal approved data, bounded CPU/memory/time/output, restricted files/network and disposable
state. Verify that timeout/cancellation terminates the workload and its descendants and that
host secrets and unauthorized resources remain inaccessible.

AST blocklists, restricted globals and in-process threads are teaching controls, not a
security boundary for hostile code. A thread future timing out does not terminate its running
function; see [Python futures](https://docs.python.org/3/library/concurrent.futures.html).
Choose isolation suitable to the threat model and test escape/exhaustion cases. A container
with broad host mounts or credentials does not establish the intended boundary.

## MCP and other external tool servers

Record approved server identity, endpoint/transport, tool names, contract revisions,
credentials, allowed destinations, timeouts and result limits. Apply authorization at the
server's underlying data/action boundary as well as client filtering. Discovery does not
authorize newly advertised tools; detect contract drift before enabling them.

An unauthenticated development server is limited to its verified local boundary. For remote
restricted services, verify authentication, audience/scope and transport protections using
the actual protocol version. Keep untrusted descriptions/results from expanding authority.
Test unavailable/malformed servers, denied users, unexpected tools, oversized output and
ambiguous writes. See [MCP security guidance](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices).

Done when each enabled runtime boundary has direct negative-path tests and an evidenced
recovery path. Read-only mocks cannot prove production isolation or exactly-once effects.
