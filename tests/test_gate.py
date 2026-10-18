"""The gate runs every step, reports each, and fails if any step fails."""

from pathlib import Path

import pytest

import gate
from gate import Step, run_steps


def test_gate_runs_twelve_steps_in_order() -> None:
    assert [step.name for step in gate.STEPS] == [
        "lockfile",
        "format",
        "lint",
        "types",
        "tests",
        "constitution copies",
        "verbatim digests",
        "secrets",
        "commit messages",
        "documentation",
        "evaluation scaffold",
        "openspec",
    ]


def test_keeps_going_after_failures_and_exits_non_zero(capsys: pytest.CaptureFixture[str]) -> None:
    ran: list[str] = []

    def failing() -> bool:
        ran.append("failing")
        return False

    def crashing() -> bool:
        ran.append("crashing")
        raise RuntimeError("boom")

    def passing() -> bool:
        ran.append("passing")
        return True

    code = run_steps([Step("first", failing), Step("second", crashing), Step("third", passing)])

    out = capsys.readouterr().out
    assert code == 1
    assert ran == ["failing", "crashing", "passing"]
    assert "error: RuntimeError('boom')" in out
    assert "Gate FAILED: 2 of 3 steps failed: first, second" in out


def test_all_steps_passing_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_steps([Step("only", lambda: True)]) == 0
    assert "Gate passed: all 1 steps." in capsys.readouterr().out


def test_problem_step_prints_each_problem(capsys: pytest.CaptureFixture[str]) -> None:
    def check(root: Path) -> list[str]:
        return ["a.md: wrong", "b.md: wrong"]

    assert gate.problems(check)() is False
    out = capsys.readouterr().out
    assert "a.md: wrong" in out
    assert "b.md: wrong" in out


def test_missing_openspec_fails_with_install_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gate.shutil, "which", lambda name: None)
    assert gate.openspec() is False
    assert "npm install -g @fission-ai/openspec" in capsys.readouterr().out
