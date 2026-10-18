"""Segment config and seed list: validation, the contact guard, schemas and content hashes."""

from pathlib import Path

import pytest

from adscout.config import (
    ConfigError,
    contact_kind,
    load_seeds,
    load_segment,
    normalize_domain,
)
from adscout.schema_files import ROOT, schema_files, schema_text

SEGMENT = ROOT / "config" / "segments" / "gaming-hardware-na.yaml"
SEEDS = ROOT / "config" / "seeds" / "gaming-hardware-na.csv"
HEADER = "name,domain,source,added_by,added_on,notes\n"


def write_segment(tmp_path: Path, text: str, name: str = "gaming-hardware-na") -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def segment_text(**changes: str) -> str:
    text = SEGMENT.read_text(encoding="utf-8")
    for old, new in changes.items():
        assert old in text
        text = text.replace(old, new)
    return text


def write_seeds(tmp_path: Path, *rows: str, header: str = HEADER) -> Path:
    path = tmp_path / "test-segment.csv"
    path.write_text(header + "".join(row + "\n" for row in rows), encoding="utf-8")
    return path


def test_committed_segment_loads() -> None:
    segment = load_segment(SEGMENT)
    assert segment.segment_id == "gaming-hardware-na"
    assert segment.regions == ["US", "CA"]
    assert segment.size_range is None
    assert segment.score_threshold is None
    assert segment.null_reasons["size_range"] == "set in Phase 2 grilling"
    assert segment.null_reasons["score_threshold"] == "set in Phase 2 grilling"


def test_unknown_field_is_rejected_by_name(tmp_path: Path) -> None:
    path = write_segment(tmp_path, segment_text() + "audience_size: 5\n")
    with pytest.raises(ConfigError, match="audience_size"):
        load_segment(path)


def test_unquoted_no_is_not_read_as_a_boolean(tmp_path: Path) -> None:
    path = write_segment(tmp_path, segment_text(**{'regions: ["US", "CA"]': "regions: [US, NO]"}))
    with pytest.raises(ConfigError, match=r"regions\.1"):
        load_segment(path)


def test_null_without_reason_is_rejected(tmp_path: Path) -> None:
    path = write_segment(tmp_path, segment_text(**{"  size_range: set in Phase 2 grilling\n": ""}))
    with pytest.raises(ConfigError, match="size_range"):
        load_segment(path)


def test_segment_id_must_match_the_file(tmp_path: Path) -> None:
    path = write_segment(tmp_path, segment_text(), name="other-segment")
    with pytest.raises(ConfigError, match="differs from the file"):
        load_segment(path)


def test_region_must_be_an_alpha_2_code(tmp_path: Path) -> None:
    path = write_segment(tmp_path, segment_text(**{'["US", "CA"]': '["USA"]'}))
    with pytest.raises(ConfigError, match="ISO 3166-1"):
        load_segment(path)


def test_phone_number_in_config_is_rejected(tmp_path: Path) -> None:
    text = segment_text(**{"wherever they": "call +1 514 555 0100, wherever they"})
    path = write_segment(tmp_path, text)
    with pytest.raises(ConfigError, match="scope contains a phone number") as caught:
        load_segment(path)
    assert "555" not in str(caught.value)


def test_committed_seed_list_loads() -> None:
    seeds = load_seeds(SEEDS)
    assert [row.domain for row in seeds.rows] == [
        "8bitdo.com",
        "corsair.com",
        "nzxt.com",
        "razer.com",
        "turtlebeach.com",
    ]
    assert seeds.duplicate_domains() == []


def test_committed_seed_rows_record_provenance() -> None:
    for row in load_seeds(SEEDS).rows:
        assert row.source and row.added_by and row.added_on
        assert "Home page checked once on 2026-10-18" in row.notes


def test_extra_seed_column_is_rejected(tmp_path: Path) -> None:
    path = write_seeds(tmp_path, header=HEADER.strip() + ",ceo\n")
    with pytest.raises(ConfigError, match="unexpected: ceo"):
        load_seeds(path)


def test_seed_domains_are_normalized(tmp_path: Path) -> None:
    path = write_seeds(tmp_path, "Example,https://WWW.Example.test:443/shop/,test,me,2026-10-18,")
    assert load_seeds(path).rows[0].domain == "example.test"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.test", "example.test"),
        ("Example.TEST.", "example.test"),
        ("http://www.shop.example.test/a?b#c", "shop.example.test"),
        ("8bitdo.com", "8bitdo.com"),
    ],
)
def test_normalize_domain(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize("raw", ["bücher.example", "not a domain", "localhost", "-bad.example"])
def test_invalid_domains_are_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_domain(raw)


def test_invalid_domain_in_seed_row_names_the_row(tmp_path: Path) -> None:
    path = write_seeds(tmp_path, "Example,bücher.example,test,me,2026-10-18,")
    with pytest.raises(ConfigError, match="row 2"):
        load_seeds(path)


def test_email_in_seed_notes_is_rejected_without_printing_it(tmp_path: Path) -> None:
    path = write_seeds(tmp_path, "Example,example.test,test,me,2026-10-18,ask jane@example.com")
    with pytest.raises(ConfigError, match="row 2 column notes: contains an email") as caught:
        load_seeds(path)
    assert "jane" not in str(caught.value)


def test_duplicate_seed_domains_are_reported_not_merged(tmp_path: Path) -> None:
    path = write_seeds(
        tmp_path,
        "Example,example.test,test,me,2026-10-18,",
        "Example again,www.example.test,test,me,2026-10-18,",
    )
    seeds = load_seeds(path)
    assert len(seeds.rows) == 2
    assert seeds.duplicate_domains() == ["example.test"]


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("write to sales@example.com", "an email address"),
        ("(514) 555-0100", "a phone number"),
        ("+44 20 7946 0958", "a phone number"),
        ("revenue $1,472.5M in 2025", None),
        ("checked on 2026-10-18", None),
        ("sec.gov/Archives/edgar/data/1743759/000119312526048668/crsr-ex99_1.htm", None),
        ("https://www.businesswire.com/news/home/20210324005217/en/Razer", None),
        ("order 20210324005217", "a phone number"),
    ],
)
def test_contact_kind(text: str, kind: str | None) -> None:
    assert contact_kind(text) == kind


@pytest.mark.parametrize("relative", sorted(schema_files()))
def test_committed_schema_matches_model(relative: str) -> None:
    committed = (ROOT / relative).read_text(encoding="utf-8")
    assert committed == schema_text(schema_files()[relative]), (
        "schema file is stale; run `uv run python -m adscout.schema_files`"
    )


def test_comment_edit_keeps_the_config_hash(tmp_path: Path) -> None:
    edited = write_segment(tmp_path, "# a new comment\n" + segment_text())
    assert load_segment(edited).content_hash() == load_segment(SEGMENT).content_hash()


def test_value_edit_changes_the_config_hash(tmp_path: Path) -> None:
    edited = write_segment(
        tmp_path,
        segment_text(**{"  - console-accessories\n": "  - console-accessories\n  - chairs\n"}),
    )
    assert load_segment(edited).content_hash() != load_segment(SEGMENT).content_hash()


def test_seed_hash_ignores_formatting(tmp_path: Path) -> None:
    quoted = write_seeds(tmp_path, '"Example","example.test","test","me","2026-10-18",""')
    plain_path = tmp_path / "plain.csv"
    plain_path.write_text(HEADER + "Example,example.test,test,me,2026-10-18,\n", encoding="utf-8")
    assert load_seeds(quoted).content_hash() == load_seeds(plain_path).content_hash()
