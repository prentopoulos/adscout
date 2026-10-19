"""Private data never reaches a model, and LangSmith tracing is refused (decisions 33, 38)."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from adscout import cli
from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.llm.adapter import FakeTransport, ModelRequest, Sent
from adscout.pipeline.contexts import TRACING_VARIABLES, TracingOn, refuse_tracing

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OFFLINE = [
    "--segment",
    "synthetic-demo",
    "--config-dir",
    str(FIXTURES / "config"),
    "--fixture-models",
    str(FIXTURES / "models" / "synthetic-demo.yaml"),
    "--fixture-sites",
    str(FIXTURES / "sites"),
    "--media-kit",
    str(FIXTURES / "config" / "media-kit" / "fixture-publisher.yaml"),
]
SECRET = "sk-ant-api03-" + "CANARY" * 8  # a made-up key, built so no scanner mistakes it
CONTACT = "canary-contact@example.test"
LABEL = "canary-label.test"
CRM_VALUE = "CANARY-CRM-VALUE-7731"
REVENUE = "CANARY-REVENUE-4412"


def test_canary_values_never_reach_a_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "adscout.db"
    upgrade(db)
    # A secret and a contact in the environment, a label file, CRM and revenue values.
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.setenv("ADSCOUT_CONTACT", CONTACT)
    (tmp_path / "labels.csv").write_text(
        f"domain,label,labelled_on\n{LABEL},good,2026-10-19\nalpha.test,poor,2026-10-19\n",
        encoding="utf-8",
    )
    connection = connect(db)
    connection.execute(
        "INSERT INTO fake_crm_accounts (domain, created_by, created_at) "
        "VALUES ('crm-only.test', 'person', ?)",
        (utc_now(),),
    )
    for field, value in (("notes", CRM_VALUE), ("deal_value", REVENUE)):
        connection.execute(
            "INSERT INTO fake_crm_account_fields VALUES (1, ?, ?, 'person', ?)",
            (field, value, utc_now()),
        )
    connection.close()
    seen: list[bytes] = []
    original = FakeTransport.send

    def watching(self: FakeTransport, request: ModelRequest, key: str) -> Sent:
        seen.append(request.canonical_bytes())
        return original(self, request, key)

    monkeypatch.setattr(FakeTransport, "send", watching)
    assert cli.main(["run", *OFFLINE, "--db", str(db)]) == 0

    assert len(seen) > 20  # every role was asked
    everything = b"\n".join(seen).decode("utf-8")
    for canary in (SECRET, CONTACT, LABEL, CRM_VALUE, REVENUE, "deal_value", "labels.csv"):
        assert canary not in everything, canary
    connection = sqlite3.connect(db)
    recorded = json.dumps(
        connection.execute("SELECT target, detail FROM source_calls").fetchall()
        + connection.execute("SELECT error_detail FROM model_calls").fetchall()
    )
    connection.close()
    assert SECRET not in recorded and CRM_VALUE not in recorded and REVENUE not in recorded


@pytest.mark.parametrize("name", TRACING_VARIABLES)
def test_any_langsmith_tracing_variable_stops_the_run(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "adscout.db"
    upgrade(db)
    monkeypatch.setenv(name, "true")
    assert cli.main(["run", *OFFLINE, "--db", str(db)]) == 1
    assert f"{name} would send run data to LangSmith" in capsys.readouterr().err
    connection = sqlite3.connect(db)
    assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
    connection.close()


def test_tracing_off_or_unset_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in TRACING_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    refuse_tracing()
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    refuse_tracing()
    monkeypatch.setenv("LANGSMITH_TRACING", "TRUE")
    with pytest.raises(TracingOn):
        refuse_tracing()


def test_no_agent_context_builder_takes_a_connection_or_a_path() -> None:
    import inspect

    from adscout.pipeline import contexts

    builders = [
        member
        for name, member in inspect.getmembers(contexts, inspect.isfunction)
        if member.__module__ == contexts.__name__ and name != "refuse_tracing"
    ]
    assert builders
    for builder in builders:
        annotations: dict[str, Any] = inspect.get_annotations(builder, eval_str=True)
        for name, kind in annotations.items():
            if name == "return":
                continue
            assert kind is not sqlite3.Connection and kind is not Path, (builder.__name__, name)
