"""The owner-approved site list (Phase 2 design, decision 11)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from adscout.config import ConfigError
from adscout.sources.site_list import company_site_refusal, load_site_list, site_list_path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "config" / "site-checks"


def raw() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(site_list_path("synthetic-demo", FIXTURES).read_text())
    return data


def write(tmp_path: Path, data: dict[str, Any], name: str = "synthetic-demo") -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_fixture_list_loads_and_answers_for_each_domain() -> None:
    sites = load_site_list(site_list_path("synthetic-demo", FIXTURES))
    assert sites.approval.given
    assert sites.live_refusal("alpha.test") is None
    assert sites.live_refusal("https://www.alpha.test/shop") is None
    assert "skips bravo.test: robots.txt disallows" in str(sites.live_refusal("bravo.test"))
    assert "not on the approved site list for synthetic-demo" in str(
        sites.live_refusal("charlie.test")
    )


def test_unapproved_list_refuses_every_domain(tmp_path: Path) -> None:
    data = raw()
    data["approval"] = {"approved_by": None, "approved_on": None, "note": "awaiting review"}
    sites = load_site_list(write(tmp_path, data))
    assert "not approved by the owner yet" in str(sites.live_refusal("alpha.test"))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["sites"].append(dict(d["sites"][0])), "listed twice"),
        (lambda d: d["sites"][0].update(decision="maybe"), "decision"),
        (lambda d: d["sites"][0].update(terms_checked_on=None), "check date"),
        (lambda d: d["approval"].update(approved_on=None), "both who approved and when"),
        (lambda d: d["sites"][0].update(notes="x"), "notes"),
        (lambda d: d.update(segment_id="other"), "differs from the file"),
        (lambda d: d["sites"][0].update(reason="call +1 514 555 0100"), "phone number"),
    ],
)
def test_invalid_lists_are_refused(tmp_path: Path, change: Any, message: str) -> None:
    data = raw()
    change(data)
    with pytest.raises(ConfigError, match=message):
        load_site_list(write(tmp_path, data))


def test_hash_ignores_formatting(tmp_path: Path) -> None:
    original = load_site_list(site_list_path("synthetic-demo", FIXTURES))
    assert load_site_list(write(tmp_path, raw())).content_hash() == original.content_hash()


def test_only_live_runs_need_the_approved_list() -> None:
    sites = load_site_list(site_list_path("synthetic-demo", FIXTURES))
    assert company_site_refusal("fixture", None, "anything.test") is None
    assert company_site_refusal("replay", None, "anything.test") is None
    assert "none is loaded" in str(company_site_refusal("live", None, "alpha.test"))
    assert company_site_refusal("live", sites, "alpha.test") is None
    assert "not on the approved" in str(company_site_refusal("live", sites, "charlie.test"))
