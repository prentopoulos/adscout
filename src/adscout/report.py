"""Plain-text run summaries for the terminal: the run list and one run's funnel."""

import sqlite3


def list_runs(connection: sqlite3.Connection, segment_id: str | None = None) -> str:
    query = (
        "SELECT run_id, kind, segment_id, status, validation_outcome, source, started_at FROM runs"
    )
    params: tuple[str, ...] = ()
    if segment_id:
        query += " WHERE segment_id = ?"
        params = (segment_id,)
    rows = connection.execute(query + " ORDER BY started_at, run_id", params).fetchall()
    if not rows:
        return "no runs yet"
    lines = [
        f"{'run':<24} {'kind':<9} {'segment':<20} {'status':<11} {'check':<8} {'source':<7} started"
    ]
    for row in rows:
        lines.append(
            f"{row['run_id']:<24} {row['kind']:<9} {row['segment_id']:<20} {row['status']:<11} "
            f"{row['validation_outcome']:<8} {row['source']:<7} {row['started_at']}"
        )
    return "\n".join(lines)


def funnel(connection: sqlite3.Connection, run_id: str) -> str:
    run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        raise LookupError(f"no run {run_id}")
    lines = [
        f"{run['kind']} run {run_id} | segment {run['segment_id']} | {run['status']} | "
        f"check {run['validation_outcome']}",
        f"source of data: {run['source']}"
        + (
            " (scripted stub steps; no live data, not pipeline assessments)"
            if run["source"] in ("stub", "fixture")
            else ""
        ),
        "",
        f"{'#':>2}  {'step':<9} {'impl':<5} {'entering':>8} {'kept':>5} {'exited':>6}  exits",
    ]
    for step in connection.execute(
        "SELECT * FROM step_runs WHERE run_id = ? ORDER BY seq", (run_id,)
    ).fetchall():
        reasons = connection.execute(
            "SELECT coalesce(reason, flag) AS code, count(*) AS n FROM lead_step_outcomes "
            "WHERE run_id = ? AND step = ? AND (reason IS NOT NULL OR flag IS NOT NULL) "
            "GROUP BY code ORDER BY code",
            (run_id, step["step"]),
        ).fetchall()
        notes = ", ".join(f"{row['code']} {row['n']}" for row in reasons)
        counts = [step["entering"], step["kept"], step["exited"]]
        shown = ["-" if value is None else str(value) for value in counts]
        status = "" if step["status"] == "succeeded" else f" [{step['status']}]"
        lines.append(
            f"{step['seq']:>2}  {step['step']:<9} {step['implementation']:<5} {shown[0]:>8} "
            f"{shown[1]:>5} {shown[2]:>6}  {notes}{status}".rstrip()
        )
    if run["error_category"]:
        lines.append(f"\nerror: {run['error_category']}: {run['error_detail']}")
    return "\n".join(lines)
