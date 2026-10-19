"""Write the offline-run fixtures: synthetic company sites and scripted model answers.

    uv run --locked python tests/fixtures/make_offline_run.py

Every company, page, number and answer is made up, on reserved `.test` domains, so a fake
run of the real pipeline exercises every step and exit without the network. Rerun after
changing this file; tests compare nothing to it, they use what it wrote.
"""

import copy
import json
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SITES = HERE / "sites"
MODELS = HERE / "models" / "synthetic-demo.yaml"

COMPANIES = {
    # domain: (name, product, launch, launch date, employees, ships, pixels, outcome note)
    "alpha.test": (
        "Alpha Gear",
        "keyboards and mice",
        "the K1 keyboard",
        "September 2026",
        1500,
        "the United States and Canada",
        True,
    ),
    "bravo.test": (
        "Bravo Gear",
        "mouse pads",
        "the P2 pad",
        "August 2026",
        None,
        "the United States and Canada",
        False,
    ),
    "charlie.test": (
        "Charlie Gear",
        "controllers",
        "the C3 controller",
        "July 2026",
        400,
        "the United States",
        False,
    ),
    "delta.test": (
        "Delta Gear",
        "cables",
        "the D4 cable",
        "June 2026",
        90,
        "the United States and Canada",
        False,
    ),
    "echo.test": (
        "Echo Gear",
        "headset stands",
        "the E5 stand",
        "May 2026",
        200,
        "the United States and Canada",
        True,
    ),
    "foxtrot.test": (
        "Foxtrot Gear",
        "webcams",
        "the F6 webcam",
        "April 2026",
        800,
        "the United States and Canada",
        True,
    ),
    "golf.test": (
        "Golf Gear",
        "microphones",
        "the G7 microphone",
        "September 2026",
        600,
        "the United States and Canada",
        True,
    ),
    "hotel.test": (
        "Hotel Gear",
        "headsets",
        "the H5 headset",
        "August 2026",
        700,
        "the United States and Canada",
        True,
    ),
}
PIXELS = '<script src="https://connect.facebook.net/en_US/fbevents.js"></script>'


def home(domain: str) -> str:
    name, product, _launch, _when, employees, _ships, pixels = COMPANIES[domain]
    team = f" We are a team of {employees:,} people in 2026." if employees else ""
    return (
        f"<html><head><title>{name}</title>{PIXELS if pixels else ''}</head><body>"
        f'<nav><a href="/news">Newsroom</a> <a href="/shipping">Shipping</a></nav>'
        f"<h1>{name}</h1><p>{name} makes {product} for PC and console gamers.{team}</p>"
        f"<p>{name} advertises on gaming video channels every month.</p></body></html>"
    )


def news(domain: str) -> str:
    name, _p, launch, when, *_ = COMPANIES[domain]
    return f"<html><body><h1>News</h1><p>{name} launched {launch} in {when}.</p></body></html>"


def shipping(domain: str) -> str:
    ships = COMPANIES[domain][5]
    return f"<html><body><p>We ship to {ships}.</p></body></html>"


def write_sites() -> None:
    for domain in COMPANIES:
        folder = SITES / domain
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(home(domain), encoding="utf-8", newline="\n")
        (folder / "news").write_text(news(domain), encoding="utf-8", newline="\n")
        (folder / "shipping").write_text(shipping(domain), encoding="utf-8", newline="\n")


def extraction(domain: str) -> dict:
    _name, _p, launch, when, employees, ships, _ = COMPANIES[domain]
    month = {
        "September": "09",
        "August": "08",
        "July": "07",
        "June": "06",
        "May": "05",
        "April": "04",
    }
    word, year = when.split()
    data = {
        "categories": {"values": ["peripherals"], "source_url": f"https://{domain}/"},
        "sells_in": {
            "values": ["US", "CA"] if "Canada" in ships else ["US"],
            "source_url": f"https://{domain}/shipping",
        },
        "recent_launches": [
            {
                "name": launch.removeprefix("the "),
                "date": f"{year}-{month[word]}",
                "source_url": f"https://{domain}/news",
            }
        ],
        "employee_count": (
            {"count": employees, "year": "2026", "source_url": f"https://{domain}/"}
            if employees
            else None
        ),
    }
    return {"input_tokens": 3000, "output_tokens": 220, "data": data}


def score(audience: int, ads: int, budget: int, launches: int) -> dict:
    ratings = [
        ("audience", audience, ["categories"]),
        ("ad_activity", ads, ["ad_signals"]),
        ("budget_capacity", budget, ["employee_count"]),
        ("recent_launches", launches, ["recent_launches"]),
    ]
    return {
        "input_tokens": 1800,
        "cache_read_tokens": 1200,  # the rubric prefix, cached after the first lead
        "output_tokens": 160,
        "data": {
            "ratings": [
                {"criterion": c, "rating": r, "reason": f"{c} reason.", "cited_fields": f}
                for c, r, f in ratings
            ]
        },
    }


def fetch(domain: str, worker: str, path: str) -> dict:
    return {
        "stop_reason": "tool_use",
        "input_tokens": 2000,
        "output_tokens": 80,
        "content": [
            {
                "type": "tool_use",
                "id": f"fetch_{worker}",
                "name": "fetch_page",
                "input": {"url": f"https://{domain}{path}"},
            }
        ],
    }


def submit(worker: str, claims: list[dict]) -> dict:
    return {
        "stop_reason": "tool_use",
        "input_tokens": 2600,
        "output_tokens": 200,
        "content": [
            {
                "type": "tool_use",
                "id": f"submit_{worker}",
                "name": "submit_findings",
                "input": {"claims": claims, "gaps": []},
            }
        ],
    }


