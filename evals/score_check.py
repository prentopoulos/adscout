"""The score check against the owner's labels, and the scoring tier rule (design decision 19).

Labels are `good`, `maybe` or `poor` per domain, given blind to scores in a versioned CSV
whose SHA-256 is recorded with every report. Labels are read here only, after scoring; no
prompt ever sees them (constitution: no agent reading untrusted content gets owner labels).

A company's score is its first sample, the one that routes it in a run. Reported, with no
p-values and no pass/fail target: a label-by-outcome table; good-versus-poor AUC (ties count
half, with the number of pairs); Kendall tau-b between score and label; precision and recall
at the threshold, naming poor-labelled companies that qualified; precision in the top 10,
taking every company tied at the cut; the companies scored 55 to 65; bootstrap 95% intervals
over companies (1,000 resamples, a fixed seed); and, with repeats, each company's spread,
criterion agreement and threshold flips.
"""

import csv
import hashlib
import io
import math
import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from adscout.config import ConfigError, normalize_domain

LabelValue = Literal["good", "maybe", "poor"]
LABEL_ORDER: dict[str, int] = {"poor": 0, "maybe": 1, "good": 2}
LABEL_COLUMNS = ("domain", "label", "labelled_on")
BOOTSTRAP_RESAMPLES = 1_000
BOOTSTRAP_SEED = 20261019
TOP_K = 10
BAND = (55.0, 65.0)
AUC_MARGIN = 0.10  # Sonnet keeps scoring only if its AUC beats Haiku's by this much


@dataclass(frozen=True)
class Labels:
    by_domain: dict[str, LabelValue]
    sha256: str
    path: str


@dataclass(frozen=True)
class Company:
    domain: str
    label: LabelValue
    outcome: str  # qualified, near_miss, below_threshold, score_failed
    scores: list[float | None]  # every sample, first first
    ratings: list[dict[str, int]]  # per sample: criterion -> rating

    @property
    def score(self) -> float | None:
        return self.scores[0] if self.scores else None


def load_labels(path: Path) -> Labels:
    data = path.read_bytes()
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    if tuple(reader.fieldnames or ()) != LABEL_COLUMNS:
        raise ConfigError(f"{path.name}: columns must be exactly {', '.join(LABEL_COLUMNS)}")
    found: dict[str, LabelValue] = {}
    for number, row in enumerate(reader, start=2):
        label = row["label"].strip().lower()
        if label not in LABEL_ORDER:
            raise ConfigError(f"{path.name} row {number}: label must be good, maybe or poor")
        domain = normalize_domain(row["domain"])
        if domain in found:
            raise ConfigError(f"{path.name} row {number}: {domain} is labelled twice")
        found[domain] = label  # type: ignore[assignment]
    return Labels(found, hashlib.sha256(data).hexdigest(), path.as_posix())


def auc(companies: Sequence[Company]) -> tuple[float | None, int]:
    """P(a good company outscores a poor one), ties half; the number of good-poor pairs."""
    good = [c.score for c in companies if c.label == "good" and c.score is not None]
    poor = [c.score for c in companies if c.label == "poor" and c.score is not None]
    pairs = len(good) * len(poor)
    if not pairs:
        return None, 0
    wins = sum(1.0 if g > p else 0.5 if g == p else 0.0 for g in good for p in poor)
    return wins / pairs, pairs


