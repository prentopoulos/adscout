"""Run each case, record its result and check the record independently."""

from typing import Any

from jsonschema import Draft202012Validator

from evals.models import Case
from evals.runner import RunFile, expected_outcome_met, run_case


def unexplained_nulls(record: dict[str, Any]) -> list[str]:
    fields = [key for key, value in record.items() if value is None]
    metrics = [f"metrics.{key}" for key, value in record["metrics"].items() if value is None]
    return [key for key in fields + metrics if key not in record["null_reasons"]]


def test_case(case: Case, run_file: RunFile, result_validator: Draft202012Validator) -> None:
    record = run_case(case, run_file.run_id, repetition=0)
    data = run_file.append(record)

    assert sorted(error.message for error in result_validator.iter_errors(data)) == []
    assert unexplained_nulls(data) == []
    assert expected_outcome_met(case.label, record.status), (
        f"{case.case_id}: {case.label} case got {record.status} ({record.validation.detail})"
    )