def worker_answers(domain: str, fails: tuple[str, ...] = ()) -> dict[str, list[dict]]:
    name, product, launch, when, *_ = COMPANIES[domain]
    quotes = {
        "worker_audience": (
            "audience_channels",
            "/",
            f"{name} makes {product} for PC and console gamers.",
        ),
        "worker_ads": (
            "ad_activity",
            "/",
            f"{name} advertises on gaming video channels every month.",
        ),
        "worker_launches": ("launches", "/news", f"{name} launched {launch} in {when}."),
    }
    found = {}
    for worker, (topic, path, quote) in quotes.items():
        key = f"{domain}|{worker}"
        if worker in fails:
            found[key] = [{"text": "I found nothing I can submit."}]
            continue
        claim = {
            "topic": topic,
            "text": quote,
            "source_url": f"https://{domain}{path}",
            "quote": quote,
        }
        found[key] = [fetch(domain, worker, path), submit(worker, [claim])]
    return found


def merge(points: list[tuple[str, list[str]]]) -> dict:
    return {"data": {"summary_points": [{"text": t, "claim_ids": ids} for t, ids in points]}}


GOOD_DRAFT = {
    "subject": "A launch-week idea for Alpha Gear's K1",
    "sentences": [
        {
            "text": "Alpha Gear's K1 keyboard launch in September 2026 caught our attention.",
            "supports": ["L1"],
        },
        {
            "text": "You already advertise on gaming video channels every month, so your buyers are clearly watching.",
            "supports": ["D1"],
        },
        {
            "text": "Fixture Gaming Media reaches 2.4 million monthly readers in the US and Canada.",
            "supports": ["mk-audience"],
        },
        {
            "text": "Our video channels draw 900,000 views a month from PC and console players.",
            "supports": ["mk-video"],
        },
        {
            "text": "A launch-week takeover with sponsored reviews could put the K1 in front of those players while interest is high.",
            "supports": ["mk-formats", "L1"],
        },
        {
            "text": "Would you be open to a short call next week to talk through options and timing?",
            "supports": [],
        },
    ],
}


def hotel_draft() -> dict:
    draft = copy.deepcopy(GOOD_DRAFT)
    draft["subject"] = "A launch-week idea for Hotel Gear's H5"
    draft["sentences"][0] = {
        "text": "Hotel Gear's H5 headset launch in August 2026 caught our attention.",
        "supports": ["L1"],
    }
    draft["sentences"][1] = {
        "text": "Your headsets already reach PC and console gamers, so your buyers are easy to find.",
        "supports": ["A1"],
    }
    draft["sentences"][4] = {
        "text": "A launch-week takeover with sponsored reviews could put the H5 in front of those players while interest is high.",
        "supports": ["mk-formats", "L1"],
    }
    return draft


def golf_draft() -> dict:
    draft = copy.deepcopy(GOOD_DRAFT)
    draft["subject"] = "An idea for Golf Gear"
    draft["sentences"][0] = {
        "text": "Golf Gear's G7 microphone sold 3 million units last year.",
        "supports": ["L1"],
    }
    return draft


def write_models() -> None:
    answers = {
        "extract": {domain: [extraction(domain)] for domain in COMPANIES},
        "score": {
            "alpha.test": [score(5, 4, 4, 3)],  # 80: research
            "delta.test": [score(2, 2, 1, 2)],  # 30: below threshold
            "echo.test": [score(4, 4, 3, 1)],  # 58.75: near miss
            "foxtrot.test": [score(5, 4, 3, 3)],  # 76.25: research
            "golf.test": [score(4, 4, 4, 3)],  # 71.25: research
            "hotel.test": [score(5, 4, 3, 4)],  # 80: research
        },
        "research_plan": {
            domain: [
                {
                    "data": {
                        "assignments": [
                            {"worker": w, "questions": [f"{w} question?"]}
                            for w in ("worker_audience", "worker_ads", "worker_launches")
                        ]
                    }
                }
            ]
            for domain in ("alpha.test", "foxtrot.test", "golf.test", "hotel.test")
        },
        "research_worker": {
            **worker_answers("alpha.test"),
            **worker_answers(
                "foxtrot.test", fails=("worker_audience", "worker_ads", "worker_launches")
            ),
            **worker_answers("golf.test"),
            **worker_answers("hotel.test", fails=("worker_ads",)),
        },
        "research_merge": {
            "alpha.test": [
                merge(
                    [
                        ("Alpha Gear sells keyboards and mice to PC and console gamers.", ["A1"]),
                        ("It launched the K1 keyboard in September 2026.", ["L1"]),
                    ]
                )
            ],
            "golf.test": [
                merge([("Golf Gear launched the G7 microphone in September 2026.", ["L1"])])
            ],
            "hotel.test": [
                merge([("Hotel Gear makes headsets for PC and console gamers.", ["A1"])])
            ],
        },
        "draft_writer": {
            "Alpha Gear": [{"data": GOOD_DRAFT}],
            "Golf Gear": [{"data": golf_draft()}],
            "Hotel Gear": [{"data": hotel_draft()}],
        },
        "draft_critic": {
            "Alpha Gear": [{"data": {"verdict": "approve", "issues": []}}],
            "Hotel Gear": [
                {
                    "data": {
                        "verdict": "revise",
                        "issues": [{"aspect": "ask", "problem": "The ask could name a date."}],
                    }
                }
            ],
        },
    }
    header = (
        "# Scripted model answers for the offline run of the real pipeline on synthetic\n"
        "# companies. Written by tests/fixtures/make_offline_run.py; every number is made up.\n"
    )
    MODELS.write_text(
        header + yaml.safe_dump({"answers": answers}, sort_keys=True, width=100),
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    write_sites()
    write_models()
    print(f"wrote {SITES} and {MODELS}")
    print(json.dumps(sorted(COMPANIES)))
