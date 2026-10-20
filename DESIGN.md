# Workspace design

Mode: Operate. A researcher works at a desktop during an ordinary workday, comparing
company evidence and drafts. The look is the familiar SaaS standard (owner, 2026-10-19),
held to the level of Linear or Attio: neutral greys, one blue accent (#3358d4) for primary
actions, selection and progress, white panels with 1px borders and a faint shadow on a
#f6f6f7 page, a light grey sidebar with counts, and the system UI font at 14px with
tabular numerals.

Status is a square-cornered pill with a plain label (Needs review, Approved, Near miss),
toned blue, green, amber, red or grey. No dots, no explanatory captions; codes never appear
raw. A plain "Synthetic data" badge marks the demo; revenue is always labelled simulated.

The ranked table leads into a review panel: the draft on the left, keyed source quotes on
the right, approve and reject at the foot of the draft. The sandbox inbox follows on the
same page; there is no funnel or footer. The page has no scripts and no inline styles (the
content policy forbids them), so bar widths use 5% step classes. Under 860px the sidebar
becomes a top row, review columns stack and the table scrolls in its own panel.
