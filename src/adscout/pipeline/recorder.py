"""Run and step records: the system version, timings, counts and honest nulls.

A run's row is written and committed before its first step, so a failed or interrupted run
keeps everything it wrote. Only one run may be live at a time; a `running` row whose process
is gone is marked `interrupted` by the next run, never deleted.
"""

import hashlib
import json
import os
import platform
import sqlite3
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import Any, Literal

from adscout.db.connection import transaction, utc_now
from adscout.db.migrate import schema_version
from adscout.ids import ROOT, agent_version, code_version, new_run_id
from adscout.llm.adapter import CallSink, write_calls
from adscout.llm.budget import BudgetExhausted
from adscout.pipeline.contracts import Implementation, Outcome, Step

RunKind = Literal["pipeline", "approval", "crm_sync", "rescore", "eval"]
RunSource = Literal["stub", "fixture", "replay", "live"]
PROMPT_VERSION = "none"  # no prompt exists until Phase 2 (Phase 1 design, decision 6)
NO_MODEL_CALL = "no model call in this step"
STEP_NULL_REASONS = {
    "model": NO_MODEL_CALL,
    "input_tokens": NO_MODEL_CALL,
    "output_tokens": NO_MODEL_CALL,
    "cost_usd": NO_MODEL_CALL,
}
BUDGETS: dict[str, float] = {"model_calls": 0, "network_calls": 0}


@dataclass(frozen=True)
class Snapshot:
    """Validated content a run used, stored once per content hash."""

    kind: Literal["segment", "seed_list", "stub_script"]
    content_hash: str
    content: Any


class RunInProgress(RuntimeError):
    """Another run's process is still alive; this run did not start."""


class RunFailed(RuntimeError):
    """A step failed; the run is recorded as failed with every row it wrote."""

    def __init__(self, run_id: str, message: str) -> None:
        super().__init__(f"run {run_id} failed: {message}")
        self.run_id = run_id


def process_alive(pid: int) -> bool:
    """Whether a process with this ID exists on this machine, without signalling it."""
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        import ctypes

        query_limited_information, still_active, access_denied = 0x1000, 259, 5
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(query_limited_information, False, pid)
        if not handle:
            # Access denied means the process exists but belongs to someone else.
            return ctypes.get_last_error() == access_denied
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and (
                code.value == still_active
            )
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)  # signal 0 only checks; on POSIX it never delivers anything
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_digest() -> str:
    return hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()


@dataclass
class StepRecorder:
    """Collects one step's outcomes and deferred writes; the run commits them together.

    The step does its work, such as a model or network call, outside any transaction, and
    hands its database writes to `defer`, so the write lock is held only briefly.
    """

    step: Step
    entering: int
    outcomes: list[Outcome] = field(default_factory=list)
    writes: list[Callable[[], None]] = field(default_factory=list)

    def defer(self, write: Callable[[], None]) -> None:
        self.writes.append(write)

    @property
    def kept(self) -> int:
        return sum(outcome.outcome == "kept" for outcome in self.outcomes)

    @property
    def exited(self) -> int:
        return sum(outcome.outcome == "exited" for outcome in self.outcomes)


