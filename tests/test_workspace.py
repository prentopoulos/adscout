"""The MVP's real human workflow and enforcing boundaries, with no socket or provider."""

import io
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from adscout.config import load_segment
from adscout.db.connection import connect
from adscout.demo import FIXTURES, SEGMENT, prepare
from adscout.pipeline.run import approved_for_sync, run_crm_sync
from adscout.web import Handler, apply_action, render, source_link
from adscout.workspace import (
    ActionRefused,
    decide,
    get_draft,
    leads,
    review_digest,
    send_sandbox,
    set_deal,
    unsubscribe,
)

CONFIG = FIXTURES / "config"


@pytest.fixture(scope="module")
def seed_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("mvp") / "seed.db"
    prepare(path)
    return path


@pytest.fixture
def db(seed_db: Path, tmp_path: Path):
    path = tmp_path / "copy.db"
    shutil.copyfile(seed_db, path)
    connection = connect(path)
    yield connection, path
    connection.close()


def pending(connection: sqlite3.Connection, domain: str = "alpha.test") -> sqlite3.Row:
    row = next(row for row in leads(connection, SEGMENT) if row["domain"] == domain)
    return get_draft(connection, row["draft_id"])


def approve_and_sync(connection: sqlite3.Connection) -> str:
    row = pending(connection)
    approval = decide(connection, row["draft_id"], review_digest(row), "approved")
    run_crm_sync(connection, load_segment(CONFIG / "segments" / f"{SEGMENT}.yaml"))
    return approval


def test_full_local_workflow_and_resume(db) -> None:
    connection, path = db
    before = prepare(path)
    approval = approve_and_sync(connection)
    message = send_sandbox(connection, approval)
    assert send_sandbox(connection, approval) == message
    assert connection.execute("SELECT count(*) FROM sandbox_messages").fetchone()[0] == 1
    delivered = connection.execute("SELECT * FROM sandbox_messages").fetchone()
    assert delivered["destination"] == "sandbox@adscout.test"
    assert "{{" not in delivered["body"] and f"/unsubscribe?id={message}" in delivered["body"]
    assert "synthetic" in delivered["sender"]
    lead_id = pending(connection)["lead_id"]
    set_deal(connection, lead_id, "won", 250000)
    set_deal(connection, lead_id, "won", 250000)
    assert connection.execute("SELECT count(*) FROM simulated_deals").fetchone()[0] == 1
    page = render(connection, SEGMENT, "csrf")
    assert "$2,500" in page and "simulated won revenue" in page
    assert "Placed locally" in page
    assert prepare(path) == before
    assert connection.execute("SELECT count(*) FROM approvals").fetchone()[0] == 1
    unsubscribe(connection, message)
    unsubscribe(connection, message)
    with pytest.raises(ActionRefused, match="unsubscribed"):
        send_sandbox(connection, approval)
    assert "Unsubscribed" in render(connection, SEGMENT, "csrf")


@pytest.mark.parametrize("field", ["subject", "body"])
def test_stale_approval_and_later_tampering_are_refused(db, field: str) -> None:
    connection, _ = db
    row = pending(connection)
    old_digest = review_digest(row)
    connection.execute(
        f"UPDATE drafts SET {field}={field} || ' changed' WHERE draft_id=?",  # noqa: S608
        (row["draft_id"],),
    )
    with pytest.raises(ActionRefused, match="changed"):
        decide(connection, row["draft_id"], old_digest, "approved")
    assert connection.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
    # Restore the fixture, approve, then change it after approval. Both consumers refuse it.
    connection.execute(
        f"UPDATE drafts SET {field}=? WHERE draft_id=?",  # noqa: S608
        (row[field], row["draft_id"]),
    )
    approval = approve_and_sync(connection)
    connection.execute(
        f"UPDATE drafts SET {field}={field} || ' changed' WHERE draft_id=?",  # noqa: S608
        (row["draft_id"],),
    )
    assert approved_for_sync(connection, SEGMENT) == []
    with pytest.raises(ActionRefused, match="changed"):
        send_sandbox(connection, approval)


def test_rejection_and_double_decision(db) -> None:
    connection, _ = db
    row = pending(connection)
    approval = decide(connection, row["draft_id"], review_digest(row), "rejected", "Not relevant")
    assert approved_for_sync(connection, SEGMENT) == []
    with pytest.raises(ActionRefused, match="already decided"):
        decide(connection, row["draft_id"], review_digest(row), "approved")
    with pytest.raises(ActionRefused, match="human approval"):
        send_sandbox(connection, approval)
    with pytest.raises(ActionRefused, match="human approval"):
        send_sandbox(connection, "missing")


def test_send_requires_crm_synthetic_domain_and_footer(db) -> None:
    connection, _ = db
    row = pending(connection)
    approval = decide(connection, row["draft_id"], review_digest(row), "approved")
    with pytest.raises(ActionRefused, match="Sync"):
        send_sandbox(connection, approval)
    run_crm_sync(connection, load_segment(CONFIG / "segments" / f"{SEGMENT}.yaml"))
    connection.execute("UPDATE companies SET domain='example.com' WHERE domain='alpha.test'")
    with pytest.raises(ActionRefused, match="synthetic"):
        send_sandbox(connection, approval)
    connection.execute("UPDATE companies SET domain='alpha.test' WHERE domain='example.com'")
    other = pending(connection, "hotel.test")
    connection.execute(
        "UPDATE drafts SET body=replace(body,'{{unsubscribe_url}}','') WHERE draft_id=?",
        (other["draft_id"],),
    )
    broken = get_draft(connection, other["draft_id"])
    bad_approval = decide(connection, other["draft_id"], review_digest(broken), "approved")
    run_crm_sync(connection, load_segment(CONFIG / "segments" / f"{SEGMENT}.yaml"))
    with pytest.raises(ActionRefused, match="placeholder"):
        send_sandbox(connection, bad_approval)
    assert connection.execute("SELECT count(*) FROM sandbox_messages").fetchone()[0] == 0


