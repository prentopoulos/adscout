"""The real pipeline, offline: every step and exit on synthetic companies, with no network.

Model answers are scripted (tests/fixtures/models/synthetic-demo.yaml) and pages are fixture
files (tests/fixtures/sites), both written by tests/fixtures/make_offline_run.py.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from adscout import cli
from adscout.db.migrate import upgrade
from adscout.llm.prompts import prompt_set_version
from adscout.pipeline.real import pipeline_graph

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
EXPECTED = {
    ("alpha.test", "draft"): ("kept", None),
    ("bravo.test", "enrich"): ("exited", "missing_key_fields"),
    ("charlie.test", "rules"): ("exited", "out_of_profile"),
    ("delta.test", "score"): ("exited", "below_threshold"),
    ("echo.test", "score"): ("exited", "near_miss"),
    ("foxtrot.test", "research"): ("exited", "research_failed"),
    ("golf.test", "draft"): ("exited", "draft_failed"),
    ("hotel.test", "research"): ("kept", "research_partial"),
    ("hotel.test", "draft"): ("kept", "critic_unresolved"),
    ("excluded.test", "source"): ("exited", "excluded"),
}


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "adscout.db"
    upgrade(path)
    return path


def run_offline(db: Path, *extra: str) -> str:
    assert cli.main(["run", *OFFLINE, "--db", str(db), *extra]) == 0
    connection = sqlite3.connect(db)
    run_id = str(
        connection.execute("SELECT run_id FROM runs ORDER BY started_at DESC").fetchone()[0]
    )
    connection.close()
    return run_id


def test_fake_run_covers_every_step_and_exit(db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_id = run_offline(db)
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    outcomes = {
        (row["domain"], row["step"]): (row["outcome"], row["reason"] or row["flag"])
        for row in connection.execute(
            "SELECT c.domain, o.step, o.outcome, o.reason, o.flag FROM lead_step_outcomes AS o "
            "JOIN leads AS l ON l.lead_id = o.lead_id "
            "JOIN companies AS c ON c.company_id = l.company_id WHERE o.run_id = ?",
            (run_id,),
        )
    }
    for key, expected in EXPECTED.items():
        assert outcomes[key] == expected, key
    run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    assert (run["status"], run["source"], run["kind"]) == ("succeeded", "fixture", "pipeline")
    assert run["media_kit_hash"] and run["price_table_hash"] and run["site_list_hash"] is None
    assert json.loads(run["options_json"])["research_design"] == "multi"
    steps = connection.execute(
        "SELECT step, implementation FROM step_runs WHERE run_id = ? ORDER BY seq", (run_id,)
    ).fetchall()
    assert [tuple(row) for row in steps] == [
        ("source", "real"),
        ("enrich", "real"),
        ("rules", "real"),
        ("score", "real"),
        ("research", "real"),
        ("draft", "real"),
    ]
    versions = {row[0] for row in connection.execute("SELECT prompt_version FROM leads")}
    assert versions == {prompt_set_version()}
    drafts = dict(
        connection.execute("SELECT status, count(*) FROM drafts GROUP BY status").fetchall()
    )
    assert drafts == {"pending_approval": 2, "failed_checks": 1}
    assert connection.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0  # stops there
    connection.close()
    assert cli.main(["check", run_id, "--db", str(db)]) == 0
    assert cli.main(["funnel", run_id, "--db", str(db)]) == 0
    assert cli.main(["export", run_id, "--db", str(db)]) == 0
    assert "pass" in capsys.readouterr().out


def test_single_design_runs_the_baseline_agent(db: Path) -> None:
    run_id = run_offline(db, "--research-design", "single")
    connection = sqlite3.connect(db)
    agents = {
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT agent_name FROM model_calls WHERE step = 'research'"
        )
    }
    designs = {
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT design FROM briefs WHERE run_id = ?", (run_id,)
        )
    }
    connection.close()
    assert agents == {"research_single"} and designs == {"single"}


def test_repeats_score_every_lead_more_than_once(db: Path) -> None:
    run_id = run_offline(db, "--score-repeats", "2")
    connection = sqlite3.connect(db)
    samples = {
        row[0]
        for row in connection.execute("SELECT sample FROM scores WHERE run_id = ?", (run_id,))
    }
    connection.close()
    assert samples == {1, 2}


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--live"], "--max-spend-usd"),
        (["--live", "--max-spend-usd", "1"], "ADSCOUT_CONTACT"),
        (["--media-kit", "nowhere.yaml"], "no media kit at nowhere.yaml"),
        (["--score-repeats", "0"], "--score-repeats must be at least 1"),
    ],
)
def test_unusable_settings_are_refused_before_any_row(
    db: Path,
    extra: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ADSCOUT_CONTACT", raising=False)
    monkeypatch.setattr("adscout.env.ENV_FILE", db.parent / "absent.env")
    monkeypatch.setattr("adscout.sources.fetcher.ENV_FILE", db.parent / "absent.env")
    args = [arg for arg in OFFLINE if arg]
    if "--media-kit" in extra:
        index = args.index("--media-kit")
        del args[index : index + 2]
    assert cli.main(["run", *args, "--db", str(db), *extra]) == 1
    assert message in capsys.readouterr().err
    connection = sqlite3.connect(db)
    assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
    connection.close()


def test_the_pipeline_graph_is_the_registry_chain() -> None:
    graph = pipeline_graph(
        steps=type(
            "Steps",
            (),
            {
                n: (lambda self, s: {})
                for n in ("source", "enrich", "rules", "score", "research", "draft")
            },
        )()
    )  # type: ignore[arg-type]
    mermaid = graph.get_graph().draw_mermaid()
    for earlier, later in [
        ("source", "enrich"),
        ("enrich", "rules"),
        ("rules", "score"),
        ("score", "research"),
        ("research", "draft"),
    ]:
        assert f"{earlier} --> {later};" in mermaid
