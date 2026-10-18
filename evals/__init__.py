"""AdScout's offline evaluation harness.

Cases live in `evals/cases/*.jsonl`; result records go to gitignored `evals/runs/`, one file
per run, never deleted. Formats are defined in `evals.models` and exported to
`evals/schemas/*.schema.json` (`python -m evals export-schemas`). Run with `pytest evals`.
"""
