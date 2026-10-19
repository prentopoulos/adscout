"""The record-and-replay cache: live responses and fetched pages, kept so a run can be replayed.

The cache is its own gitignored SQLite file, `data/cache.db` (design decision 20). A live
run records each model response under the run's ID, the request's hash (model, prompt
version, tools and canonical input) and how many times that request had been seen in the
run, so three identical scoring requests replay as their three different answers. A replay
names the run it reproduces; its calls cost nothing and keep the original cost. Fetched page
bodies live only here, never in the pipeline database (decision 12).
"""

import json
import sqlite3
import threading
from collections import Counter
from decimal import Decimal
from pathlib import Path

from anthropic.types import Message

from adscout.db.connection import utc_now
from adscout.llm.adapter import Mode, ModelCallFailed, ModelRequest, Sent

DEFAULT_CACHE = Path("data") / "cache.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_responses (
    run_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
    occurrence INTEGER NOT NULL CHECK (occurrence >= 1),
    response_json TEXT CHECK (response_json IS NULL OR json_valid(response_json)),
    cost_usd TEXT NOT NULL,
    error_category TEXT,
    error_detail TEXT,
    fallback_allowed INTEGER CHECK (fallback_allowed IN (0, 1)),
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (run_id, request_sha256, occurrence),
    CHECK ((response_json IS NULL) = (error_category IS NOT NULL))
) STRICT;
CREATE TABLE IF NOT EXISTS pages (
    run_id TEXT NOT NULL,
    url TEXT NOT NULL,
    occurrence INTEGER NOT NULL CHECK (occurrence >= 1),
    http_status INTEGER NOT NULL,
    content_type TEXT,
    body BLOB NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (run_id, url, occurrence)
) STRICT;
"""


class ReplayMiss(ModelCallFailed):
    """The run being replayed has no recorded answer for this request."""

    def __init__(self, detail: str) -> None:
        super().__init__("replay_miss", detail, fallback_allowed=False)


class ReplayCache:
    """One cache file, shared by the threads of one run behind a lock."""

    def __init__(self, path: Path = DEFAULT_CACHE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            path, autocommit=True, timeout=5, check_same_thread=False
        )
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.executescript(SCHEMA)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._connection.close()

    def store(
        self,
        run_id: str,
        key: str,
        occurrence: int,
        message: Message | None,
        cost_usd: Decimal,
        failure: ModelCallFailed | None = None,
    ) -> None:
        """One live answer: a response with its cost, or the error the call ended with."""
        with self._lock:
            self._connection.execute(
                "INSERT INTO model_responses (run_id, request_sha256, occurrence, "
                "response_json, cost_usd, error_category, error_detail, fallback_allowed, "
                "recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    key,
                    occurrence,
                    message.model_dump_json() if message else None,
                    str(cost_usd),
                    failure.category if failure else None,
                    failure.detail if failure else None,
                    int(failure.fallback_allowed) if failure else None,
                    utc_now(),
                ),
            )

    def load(self, run_id: str, key: str, occurrence: int) -> tuple[Message, Decimal]:
        """The recorded response, or the recorded error raised again."""
        with self._lock:
            row = self._connection.execute(
                "SELECT response_json, cost_usd, error_category, error_detail, "
                "fallback_allowed FROM model_responses "
                "WHERE run_id = ? AND request_sha256 = ? AND occurrence = ?",
                (run_id, key, occurrence),
            ).fetchone()
        if row is None:
            raise ReplayMiss(
                f"run {run_id} recorded no answer #{occurrence} for request {key[:12]}"
            )
        response_json, cost_usd, category, detail, fallback_allowed = row
        if response_json is None:
            raise ModelCallFailed(category, detail, fallback_allowed=bool(fallback_allowed))
        return Message.model_validate(json.loads(response_json)), Decimal(cost_usd)

    def responses(self, run_id: str) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT count(*) FROM model_responses WHERE run_id = ?", (run_id,)
            ).fetchone()
        return int(row[0])


class Occurrences:
    """How many times each request hash has been seen in this run (1 for the first)."""

    def __init__(self) -> None:
        self._seen: Counter[str] = Counter()
        self._lock = threading.Lock()

    def next(self, key: str) -> int:
        with self._lock:
            self._seen[key] += 1
            return self._seen[key]


class Recorder:
    """Stores each live answer of one run, errors included, in the order the run saw them."""

    def __init__(self, cache: ReplayCache, run_id: str) -> None:
        self.cache = cache
        self.run_id = run_id
        self.occurrences = Occurrences()

    def response(self, key: str, message: Message, cost_usd: Decimal) -> None:
        self.cache.store(self.run_id, key, self.occurrences.next(key), message, cost_usd)

    def failure(self, key: str, failure: Exception) -> None:
        # A budget stop ends the run; replaying past it is not a goal, so only call errors.
        if isinstance(failure, ModelCallFailed):
            occurrence = self.occurrences.next(key)
            self.cache.store(self.run_id, key, occurrence, None, Decimal(0), failure)


class ReplayTransport:
    """Answers from a recorded run, in the order that run saw each request; never the network."""

    mode: Mode = "replay"

    def __init__(self, cache: ReplayCache, source_run_id: str) -> None:
        self.cache = cache
        self.source_run_id = source_run_id
        self.occurrences = Occurrences()

    def send(self, request: ModelRequest, key: str) -> Sent:
        message, original = self.cache.load(self.source_run_id, key, self.occurrences.next(key))
        return Sent(message, original_cost_usd=original)
