"""pytest wiring for the evaluation harness: case parametrization and the run file."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from evals.runner import CASES, RUNS, SCHEMAS, RunFile, case_files, load_cases, new_run_id


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("adscout evaluation")
    group.addoption(
        "--cases", default=str(CASES), help="case file, or folder of *.jsonl case files, to run"
    )
    group.addoption("--runs-dir", default=str(RUNS), help="folder for run record files")


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "case" in metafunc.fixturenames:
        path = Path(str(metafunc.config.getoption("--cases")))
        cases = load_cases(*case_files(path))
        if not cases:
            # pytest would skip an empty parameter set and exit 0: a vacuous pass.
            raise pytest.UsageError(f"{path} contains no cases")
        metafunc.parametrize("case", cases, ids=[case.case_id for case in cases])


@pytest.fixture(scope="session")
def run_file(request: pytest.FixtureRequest) -> RunFile:
    return RunFile(Path(str(request.config.getoption("--runs-dir"))), new_run_id())


@pytest.fixture(scope="session")
def result_validator() -> Draft202012Validator:
    schema = json.loads((SCHEMAS / "result.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)
