# Design PII redaction and sensitive-data handling

## Purpose and inputs

Act as the data-protection designer. Derive masking, minimization, retention, and handling rules from declared sensitivity and the approved policy, covering the full agent data path.

Read [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md). Read [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for required controls and lifecycle/capability triggers; personal ownership does not waive the baseline. Recheck affected prior exemptions before expanding scope. Apply its project profile and control-applicability rules: required evidence must be verified; optional organizational processes may be marked not applicable with a reason. Honor authorization already provided by the project owner. Inputs: `spec`, data contracts, field inventory, tool/prompt design, memory plan, telemetry consumers, and project classification/retention policy. The classifications below are proposed vocabulary and must be mapped to the project scheme.

## Procedure

1. Inventory fields at ingress, retrieval, model context, tool arguments/results, session/memory storage, cache, evaluation datasets, and telemetry. Include identifiers and combinations that can identify a person or reveal commercial/operational information.
2. For every field and destination, assign one action: allow for an authorized purpose, drop, mask, tokenize, aggregate, or block. Record why the field is needed, who may receive it, retention/deletion rules, and the governing policy. Keep operationally necessary values available only at the boundary that needs them.
3. Minimize fields before model submission. Use schema-aware handling plus approved detectors for free text. Apply output filtering before delivery and before logging. Document detector limitations, languages/formats, false positives and false negatives.
4. Where linkage is necessary, use scoped opaque tokens with protected mappings and limited lifetime. If pseudonymous correlation uses keyed hashing, manage the key separately and scope it appropriately; plain hashing is not guaranteed anonymization. Treat reversible or linkable tokens as sensitive.
5. Apply user isolation and retention to stored conversations, memory, caches, documents, embeddings, backups and evaluation artifacts. Specify deletion propagation and backup-expiry handling. Do not assign a production retention period when the authoritative value is unknown.
6. Define unavailable-filter behavior by data class and destination. For confidential/restricted model transfer or disclosure, stop the affected operation if its required protection cannot run; return a safe explanation without logging the original payload. Test the entire path for bypasses.

## Proposed handling matrix

| Class | Draft default |
|---|---|
| Public | Validate declared public status; still remove secrets and unintended identifiers |
| Internal | Limit context to task-relevant fields; keep routine telemetry payload-free |
| Confidential | Allowlist fields, mask/tokenize unnecessary identifiers, require approved processing destinations and retention |
| Restricted | Require explicit permitted processing path and policy evidence before model transfer; otherwise block that transfer |

## Outputs

- `artifacts/data-handling-policy.yaml`: field/destination/action rules, detector/tokenization settings, retention, failure behavior and policy references.
- `artifacts/redaction-cases.jsonl`: synthetic inputs, expected protected fields, allowed operational fields, destination and expected outcome.
- Shared result envelope using skill stem `design_pii_redaction`.

## Inventory assistant worked example

Preserve authorized item/location identifiers, timestamps, quantities and units when required for analysis. Exclude customer names, addresses, contact details and unnecessary order-level identifiers from model context. A free-text note containing a synthetic phone number must be filtered before both inference and logging. Inventory-level aggregates may remain confidential; removing names does not make operational data public.

## Completion checks

Every sensitive field has a destination-specific disposition. Tests cover structured fields, free text, errors, logs, caches and stored history. Unknown retention and policy references remain explicit, and masking is never represented as proof of complete anonymization.

## Progression to production

Reassess classification, processing destinations, retention and deletion before replacing fixtures with real data or enabling memory. Include provider retention, logs, caches and backups; memory disabled alone does not justify a no-retention exemption.
