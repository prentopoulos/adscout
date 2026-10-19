"""Field validators, source choice, ad-tag detection and page handling (decisions 7 and 8)."""

from datetime import date
from typing import Any

import pytest

from adscout.enrichment.countries import ALPHA_2
from adscout.enrichment.fields import (
    Candidate,
    Checked,
    check,
    choose,
    missing_key_fields,
    valid_values,
)
from adscout.enrichment.pages import pick_pages, site_links, text_of
from adscout.enrichment.tags import detect

TODAY = date(2026, 10, 19)
CATEGORIES = ("peripherals", "pc-components", "prebuilt-pcs", "console-accessories")


def candidate(field: str, value: Any, **changes: Any) -> Candidate:
    values: dict[str, Any] = {
        "field": field,
        "value": value,
        "source_url": "https://example.test/",
        "source_kind": "company_site",
        "method": "extracted",
        "retrieved_at": "2026-10-19T00:00:00.000Z",
    } | changes
    return Candidate(**values)


def checked(field: str, value: Any, **changes: Any) -> list[Checked]:
    return check(candidate(field, value, **changes), CATEGORIES, TODAY)


def statuses(rows: list[Checked]) -> list[tuple[str, Any]]:
    return [(row.status, row.value) for row in rows]


def test_country_list_is_the_249_assigned_codes() -> None:
    assert len(ALPHA_2) == 249
    assert {"US", "CA", "GB", "TW", "HK"} <= ALPHA_2
    assert not {"UK", "EU", "USA"} & ALPHA_2


def test_invalid_country_code_is_dropped_and_the_rest_kept() -> None:
    rows = checked("sells_in", ["USA", "CA"])
    assert statuses(rows) == [("valid", ["CA"]), ("dropped", ["USA"])]
    assert rows[1].detail == "not ISO 3166-1 alpha-2 codes"
    assert statuses(checked("sells_in", ["Canada"])) == [("dropped", ["Canada"])]


def test_categories_come_from_the_segment_list() -> None:
    rows = checked("categories", ["Peripherals", "furniture", "peripherals"])
    assert statuses(rows) == [("valid", ["peripherals"]), ("dropped", ["furniture"])]


@pytest.mark.parametrize(
    ("value", "as_of", "message"),
    [
        (1200, None, "as-of date"),
        (1200, "2027-01-01", "in the future"),
        (0, "2025", "positive whole number"),
        (True, "2025", "positive whole number"),
        ("1,200", "2025", "positive whole number"),
    ],
)
def test_employee_count_needs_a_positive_count_and_a_past_as_of(
    value: Any, as_of: str | None, message: str
) -> None:
    [row] = checked("employee_count", value, as_of=as_of)
    assert row.status == "dropped" and message in str(row.detail)


def test_employee_count_from_sec_beats_wikidata_and_the_site() -> None:
    rows = [
        *checked("employee_count", {"count": 900}, source_kind="company_site", as_of="2026"),
        *checked("employee_count", 1100, source_kind="wikidata", as_of="2024-12-31"),
        *checked("employee_count", 1200, source_kind="sec_edgar", as_of="2025-12-31"),
    ]
    final = choose(rows)
    assert valid_values(final)["employee_count"].value == {"count": 1200}
    assert sorted(row.detail or "" for row in final if row.status == "dropped") == [
        "superseded by sec_edgar",
        "superseded by sec_edgar",
    ]


def test_revenue_only_for_a_public_company() -> None:
    revenue = {"amount": 1.5e9, "currency": "USD", "fiscal_year": 2025}
    from_wikidata = checked("revenue_usd", revenue, source_kind="wikidata", as_of="2025-12-31")
    private = checked("ownership", "private", source_kind="wikidata")
    final = choose([*from_wikidata, *private])
    assert "revenue_usd" not in valid_values(final)
    assert final[0].detail == "revenue is kept only for public companies"
    public = checked("ownership", "public", source_kind="wikidata")
    assert valid_values(choose([*from_wikidata, *public]))["revenue_usd"].value == {
        "amount": 1.5e9,
        "currency": "USD",
        "period_end": "2025-12-31",
        "fiscal_year": 2025,
    }
    from_sec = checked("revenue_usd", revenue, source_kind="sec_edgar", as_of="2025-12-31")
    assert "revenue_usd" in valid_values(choose(from_sec))
    [euros] = checked("revenue_usd", {"amount": 5, "currency": "EUR"}, as_of="2025")
    assert euros.detail == "revenue must be in US dollars"


