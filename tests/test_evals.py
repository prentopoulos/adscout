"""The evaluation harness: formats, retention and the gate step's pass rule."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import ROOT
from evals.models import SCHEMA_FILES, schema_text
from evals.runner import (
    NULL_REASONS,
    SCHEMAS,
    RunFile,
    expected_outcome_met,
    load_cases,
    new_run_id,
    run_case,
)

SCAFFOLD = ROOT / "evals" / "cases" / "scaffold.jsonl"


def scaffold_case(**changes: Any) -> dict[str, Any]:
    first = json.loads(SCAFFOLD.read_text(encoding="utf-8").splitlines()[0])
    return {**first, **changes}


def write_cases(path: Path, *cases: dict[str, Any]) -> Path:
    path.write_text("".join(json.dumps(case) + "\n" for case in cases), encoding="utf-8")
    return path


def run_eval_step(cases: Path, runs: Path) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "pytest", "evals", "-q", "-p", "no:cacheprovider"]
    command += ["--cases", str(cases), "--runs-dir", str(runs)]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("filename", sorted(SCHEMA_FILES))
def test_committed_schema_matches_model(filename: str) -> None:
    committed = (SCHEMAS / filename).read_text(encoding="utf-8")
    assert committed == schema_text(SCHEMA_FILES[filename]), (
        "schema file is stale; run `uv run python -m evals export-schemas`"
    )


def test_scaffold_has_each_label_and_is_synthetic() -> None:
    cases = load_cases(SCAFFOLD)
    assert {case.label for case in cases} == {"normal", "edge", "deliberately_failing"}
    assert all(case.synthetic for case in cases)


def test_case_without_label_is_rejected_by_name(tmp_path: Path) -> None:
    bad = scaffold_case(case_id="no-label")
    del bad["label"]
    with pytest.raises(ValueError, match="case 'no-label' is invalid"):
        load_cases(write_cases(tmp_path / "cases.jsonl", bad))


def test_case_without_synthetic_flag_is_rejected(tmp_path: Path) -> None:
    bad = scaffold_case(case_id="no-flag")
    del bad["synthetic"]
    with pytest.raises(ValueError, match="case 'no-flag' is invalid"):
        load_cases(write_cases(tmp_path / "cases.jsonl", bad))


def test_null_without_reason_is_rejected() -> None:
    record = run_case(load_cases(SCAFFOLD)[0], new_run_id(), repetition=0)
    data = record.model_dump(mode="json", by_alias=True)
    del data["null_reasons"]["cost_usd"]
    with pytest.raises(ValidationError, match="null fields without a reason"):
        type(record).model_validate(data)


def test_unknown_evaluator_is_an_error_result() -> None:
    case = load_cases(SCAFFOLD)[0].model_copy(update={"evaluator": "missing"})
    record = run_case(case, new_run_id(), repetition=0)
    assert record.status == "error"
    assert record.validation.outcome == "not_run"


def test_phase_0_record_explains_its_nulls() -> None:
    record = run_case(load_cases(SCAFFOLD)[0], new_run_id(), repetition=0)
    data = record.model_dump(mode="json", by_alias=True)
    assert data["source"] == "fixture"
    assert data["gen_ai.request.model"] is None
    assert data["null_reasons"] == NULL_REASONS


def test_run_file_is_never_overwritten(tmp_path: Path) -> None:
    run_id = new_run_id()
    RunFile(tmp_path, run_id)
    with pytest.raises(FileExistsError):
        RunFile(tmp_path, run_id)


@pytest.mark.parametrize(
    ("label", "status", "met"),
    [
        ("normal", "pass", True),
        ("edge", "pass", True),
        ("normal", "fail", False),
        ("deliberately_failing", "fail", True),
        ("deliberately_failing", "pass", False),
        ("deliberately_failing", "error", False),
    ],
)
def test_expected_outcome_rule(label: Any, status: Any, met: bool) -> None:
    assert expected_outcome_met(label, status) is met


def test_eval_step_passes_on_scaffold(tmp_path: Path) -> None:
    result = run_eval_step(SCAFFOLD, tmp_path / "runs")
    assert result.returncode == 0, result.stdout
    (run,) = (tmp_path / "runs").iterdir()
    assert len(run.read_text(encoding="utf-8").splitlines()) == 6


def test_eval_step_fails_on_empty_case_file(tmp_path: Path) -> None:
    cases = tmp_path / "cases.jsonl"
    cases.write_text("", encoding="utf-8")
    result = run_eval_step(cases, tmp_path / "runs")
    assert result.returncode != 0, result.stdout
    assert "contains no cases" in result.stdout + result.stderr


def test_eval_step_fails_when_deliberately_failing_case_passes(tmp_path: Path) -> None:
    wrongly_passing = scaffold_case(case_id="wrongly-passing", label="deliberately_failing")
    cases = write_cases(tmp_path / "cases.jsonl", wrongly_passing)
    result = run_eval_step(cases, tmp_path / "runs")
    assert result.returncode == 1, result.stdout
    (run,) = (tmp_path / "runs").iterdir()  # the failed run's record is kept
    assert json.loads(run.read_text(encoding="utf-8"))["status"] == "pass"
