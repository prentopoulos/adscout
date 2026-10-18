"""AdScout's local quality gate: run every check in order, then summarise.

Run it with `uv run --locked python scripts/gate.py`. Every step runs even after a failure,
so one run reports everything that is wrong; the exit code is non-zero if any step failed.
"""

import io
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from checks import commits, constitution, digests, docs, secrets

ROOT = Path(__file__).resolve().parent.parent
OPENSPEC_INSTALL = "npm install -g @fission-ai/openspec@1.6.0"
# OpenSpec sends a usage event on every command unless told not to; the gate stays offline.
OPENSPEC_NO_TELEMETRY = {"OPENSPEC_TELEMETRY": "0", "DO_NOT_TRACK": "1"}
# Line coverage of src/ and scripts/; raise it as coverage grows, never lower it (owner).
COVERAGE_THRESHOLD = 90
TEST_ARGS = (
    "pytest",
    "--cov=src",
    "--cov=scripts",
    "--cov-report=term",
    f"--cov-fail-under={COVERAGE_THRESHOLD}",
)


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[], bool]


def command(*args: str) -> Callable[[], bool]:
    def run() -> bool:
        print("$ " + " ".join(args), flush=True)
        return subprocess.run(list(args), cwd=ROOT, check=False).returncode == 0

    return run


def python_module(*args: str) -> Callable[[], bool]:
    # The project's own interpreter, so the tools pinned in uv.lock run, not global ones.
    return command(sys.executable, "-m", *args)


def problems(check: Callable[[Path], list[str]]) -> Callable[[], bool]:
    def run() -> bool:
        found = check(ROOT)
        for problem in found:
            print("  " + problem)
        return not found

    return run


def openspec() -> bool:
    executable = shutil.which("openspec")
    if executable is None:
        print(f"  openspec is not on PATH; install it with: {OPENSPEC_INSTALL}")
        return False
    env = os.environ | OPENSPEC_NO_TELEMETRY
    version = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, env=env, check=False
    ).stdout.strip()
    print(f"  OpenSpec {version}", flush=True)
    validate = [executable, "validate", "--all", "--strict"]
    return subprocess.run(validate, cwd=ROOT, env=env, check=False).returncode == 0


STEPS = [
    Step("lockfile", command("uv", "lock", "--locked")),
    Step("format", python_module("ruff", "format", "--check", ".")),
    Step("lint", python_module("ruff", "check", ".")),
    Step("types", python_module("mypy")),
    Step("tests", python_module(*TEST_ARGS)),
    Step("constitution copies", problems(constitution.check)),
    Step("verbatim digests", problems(digests.check)),
    Step("secrets", problems(secrets.check)),
    Step("commit messages", problems(commits.check)),
    Step("documentation", problems(docs.check)),
    Step("evaluation scaffold", python_module("pytest", "evals", "-q")),
    Step("openspec", openspec),
]


def run_steps(steps: Sequence[Step]) -> int:
    failed: list[str] = []
    for number, step in enumerate(steps, start=1):
        print(f"\n== [{number}/{len(steps)}] {step.name}", flush=True)
        try:
            passed = step.run()
        except Exception as error:  # a crashing check fails its step, not the whole gate
            print(f"  error: {error!r}")
            passed = False
        print(f"== {step.name}: {'PASS' if passed else 'FAIL'}", flush=True)
        if not passed:
            failed.append(step.name)
    print()
    if failed:
        print(f"Gate FAILED: {len(failed)} of {len(steps)} steps failed: {', '.join(failed)}")
        return 1
    print(f"Gate passed: all {len(steps)} steps.")
    return 0


def main() -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        # Piped output on Windows defaults to cp1252, which cannot print "⛔".
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    return run_steps(STEPS)


if __name__ == "__main__":
    sys.exit(main())