class Run:
    """One run of the pipeline, the approver or the CRM sync, recorded as it goes."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        kind: RunKind,
        segment_id: str,
        source: RunSource,
        snapshots: dict[str, Snapshot],
        null_reasons: dict[str, str],
        calls: CallSink | None = None,
        budgets: dict[str, float] | None = None,
    ) -> None:
        self.connection = connection
        # Model call records from the adapter, written with each step, failed ones included.
        self.calls = calls or CallSink()
        self.budgets = budgets if budgets is not None else dict(BUDGETS)
        self.kind = kind
        self.segment_id = segment_id
        self.source = source
        self.snapshots = snapshots
        self.hashes = {field: snapshot.content_hash for field, snapshot in snapshots.items()}
        self.null_reasons = null_reasons
        self.run_id = new_run_id()
        self.seq = 0
        revision, dirty = code_version()
        self.revision, self.dirty = revision, dirty
        self.package_version = version("adscout")
        self.agent_version = agent_version(revision, dirty, self.package_version)

    def start(self) -> str:
        """Refuse if another run is live; mark dead `running` runs interrupted; record this one."""
        with transaction(self.connection):
            for row in self.connection.execute(
                "SELECT run_id, pid, host FROM runs WHERE status = 'running'"
            ).fetchall():
                if row["host"] != platform.node() or process_alive(row["pid"]):
                    raise RunInProgress(
                        f"run {row['run_id']} is still running (process {row['pid']} on "
                        f"{row['host']}); wait for it to finish"
                    )
                self.connection.execute(
                    "UPDATE runs SET status = 'interrupted', ended_at = ?, "
                    "error_category = 'interrupted', error_detail = ? WHERE run_id = ?",
                    (
                        utc_now(),
                        f"process ended without finishing; seen by {self.run_id}",
                        row["run_id"],
                    ),
                )
            for snapshot in self.snapshots.values():
                self.snapshot(snapshot)
            self.connection.execute(
                "INSERT INTO runs (run_id, kind, segment_id, status, started_at, source, "
                "code_revision, code_dirty, lock_digest, package_version, agent_version, "
                "prompt_version, python_version, platform, schema_version, icp_config_hash, "
                "seed_list_hash, stub_script_hash, budgets_json, null_reasons_json, pid, host) "
                "VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.run_id,
                    self.kind,
                    self.segment_id,
                    utc_now(),
                    self.source,
                    self.revision,
                    int(self.dirty),
                    lock_digest(),
                    self.package_version,
                    self.agent_version,
                    PROMPT_VERSION,
                    platform.python_version(),
                    platform.platform(),
                    schema_version(self.connection),
                    self.hashes.get("icp_config_hash"),
                    self.hashes.get("seed_list_hash"),
                    self.hashes.get("stub_script_hash"),
                    json.dumps(self.budgets, sort_keys=True),
                    json.dumps(self.null_reasons, sort_keys=True),
                    os.getpid(),
                    platform.node(),
                ),
            )
        return self.run_id

    def snapshot(self, snapshot: Snapshot) -> None:
        """Keep the validated content a run used, once per hash."""
        self.connection.execute(
            "INSERT OR IGNORE INTO config_snapshots VALUES (?, ?, ?, ?, ?)",
            (
                snapshot.content_hash,
                snapshot.kind,
                self.segment_id,
                json.dumps(snapshot.content, sort_keys=True, ensure_ascii=False),
                utc_now(),
            ),
        )

    @contextmanager
    def step(
        self, step: Step, implementation: Implementation, entering: int
    ) -> Iterator[StepRecorder]:
        """Record a step: its row first; then its deferred writes and outcomes in one short
        transaction after the step's work is done."""
        self.seq += 1
        started_at, clock = utc_now(), time.perf_counter()
        version_label = "stub-1" if implementation == "stub" else "1"
        with transaction(self.connection):
            self.connection.execute(
                "INSERT INTO step_runs (run_id, step, seq, implementation, "
                "implementation_version, status, started_at, entering, null_reasons_json) "
                "VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?)",
                (
                    self.run_id,
                    step,
                    self.seq,
                    implementation,
                    version_label,
                    started_at,
                    entering,
                    json.dumps(STEP_NULL_REASONS, sort_keys=True),
                ),
            )
        recorder = StepRecorder(step=step, entering=entering)
        try:
            yield recorder
            with transaction(self.connection):
                write_calls(self.connection, self.calls.drain())
                for write in recorder.writes:
                    write()
                ended_at = utc_now()
                for outcome in recorder.outcomes:
                    self.connection.execute(
                        "INSERT INTO lead_step_outcomes (run_id, step, lead_id, seed_row, "
                        "outcome, reason, flag, detail, implementation, started_at, ended_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            self.run_id,
                            step,
                            outcome.lead_id,
                            outcome.seed_row,
                            outcome.outcome,
                            outcome.reason,
                            outcome.flag,
                            outcome.detail,
                            implementation,
                            started_at,
                            ended_at,
                        ),
                    )
                self.end_step(step, "succeeded", clock, recorder)
        except BaseException:
            with transaction(self.connection):
                write_calls(self.connection, self.calls.drain())
                self.end_step(step, "failed", clock, None)
            raise

    def end_step(
        self, step: Step, status: str, clock: float, recorder: StepRecorder | None
    ) -> None:
        self.total_calls(step)
        self.connection.execute(
            "UPDATE step_runs SET status = ?, ended_at = ?, duration_ms = ?, kept = ?, "
            "exited = ? WHERE run_id = ? AND step = ?",
            (
                status,
                utc_now(),
                round((time.perf_counter() - clock) * 1000),
                recorder.kept if recorder else None,
                recorder.exited if recorder else None,
                self.run_id,
                step,
            ),
        )

    def total_calls(self, step: Step) -> None:
        """A step's model, token and cost totals: the sums of its `model_calls` rows.

        Input tokens count everything the model read: uncached input, cache writes and
        cache reads, as OpenTelemetry's `gen_ai.usage.input_tokens` does.
        """
        totals = self.connection.execute(
            "SELECT count(*) AS calls, group_concat(DISTINCT model) AS models, "
            "sum(coalesce(input_tokens, 0) + coalesce(cache_write_tokens, 0) "
            "+ coalesce(cache_read_tokens, 0)) AS input_tokens, "
            "sum(coalesce(output_tokens, 0)) AS output_tokens, sum(cost_usd) AS cost_usd "
            "FROM model_calls WHERE run_id = ? AND step = ?",
            (self.run_id, step),
        ).fetchone()
        if not totals["calls"]:
            return
        models = ",".join(sorted(totals["models"].split(",")))
        self.connection.execute(
            "UPDATE step_runs SET model = ?, input_tokens = ?, output_tokens = ?, cost_usd = ?, "
            "null_reasons_json = '{}' WHERE run_id = ? AND step = ?",
            (
                models,
                totals["input_tokens"],
                totals["output_tokens"],
                totals["cost_usd"],
                self.run_id,
                step,
            ),
        )

    def finish(
        self,
        status: Literal["succeeded", "failed", "interrupted"],
        error_category: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        with transaction(self.connection):
            self.connection.execute(
                "UPDATE runs SET status = ?, ended_at = ?, error_category = ?, error_detail = ? "
                "WHERE run_id = ?",
                (status, utc_now(), error_category, error_detail, self.run_id),
            )

    @contextmanager
    def recording(self) -> Iterator["Run"]:
        """Start the run, and finish it as succeeded, failed or interrupted."""
        self.start()
        try:
            yield self
        except KeyboardInterrupt:
            self.finish("interrupted", "interrupted", "stopped by the user")
            raise
        except Exception as error:
            # A cap stop is its own category, so a report can tell it from a broken step.
            category = error.category if isinstance(error, BudgetExhausted) else "step_error"
            self.finish("failed", category, repr(error))
            raise RunFailed(self.run_id, repr(error)) from error
        self.finish("succeeded")
