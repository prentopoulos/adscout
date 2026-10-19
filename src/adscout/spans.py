"""Spans that are not calls: a lead's step and each agent invocation (design decision 36).

A lead's trace ID is its UUIDv7 as hex. Its step span is a root; agent spans nest under it,
and model and source calls nest under either. Spans are written with the step's other rows.
"""

import sqlite3
from dataclasses import dataclass, fields
from typing import ClassVar, Literal

from adscout.db.connection import utc_now
from adscout.llm.adapter import new_span_id, trace_id_for

Operation = Literal["step", "invoke_agent"]
SpanStatus = Literal["succeeded", "failed"]


@dataclass
class Span:
    """An open span; `close` turns it into the row the run writes."""

    run_id: str
    lead_id: str
    step: str
    operation: Operation
    parent_span_id: str | None = None
    agent_name: str | None = None
    span_id: str = ""
    started_at: str = ""

    def __post_init__(self) -> None:
        self.span_id = self.span_id or new_span_id()
        self.started_at = self.started_at or utc_now()

    def child(self, agent_name: str) -> "Span":
        return Span(self.run_id, self.lead_id, self.step, "invoke_agent", self.span_id, agent_name)

    def close(self, status: SpanStatus, detail: str) -> "SpanRecord":
        return SpanRecord(
            span_id=self.span_id,
            trace_id=trace_id_for(self.lead_id),
            parent_span_id=self.parent_span_id,
            run_id=self.run_id,
            lead_id=self.lead_id,
            step=self.step,
            operation=self.operation,
            agent_name=self.agent_name,
            status=status,
            detail=detail,
            started_at=self.started_at,
            ended_at=utc_now(),
        )


def step_span(run_id: str, lead_id: str, step: str) -> Span:
    return Span(run_id, lead_id, step, "step")


@dataclass(frozen=True)
class SpanRecord:
    """One `spans` row."""

    write_order: ClassVar[int] = 0

    span_id: str
    trace_id: str
    parent_span_id: str | None
    run_id: str
    lead_id: str
    step: str
    operation: str
    agent_name: str | None
    status: str
    detail: str
    started_at: str
    ended_at: str

    def insert(self, connection: sqlite3.Connection) -> None:
        columns = [item.name for item in fields(self)]
        connection.execute(
            f"INSERT INTO spans ({', '.join(columns)}) "  # noqa: S608
            f"VALUES ({', '.join('?' * len(columns))})",
            tuple(getattr(self, name) for name in columns),
        )
