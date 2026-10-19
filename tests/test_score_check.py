"""The score check metrics, the labels file, the tier rule and `python -m evals score-compare`."""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from test_rescore import FIXTURES, MODELS, build_db

from adscout.config import ConfigError
from adscout.db.connection import connect
from evals.__main__ import main as evals_main
from evals.score_check import (
    Company,
    auc,
    band,
    bootstrap,
    kendall_tau_b,
    load_labels,
    precision_recall,
    precision_top_k,
    report,
    spread,
    tier_decision,
)


def company(domain: str, label: str, *scores: float | None, outcome: str = "qualified") -> Company:
    return Company(domain, label, outcome, list(scores), [{} for _ in scores])  # type: ignore[arg-type]


def test_auc_counts_ties_as_half_and_states_its_pairs() -> None:
    companies = [
        company("a", "good", 80),
        company("b", "good", 60),
        company("c", "poor", 60),
        company("d", "poor", 40),
        company("e", "maybe", 99),
        company("f", "poor", None),
    ]
    assert auc(companies) == (3.5 / 4, 4)
    assert auc([company("a", "good", 1)]) == (None, 0)


def test_kendall_tau_b_with_and_without_ties() -> None:
    assert kendall_tau_b([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert kendall_tau_b([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert kendall_tau_b([1, 1, 2], [0, 1, 2]) == pytest.approx(2 / math.sqrt(6))
    assert kendall_tau_b([1, 1], [1, 1]) is None


def test_precision_recall_names_poor_companies_that_qualified() -> None:
    companies = [
        company("good-in", "good", 70),
        company("poor-in", "poor", 65),
        company("good-out", "good", 50),
        company("maybe-in", "maybe", 60),
    ]
    result = precision_recall(companies, 60)
    assert result == {
        "precision": 1 / 3,
        "recall": 1 / 2,
        "qualified": 3,
        "good": 2,
        "poor_qualified": ["poor-in"],
    }


def test_top_k_takes_every_company_tied_at_the_cut() -> None:
    companies = [company(f"c{i}", "good" if i % 2 else "poor", 100 - i) for i in range(9)]
    companies += [
        company("tie1", "good", 50),
        company("tie2", "poor", 50),
        company("low", "good", 1),
    ]
    result = precision_top_k(companies, k=10)
    assert result["included"] == 11 and result["cut_score"] == 50
    assert result["precision"] == 5 / 11


def test_band_lists_companies_scored_55_to_65() -> None:
    companies = [company("a", "good", 54.9), company("b", "maybe", 55), company("c", "poor", 65)]
    assert [row["domain"] for row in band(companies)] == ["b", "c"]


def test_bootstrap_is_seeded_and_brackets_the_estimate() -> None:
    companies = [company(f"g{i}", "good", 60 + i) for i in range(8)]
    companies += [company(f"p{i}", "poor", 50 + 2 * i) for i in range(8)]
    first = bootstrap(companies, lambda sample: auc(sample)[0])
    assert first == bootstrap(companies, lambda sample: auc(sample)[0])
    assert first is not None and first[0] <= auc(companies)[0] <= first[1]  # type: ignore[operator]
    assert bootstrap([company("a", "good", 1)], lambda sample: auc(sample)[0]) is None


def test_spread_counts_threshold_flips_and_criterion_agreement() -> None:
    steady = Company("s", "good", "qualified", [70, 72, 71], [{"a": 4, "b": 3}] * 3)
    flipping = Company(
        "f",
        "poor",
        "near_miss",
        [58, 61, 59],
        [{"a": 3, "b": 3}, {"a": 4, "b": 3}, {"a": 3, "b": 3}],
    )
    result = spread([steady, flipping, company("one", "good", 80)], 60)
    assert result["flips"] == 1 and result["max_range"] == 3
    agreement = {row["domain"]: row["criterion_agreement"] for row in result["companies"]}
    assert agreement == {"s": 1.0, "f": 0.5}


def sample_report(auc_value: float | None, failed: int = 0, flips: int = 0) -> dict[str, Any]:
    return {"auc_good_vs_poor": auc_value, "score_failed": failed, "repeats": {"flips": flips}}


@pytest.mark.parametrize(
    ("haiku", "sonnet", "model"),
    [
        (sample_report(0.70), sample_report(0.80), "sonnet"),
        (sample_report(0.70), sample_report(0.79), "haiku"),
        (sample_report(0.70), sample_report(0.90, failed=1), "haiku"),
        (sample_report(0.70), sample_report(0.90, flips=2), "haiku"),
        (sample_report(None), sample_report(0.90), "haiku"),
    ],
)
def test_sonnet_keeps_scoring_only_by_the_predeclared_rule(
    haiku: dict[str, Any], sonnet: dict[str, Any], model: str
) -> None:
    assert tier_decision(haiku, sonnet)["model"] == model


def write_labels(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "labels.csv"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def test_labels_load_with_their_hash(tmp_path: Path) -> None:
    path = write_labels(tmp_path, "domain,label,labelled_on\nWWW.Alpha.test,Good,2026-10-19\n")
    labels = load_labels(path)
    assert labels.by_domain == {"alpha.test": "good"} and len(labels.sha256) == 64


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("domain,label\nalpha.test,good\n", "columns must be exactly"),
        ("domain,label,labelled_on\nalpha.test,great,2026-10-19\n", "good, maybe or poor"),
        ("domain,label,labelled_on\na.test,good,x\nA.test,poor,x\n", "labelled twice"),
    ],
)
def test_bad_labels_are_refused(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_labels(write_labels(tmp_path, text))


def test_report_puts_every_metric_together() -> None:
    companies = [company("a", "good", 80), company("b", "poor", 30, outcome="below_threshold")]
    result = report(companies, 60)
    assert result["label_by_outcome"] == {"good": {"qualified": 1}, "poor": {"below_threshold": 1}}
    assert result["auc_good_vs_poor"] == 1.0 and result["kendall_tau_b"] == 1.0


def test_score_compare_runs_both_arms_and_applies_the_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = build_db(tmp_path / "adscout.db")
    labels = write_labels(
        tmp_path,
        "domain,label,labelled_on\nalpha.test,good,2026-10-19\nfoxtrot.test,maybe,2026-10-19\n"
        "golf.test,poor,2026-10-19\n",
    )
    monkeypatch.setattr("evals.score_compare.RUNS", tmp_path / "runs")
    code = evals_main(
        [
            "score-compare",
            "--segment",
            "synthetic-demo",
            "--labels",
            str(labels),
            "--config-dir",
            str(FIXTURES / "config"),
            "--db",
            str(db),
            "--repeats",
            "2",
            "--fixture-models",
            str(MODELS),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "tier rule: haiku scores" in out  # equal scripted answers: Sonnet does not beat Haiku
    [written] = (tmp_path / "runs").glob("score-compare-synthetic-demo-*.json")
    result = json.loads(written.read_text(encoding="utf-8"))
    assert result["haiku"]["auc_good_vs_poor"] == result["sonnet"]["auc_good_vs_poor"] == 1.0
    assert result["labels"]["labelled"] == 3 and result["repeats"] == 2
    connection = connect(db)
    kinds = [row[0] for row in connection.execute("SELECT kind FROM runs ORDER BY started_at")]
    models = {row[0] for row in connection.execute("SELECT model FROM model_calls")}
    connection.close()
    assert kinds.count("eval") == 2
    assert models == {"claude-haiku-5-5", "claude-sonnet-5-5"}
