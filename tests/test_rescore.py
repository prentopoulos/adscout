"""`adscout rescore` on stored enrichments: scoring calls only, as a `rescore` run."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from adscout import cli
from adscout.db.connection import connect, utc_now
from adscout.db.migrate import upgrade
from adscout.ids import uuid7
from adscout.pipeline.models import ModelChoice, ModelsNotChosen
from adscout.pipeline.rescore import stored_enrichments

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODELS = FIXTURES / "models" / "rescore.yaml"
GOOD = {
    "categories": ["peripherals"],
    "sells_in": ["CA", "US"],
    "employee_count": {"count": 300},
    "ad_signals": [{"tag": "meta_pixel", "kind": "ad_pixel", "host": "connect.facebook.net"}],
    "recent_launches": [{"name": "K1", "date": "2026-09", "source_url": "https://alpha.test/n"}],
}


@pytest.fixture
def db_path(tmp_path: Path) -> Iterator[Path]:
    yield build_db(tmp_path / "adscout.db")


def build_db(path: Path) -> Path:
    """A database holding four synthetic leads' stored enrichments from a finished run."""
    upgrade(path)
    connection = connect(path)
    run_id = "20261019T000000Z-aaaaaa"
    connection.execute(
        "INSERT INTO runs (run_id, kind, segment_id, status, started_at, ended_at, source, "
        "code_revision, code_dirty, lock_digest, package_version, agent_version, prompt_version, "
        "python_version, platform, schema_version, budgets_json, null_reasons_json, pid, host) "
        "VALUES (?, 'pipeline', 'synthetic-demo', 'succeeded', ?, ?, 'fixture', 'abc', 0, 'x', "
        "'0', 'v', 'p-0', '3.13', 't', 2, '{}', '{}', 1, 'h')",
        (run_id, utc_now(), utc_now()),
    )
    leads = {
        "alpha.test": GOOD,
        "foxtrot.test": GOOD,
        "golf.test": GOOD,
        "hotel.test": GOOD | {"sells_in": ["US"]},  # fails the region rule: not scored
    }
    for number, (domain, fields) in enumerate(leads.items(), 1):
        lead_id = str(uuid7())
        connection.execute(
            "INSERT INTO companies VALUES (?, ?, ?, ?, ?)",
            (number, domain, domain.split(".")[0].title(), run_id, utc_now()),
        )
        connection.execute(
            "INSERT INTO leads VALUES (?, 'synthetic-demo', ?, 'test', 'p-0', 'v', ?, ?)",
            (lead_id, number, run_id, utc_now()),
        )
        for version in (fields | {"categories": ["old"]}, fields):  # the latest one counts
            connection.execute(
                "INSERT INTO enrichments (lead_id, run_id, implementation, fields_json, "
                "missing_fields_json, created_at) VALUES (?, ?, 'real', ?, '[]', ?)",
                (lead_id, run_id, json.dumps({"fields": version}), utc_now()),
            )
    connection.close()
    return path


def rescore(db_path: Path, *extra: str) -> int:
    return cli.main(
        [
            "rescore",
            "--segment",
            "synthetic-demo",
            "--config-dir",
            str(FIXTURES / "config"),
            "--db",
            str(db_path),
            *extra,
        ]
    )


def test_stored_enrichments_are_each_leads_latest(db_path: Path) -> None:
    connection = connect(db_path)
    found = stored_enrichments(connection, "synthetic-demo")
    connection.close()
    assert [lead.domain for lead, _ in found] == [
        "alpha.test",
        "foxtrot.test",
        "golf.test",
        "hotel.test",
    ]
    assert all(fields["categories"] == ["peripherals"] for _, fields in found)


def test_rescore_makes_scoring_calls_only(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rescore(db_path, "--fixture-models", str(MODELS)) == 0
    assert "rescore run" in capsys.readouterr().out
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    run = connection.execute("SELECT * FROM runs WHERE kind = 'rescore'").fetchone()
    assert (run["status"], run["source"]) == ("succeeded", "fixture")
    assert run["price_table_hash"] and run["icp_config_hash"]
    assert json.loads(run["options_json"])["model"] == "claude-sonnet-5-5"
    steps = [
        row[0]
        for row in connection.execute(
            "SELECT step FROM step_runs WHERE run_id = ?", (run["run_id"],)
        )
    ]
    assert steps == ["score"]
    assert connection.execute("SELECT count(*) FROM source_calls").fetchone()[0] == 0
    calls = connection.execute("SELECT DISTINCT role FROM model_calls").fetchall()
    assert [row[0] for row in calls] == ["scorer"]
    outcomes = connection.execute(
        "SELECT c.domain, o.outcome, o.reason FROM lead_step_outcomes AS o "
        "JOIN leads AS l ON l.lead_id = o.lead_id "
        "JOIN companies AS c ON c.company_id = l.company_id "
        "ORDER BY c.domain"
    ).fetchall()
    assert [tuple(row) for row in outcomes] == [
        ("alpha.test", "kept", None),
        ("foxtrot.test", "exited", "near_miss"),
        ("golf.test", "exited", "below_threshold"),
    ]
    scores = dict(
        connection.execute(
            "SELECT c.domain, s.score FROM scores AS s JOIN leads AS l ON l.lead_id = s.lead_id "
            "JOIN companies AS c ON c.company_id = l.company_id"
        ).fetchall()
    )
    assert scores == {"alpha.test": 80.0, "foxtrot.test": 58.75, "golf.test": 30.0}
    connection.close()


def test_offline_rescore_needs_answers_or_a_replay(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rescore(db_path) == 1
    assert "needs scripted answers (--fixture-models) or a run to replay" in capsys.readouterr().err


def test_live_rescore_needs_a_cap(db_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert rescore(db_path, "--live") == 1
    assert "--max-spend-usd" in capsys.readouterr().err


def test_live_and_replay_are_exclusive() -> None:
    with pytest.raises(ModelsNotChosen, match="not both"):
        ModelChoice(live=True, replay_run_id="r").check()


def test_rescore_of_an_empty_segment_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "empty.db"
    upgrade(path)
    assert rescore(path, "--fixture-models", str(MODELS)) == 1
    assert "no stored real enrichments" in capsys.readouterr().err