def test_launches_need_a_source_and_a_recent_date() -> None:
    launches = [
        {"name": "K70 Pro", "date": "2026-09", "source_url": "https://example.test/news/k70"},
        {"name": "Old mouse", "date": "2023-01-15", "source_url": "https://example.test/a"},
        {"name": "No source", "date": "2026-05"},
        {"name": "Undated", "date": None, "source_url": "https://example.test/b"},
    ]
    [kept, dropped] = checked("recent_launches", launches)
    assert [item["name"] for item in kept.value] == ["K70 Pro", "Undated"]
    assert [item["name"] for item in dropped.value] == ["Old mouse", "No source"]


def test_a_creator_sponsorship_keeps_no_name() -> None:
    items = [
        {"kind": "creator", "name": "A Streamer", "source_url": "https://example.test/s"},
        {"kind": "esports_team", "name": "Team Example", "source_url": "https://example.test/t"},
    ]
    [kept] = checked("sponsorships", items)
    assert {(item["kind"], item["name"]) for item in kept.value} == {
        ("creator", None),
        ("esports_team", "Team Example"),
    }


def test_social_accounts_never_keep_follower_counts() -> None:
    accounts = [
        {"platform": "youtube", "id": "UC123", "url": "https://www.youtube.com/channel/UC123"},
        {"platform": "youtube", "id": "UC9", "url": "https://youtube.test/", "subscribers": 5},
        {"platform": "myspace", "id": "x", "url": "https://myspace.test/x"},
    ]
    [kept, dropped] = checked("social_accounts", accounts)
    assert [item["id"] for item in kept.value] == ["UC123"]
    assert len(dropped.value) == 2 and "no follower counts" in str(dropped.detail)


def test_contact_data_and_bad_sources_are_dropped_whole() -> None:
    [row] = checked("parent", "Write to ceo@example.test")
    assert row.status == "dropped" and row.value is None and "email" in str(row.detail)
    [row] = checked("hq_country", "US", source_url="ftp://example.test/")
    assert row.detail == "the source URL is not absolute http(s)"
    [row] = checked("hq_country", "USA")
    assert "not an ISO 3166-1 alpha-2 code" in str(row.detail)
    [row] = checked("ownership", "family")
    assert row.status == "dropped"
    [row] = checked("categories", "peripherals")
    assert row.detail == "expected a list"


def test_missing_key_fields_are_named() -> None:
    rows = [*checked("categories", ["peripherals"]), *checked("sells_in", ["US", "CA"])]
    assert missing_key_fields(rows) == ["employee_count"]


def test_ad_signals_must_be_known_tags_of_their_kind() -> None:
    signals = [
        {"tag": "meta_pixel", "kind": "ad_pixel", "host": "connect.facebook.net"},
        {"tag": "meta_pixel", "kind": "analytics", "host": "x"},
        {"tag": "made_up", "kind": "ad_pixel", "host": "x"},
    ]
    [kept, dropped] = checked("ad_signals", signals, method="parsed")
    assert [item["tag"] for item in kept.value] == ["meta_pixel"]
    assert len(dropped.value) == 2
    assert statuses(checked("ad_signals", [], method="parsed")) == [("valid", [])]


HOME = """
<html><head><title>Example</title><script src="https://www.googletagmanager.com/gtm.js?id=GTM-1"></script>
<script>!function(f){f.fbq('init','1')}(window);</script>
<script src="https://connect.facebook.net/en_US/fbevents.js"></script></head>
<body><nav><a href="/news">Newsroom</a> <a href="https://shop.example.test/shipping">Shipping</a>
<a href="https://elsewhere.test/press">Press elsewhere</a> <a href="mailto:x@example.test">Mail</a>
<a href="/#top">Home</a></nav>
<style>.x{color:red}</style><h1>Gaming gear</h1><p>Keyboards and   mice.</p>
<noscript><img src="https://www.facebook.com/tr?id=1"></noscript></body></html>
"""


def test_tags_are_detected_from_raw_html_without_a_model() -> None:
    assert detect(HOME) == [
        {"tag": "google_tag_manager", "kind": "tag_manager", "host": "googletagmanager.com"},
        {"tag": "meta_pixel", "kind": "ad_pixel", "host": "connect.facebook.net"},
    ]
    assert detect("<p>Follow us on facebook and google</p>") == []


def test_page_text_skips_scripts_and_styles() -> None:
    text = text_of(HOME)
    assert "Gaming gear" in text and "Keyboards and mice." in text
    assert "fbq" not in text and "color:red" not in text and "Example" not in text


def test_links_stay_on_site_and_pick_news_and_store_pages() -> None:
    links = [url for url, _ in site_links(HOME, "https://example.test/", "example.test")]
    assert links == [
        "https://example.test/news",
        "https://shop.example.test/shipping",
        "https://example.test/",
    ]
    assert pick_pages(HOME, "https://example.test/", "example.test") == [
        "https://example.test/news",
        "https://shop.example.test/shipping",
    ]
