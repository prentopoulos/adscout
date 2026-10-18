"""The evaluation harness: formats, retention and the gate step's pass rule."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import ROOT
from evals import runner
from evals.evaluators import Outcome
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


def test_non_boolean_synthetic_flag_is_rejected(tmp_path: Path) -> None:
    bad = scaffold_case(case_id="yes-flag", synthetic="yes")
    with pytest.raises(ValueError, match="case 'yes-flag' is invalid"):
        load_cases(write_cases(tmp_path / "cases.jsonl", bad))


def test_line_that_is_not_json_is_rejected_by_line(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(scaffold_case()) + '\n{"case_id": "x", bad json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"cases\.jsonl:2: line is not valid JSON"):
        load_cases(path)


def test_repeated_case_id_is_rejected(tmp_path: Path) -> None:
    first = write_cases(tmp_path / "a.jsonl", scaffold_case())
    again = write_cases(tmp_path / "b.jsonl", scaffold_case())
    with pytest.raises(ValueError, match=r"b\.jsonl:1: .* repeats the case ID at a\.jsonl:1"):
        load_cases(first, again)


def test_raw_line_separator_inside_a_case_loads(tmp_path: Path) -> None:
    case = scaffold_case(tags=["one" + chr(0x2028) + "line"])
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    (loaded,) = load_cases(path)
    assert loaded.tags == case["tags"]


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


def test_malformed_input_is_an_error_not_a_fail() -> None:
    case = load_cases(SCAFFOLD)[2]  # deliberately failing: it must fail for the right reason
    assert case.label == "deliberately_failing"
    malformed = case.model_copy(update={"inputs": {"entering": "5", "kept": 3, "dropped": 2}})
    record = run_case(malformed, new_run_id(), repetition=0)
    assert record.status == "error"
    assert "must be a number" in record.validation.detail
    assert not expected_outcome_met(case.label, record.status)


def test_outcome_that_cannot_be_recorded_is_an_error_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics: dict[str, Any] = {"entering": "five"}
    unrecordable = ("test", lambda inputs: Outcome("pass", "looks fine", metrics))
    monkeypatch.setitem(runner.EVALUATORS, "funnel_conservation", unrecordable)
    record = run_case(load_cases(SCAFFOLD)[0], new_run_id(), repetition=0)
    assert record.status == "error"
    assert record.validation.outcome == "not_run"
    assert record.validation.detail.startswith("outcome not recordable")
    assert record.metrics == {}


def test_input_hash_names_the_case_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    case = load_cases(SCAFFOLD)[0]
    expected = runner.sha256_hex(json.dumps(case.inputs, sort_keys=True).encode("utf-8"))

    def mutating(inputs: dict[str, Any]) -> Outcome:
        inputs.pop("dropped")
        return Outcome("pass", "changed its inputs")

    monkeypatch.setitem(runner.EVALUATORS, "funnel_conservation", ("test", mutating))
    record = run_case(case, new_run_id(), repetition=0)
    assert record.input_hash == expected
    assert "dropped" in case.inputs


def test_null_metric_needs_a_reason() -> None:
    (case,) = [case for case in load_cases(SCAFFOLD) if case.case_id.endswith("zero-qualified")]
    record = run_case(case, new_run_id(), repetition=0)
    data = record.model_dump(mode="json", by_alias=True)
    assert data["metrics"] == {"expected": None, "reported": None}
    assert data["null_reasons"]["metrics.expected"] == "undefined at zero qualified leads"
    del data["null_reasons"]["metrics.reported"]
    with pytest.raises(ValidationError, match=r"null fields without a reason.*metrics\.reported"):
        type(record).model_validate(data)


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


def test_eval_step_runs_every_case_file_in_a_folder(tmp_path: Path) -> None:
    folder = tmp_path / "cases"
    folder.mkdir()
    write_cases(folder / "a.jsonl", scaffold_case(case_id="first"))
    write_cases(folder / "b.jsonl", scaffold_case(case_id="second"))
    result = run_eval_step(folder, tmp_path / "runs")
    assert result.returncode == 0, result.stdout
    (run,) = (tmp_path / "runs").iterdir()
    records = [json.loads(line) for line in run.read_text(encoding="utf-8").splitlines()]
    assert [record["case_id"] for record in records] == ["first", "second"]


def test_eval_step_fails_on_empty_case_folder(tmp_path: Path) -> None:
    (tmp_path / "cases").mkdir()
    result = run_eval_step(tmp_path / "cases", tmp_path / "runs")
    assert result.returncode != 0, result.stdout
    assert "contains no cases" in result.stdout + result.stderr