def kendall_tau_b(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    concordant = discordant = ties_x = ties_y = 0
    n = len(xs)
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = xs[i] - xs[j], ys[i] - ys[j]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                ties_x += 1
            elif dy == 0:
                ties_y += 1
            elif (dx > 0) == (dy > 0):
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt((concordant + discordant + ties_x) * (concordant + discordant + ties_y))
    return (concordant - discordant) / denominator if denominator else None


def precision_recall(companies: Sequence[Company], threshold: float) -> dict[str, Any]:
    scored = [c for c in companies if c.score is not None]
    qualified = [c for c in scored if c.score is not None and c.score >= threshold]
    good = [c for c in scored if c.label == "good"]
    hits = [c for c in qualified if c.label == "good"]
    return {
        "precision": len(hits) / len(qualified) if qualified else None,
        "recall": len(hits) / len(good) if good else None,
        "qualified": len(qualified),
        "good": len(good),
        "poor_qualified": sorted(c.domain for c in qualified if c.label == "poor"),
    }


def precision_top_k(companies: Sequence[Company], k: int = TOP_K) -> dict[str, Any]:
    ranked = sorted((c for c in companies if c.score is not None), key=lambda c: -(c.score or 0))
    if not ranked:
        return {"precision": None, "included": 0}
    cut = ranked[min(k, len(ranked)) - 1].score
    top = [c for c in ranked if c.score is not None and cut is not None and c.score >= cut]
    good = sum(c.label == "good" for c in top)
    return {"precision": good / len(top), "included": len(top), "cut_score": cut}


def band(companies: Sequence[Company]) -> list[dict[str, Any]]:
    low, high = BAND
    return [
        {"domain": c.domain, "score": c.score, "label": c.label}
        for c in sorted(companies, key=lambda c: c.domain)
        if c.score is not None and low <= c.score <= high
    ]


def bootstrap(
    companies: Sequence[Company], metric: Callable[[Sequence[Company]], float | None]
) -> list[float] | None:
    """A 95% percentile interval over companies resampled with replacement."""
    rng = random.Random(BOOTSTRAP_SEED)  # noqa: S311 - a seeded resampler, not a secret
    values = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [rng.choice(companies) for _ in companies]
        value = metric(sample)
        if value is not None:
            values.append(value)
    if len(values) < BOOTSTRAP_RESAMPLES // 2:
        return None
    values.sort()
    return [
        values[int(0.025 * len(values))],
        values[min(int(0.975 * len(values)), len(values) - 1)],
    ]


def spread(companies: Sequence[Company], threshold: float) -> dict[str, Any]:
    """Across repeats: score range and SD per company, criterion agreement, threshold flips."""
    rows: list[dict[str, Any]] = []
    ranges: list[float] = []
    for c in companies:
        scores = [s for s in c.scores if s is not None]
        if len(scores) < 2:
            continue
        criteria = set().union(*(set(r) for r in c.ratings)) if c.ratings else set()
        agreeing = [name for name in criteria if len({r.get(name) for r in c.ratings}) == 1]
        ranges.append(max(scores) - min(scores))
        rows.append(
            {
                "domain": c.domain,
                "range": ranges[-1],
                "sd": statistics.stdev(scores),
                "criterion_agreement": len(agreeing) / len(criteria) if criteria else None,
                "flips": len({s >= threshold for s in scores}) > 1,
            }
        )
    return {
        "companies": rows,
        "flips": sum(row["flips"] for row in rows),
        "max_range": max(ranges, default=None),
    }


def report(companies: Sequence[Company], threshold: float) -> dict[str, Any]:
    by_label: dict[str, dict[str, int]] = {}
    for c in companies:
        by_label.setdefault(c.label, {}).setdefault(c.outcome, 0)
        by_label[c.label][c.outcome] += 1
    value, pairs = auc(companies)
    scored = [c for c in companies if c.score is not None]
    tau = kendall_tau_b([c.score or 0.0 for c in scored], [LABEL_ORDER[c.label] for c in scored])
    return {
        "companies": len(companies),
        "label_by_outcome": by_label,
        "auc_good_vs_poor": value,
        "auc_pairs": pairs,
        "auc_ci95": bootstrap(companies, lambda sample: auc(sample)[0]),
        "kendall_tau_b": tau,
        "at_threshold": precision_recall(companies, threshold),
        "top_10": precision_top_k(companies),
        "band_55_65": band(companies),
        "score_failed": sum(c.outcome == "score_failed" for c in companies),
        "repeats": spread(companies, threshold),
    }


def tier_decision(haiku: dict[str, Any], sonnet: dict[str, Any]) -> dict[str, Any]:
    """Sonnet stays only if its AUC is at least Haiku's + 0.10, with no more score failures
    and no more threshold flips; otherwise Haiku scores and the segment is rescored."""
    h_auc, s_auc = haiku["auc_good_vs_poor"], sonnet["auc_good_vs_poor"]
    reasons = []
    if h_auc is None or s_auc is None:
        reasons.append("an AUC is undefined (no good-poor pairs)")
    elif s_auc < h_auc + AUC_MARGIN:
        reasons.append(f"Sonnet AUC {s_auc:.3f} < Haiku {h_auc:.3f} + {AUC_MARGIN}")
    if sonnet["score_failed"] > haiku["score_failed"]:
        reasons.append("Sonnet has more score_failed")
    if sonnet["repeats"]["flips"] > haiku["repeats"]["flips"]:
        reasons.append("Sonnet has more threshold flips")
    return {"model": "sonnet" if not reasons else "haiku", "reasons_against_sonnet": reasons}