def test_deal_and_request_validation(db) -> None:
    connection, _ = db
    row = pending(connection)
    for lead, stage, amount in [(row["lead_id"], "won", 100), ("missing", "won", 100)]:
        with pytest.raises(ActionRefused, match="CRM"):
            set_deal(connection, lead, stage, amount)
    for stage, amount in [("bad", 1), ("won", -1), ("won", 100000001)]:
        with pytest.raises(ActionRefused, match="valid"):
            set_deal(connection, row["lead_id"], stage, amount)
    with pytest.raises(ActionRefused, match="not found"):
        unsubscribe(connection, "missing")
    with pytest.raises(ActionRefused, match="not found"):
        get_draft(connection, -1)
    with pytest.raises(ActionRefused):
        decide(connection, row["draft_id"], review_digest(row), "approved", "bad")
    assert source_link("javascript:alert(1)") == "javascript:alert(1)"
    assert "href=" not in source_link("http://user:password@example.test/")
    assert "href=" not in source_link("http://[broken/")
    with pytest.raises(ActionRefused):
        apply_action(connection, SEGMENT, CONFIG, {"action": "unknown"})


def test_render_escapes_draft_and_evidence(db) -> None:
    connection, _ = db
    row = pending(connection)
    connection.execute(
        "UPDATE drafts SET subject='<script>alert(1)</script>' WHERE draft_id=?", (row["draft_id"],)
    )
    page = render(connection, SEGMENT, "csrf", row["draft_id"], notice="<img onerror=boom>")
    assert "&lt;script&gt;" in page and "<script>" not in page
    assert "&lt;img onerror=boom&gt;" in page
    assert "https://alpha.test" in page and "Verified research" in page
    hotel = pending(connection, "hotel.test")
    page = render(connection, SEGMENT, "csrf", hotel["draft_id"])
    assert "<strong>Critic concern unresolved</strong>" in page
    assert "<strong>Research partly failed</strong>" in page


def test_dashboard_uses_the_routing_sample_of_latest_scoring_run(db) -> None:
    connection, _ = db
    row = pending(connection)
    original = connection.execute(
        "SELECT * FROM scores WHERE lead_id=?", (row["lead_id"],)
    ).fetchone()
    connection.execute(
        "INSERT INTO scores (lead_id, run_id, implementation, score, reasons_json, "
        "null_reasons_json, created_at, sample) VALUES (?, ?, 'real', 5, '[]', '{}', ?, 2)",
        (row["lead_id"], original["run_id"], original["created_at"]),
    )
    displayed = next(r for r in leads(connection, SEGMENT) if r["lead_id"] == row["lead_id"])
    assert displayed["score"] == original["score"]
    approve_and_sync(connection)
    crm_score = connection.execute(
        "SELECT value FROM fake_crm_account_fields WHERE field='adscout_score'"
    ).fetchone()[0]
    assert float(crm_score) == original["score"]


class SocketFixture:
    def __init__(self, request: bytes):
        self.request = io.BytesIO(request)
        self.response = bytearray()

    def makefile(self, *args, **kwargs):
        return self.request

    def sendall(self, data):
        self.response.extend(data)


def http(
    path: Path,
    route: str = "/",
    values: dict[str, str] | None = None,
    host: str = "127.0.0.1:8765",
    origin: str = "http://127.0.0.1:8765",
) -> bytes:
    body = urlencode(values).encode() if values is not None else b""
    method = "POST" if values is not None else "GET"
    request = (
        f"{method} {route} HTTP/1.1\r\nHost: {host}\r\nOrigin: {origin}\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    ).encode() + body
    fixture = SocketFixture(request)
    Handler(
        fixture,
        ("127.0.0.1", 1234),
        SimpleNamespace(server_port=8765),
        db=path,
        config=CONFIG,
        segment=SEGMENT,
        csrf="test-csrf",
    )
    return bytes(fixture.response)


def test_http_forms_and_security_boundary(db) -> None:
    connection, path = db
    assert b"200 OK" in http(path)
    assert b"text/css" in http(path, "/workspace.css")
    assert b"404" in http(path, "/missing")
    assert b"400" in http(path, "/?draft=garbage")
    assert b"403" in http(path, host="attacker.test")
    form = {"csrf": "test-csrf", "action": "sync"}
    assert b"403" in http(path, "/action", form, origin="https://attacker.test")
    assert b"400" in http(path, "/action", form | {"csrf": "bad"})
    assert b"400" in http(path, "/action", form | {"csrf": "\u2603"})
    assert b"403" in http(path, "/bad", form)
    row = pending(connection)
    approve = {
        "csrf": "test-csrf",
        "action": "approve",
        "draft": str(row["draft_id"]),
        "reviewed": review_digest(row),
    }
    assert b"200 OK" in http(path, "/action", approve)
    assert b"400" in http(path, "/action", approve)
    assert b"200 OK" in http(path, "/action", form)
    approval = connection.execute("SELECT approval_id FROM approvals").fetchone()[0]
    assert b"200 OK" in http(
        path, "/action", {"csrf": "test-csrf", "action": "send", "approval": approval}
    )
    message = connection.execute("SELECT message_id FROM sandbox_messages").fetchone()[0]
    assert b"Confirm unsubscribe" in http(path, f"/unsubscribe?id={message}")
    assert b"200 OK" in http(
        path, "/action", {"csrf": "test-csrf", "action": "unsubscribe", "id": message}
    )
    assert b"400" in http(
        path, "/action", {"csrf": "test-csrf", "action": "send", "approval": approval}
    )
