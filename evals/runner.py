"""Load cases, run them through their evaluators and record one result per case."""

import copy
import hashlib
import json
import platform
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from adscout.ids import agent_version, code_version
from evals.evaluators import EVALUATORS
from evals.models import Case, Label, ResultRecord, Status, Validation, started_now

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "evals" / "cases"
RUNS = ROOT / "evals" / "runs"
SCHEMAS = ROOT / "evals" / "schemas"

NULL_REASONS = {
    "gen_ai.request.model": "scaffold cases run no model step",
    "prompt_version": "scaffold cases run no prompt",
    "gen_ai.usage.input_tokens": "scaffold cases run no model step",
    "gen_ai.usage.output_tokens": "scaffold cases run no model step",
    "cost_usd": "scaffold cases run no model step",
    "segment": "scaffold cases belong to no segment",
    "seed_list_hash": "scaffold cases use no seed list",
    "icp_config_hash": "scaffold cases use no segment config",
    "labelled_set_version": "no owner-labelled set; scaffold cases are synthetic",
    "attribution_rule": "no revenue figure",
}


def case_files(path: Path) -> list[Path]:
    """The case file itself, or every `*.jsonl` file in a folder of cases."""
    return sorted(path.glob("*.jsonl")) if path.is_dir() else [path]


def load_cases(*paths: Path) -> list[Case]:
    """Every case in the JSON Lines files; an invalid or repeated case fails the load, naming it."""
    cases: list[Case] = []
    seen: dict[str, str] = {}
    for path in paths:
        # Newlines only: str.splitlines also breaks at U+2028 and similar characters, which
        # JSON allows raw inside a string.
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
            if not line.strip():
                continue
            where = f"{path.name}:{number}"
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{where}: line is not valid JSON: {error}") from error
            name = raw.get("case_id", "?") if isinstance(raw, dict) else "?"
            try:
                # Strict, like the committed schema: "yes" is not a boolean.
                case = Case.model_validate(raw, strict=True)
            except ValidationError as error:
                raise ValueError(f"{where}: case {name!r} is invalid: {error}") from error
            if case.case_id in seen:
                raise ValueError(f"{where}: case {name!r} repeats the case ID at {seen[name]}")
            seen[case.case_id] = where
            cases.append(case)
    return cases


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_outcome_met(label: Label, status: Status) -> bool:
    """Normal and edge cases must pass; a deliberately failing case must fail."""
    return status == ("fail" if label == "deliberately_failing" else "pass")


def run_case(case: Case, run_id: str, repetition: int, root: Path = ROOT) -> ResultRecord:
    revision, dirty = code_version(root)
    # Hash the case's inputs before evaluating, and evaluate a copy, so the hash names them.
    input_hash = sha256_hex(json.dumps(case.inputs, sort_keys=True).encode("utf-8"))
    started = started_now()
    clock = time.perf_counter()
    status: Status
    metrics: dict[str, float | int | None] = {}
    metric_null_reasons: dict[str, str] = {}
    version = "unknown"
    if case.evaluator not in EVALUATORS:
        status, detail = "error", f"unknown evaluator {case.evaluator!r}"
    else:
        version, evaluate = EVALUATORS[case.evaluator]
        try:
            outcome = evaluate(copy.deepcopy(case.inputs), copy.deepcopy(case.expected))
            status, detail, metrics = outcome.status, outcome.detail, outcome.metrics
            metric_null_reasons = outcome.null_reasons
        except Exception as error:  # an evaluator crash is an error result, not a lost run
            status, detail = "error", repr(error)
    duration = time.perf_counter() - clock
    fields: dict[str, Any] = {
        "run_id": run_id,
        "case_id": case.case_id,
        "case_set": case.case_set,
        "case_set_version": case.case_set_version,
        "step": case.step,
        "layer": case.layer,
        "label": case.label,
        "synthetic": case.synthetic,
        "split": case.split,
        "repetition": repetition,
        "input_hash": input_hash,
        "code_revision": revision,
        "code_dirty": dirty,
        "lock_digest": sha256_hex((root / "uv.lock").read_bytes()),
        "agent_version": agent_version(revision, dirty),
        "evaluator": case.evaluator,
        "evaluator_version": version,
        "config": {"case_set": case.case_set, "case_set_version": case.case_set_version},
        "budgets": {"model_calls": 0},
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "status": status,
        "validation": Validation(
            outcome=status if status in ("pass", "fail") else "not_run", detail=detail
        ),
        "metrics": metrics,
        "started_at": started,
        "duration_s": duration,
        "source": "fixture",
        "null_reasons": NULL_REASONS
        | {f"metrics.{key}": reason for key, reason in metric_null_reasons.items()},
    }
    fields |= dict.fromkeys(NULL_REASONS)
    try:
        return ResultRecord.model_validate(fields)
    except ValidationError as error:  # an outcome that cannot be recorded is an error result
        fields |= {
            "status": "error",
            "validation": Validation(outcome="not_run", detail=f"outcome not recordable: {error}"),
            "metrics": {},
        }
        return ResultRecord.model_validate(fields)


class RunFile:
    """One run's records, in a new file that is never overwritten."""

    def __init__(self, runs_dir: Path, run_id: str) -> None:
        runs_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.path = runs_dir / f"{run_id}.jsonl"
        with self.path.open("x", encoding="utf-8"):
            pass

    def append(self, record: ResultRecord) -> dict[str, Any]:
        data: dict[str, Any] = record.model_dump(mode="json", by_alias=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(data, ensure_ascii=False) + "\n")
        return data
