"""
Unit tests for the pure-logic stages (parsing and theme matching) -- no
network calls needed, since Stages 4 and 5 are deterministic functions of
their input. Run with: pytest

Stages that require live network access (ground truth, downloading,
fetching, extraction) are not unit-tested here; they'd need either real
network access or mocked HTTP responses, neither of which this generated
scaffolding includes yet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.gkg_parser import parse_line
from pipeline.theme_matcher import (
    countries_mentioned,
    flu_theme_hits,
    has_excluded_theme,
    has_location_match,
    has_theme_match,
    is_flu_candidate,
)

# A real cohort-country location entry (United States), used in tests that
# need Stage 5's location condition to pass. Format confirmed against live
# GKG data -- see pipeline/gkg_parser.py.
_US_LOCATION = "1#United States#US#US##39.8#-98.5#US#580"
_TEST_COUNTRIES = {"USA": "US", "IND": "IN"}  # small stand-in for config.TARGET_COUNTRIES


def _build_raw_line(url: str, themes_field: str, locations_field: str) -> str:
    """Builds a minimal 27-field raw GKG line with only the fields the
    parser actually reads populated -- matches the real field positions
    (field 5 = URL, field 9 = Themes_V2, field 11 = Locations_V2)."""
    fields = [""] * 27
    fields[0] = "20230115121500-0"
    fields[1] = "20230115121500"
    fields[4] = url
    fields[8] = themes_field
    fields[10] = locations_field
    return "\t".join(fields)


def test_parse_line_extracts_url_themes_and_locations():
    raw = _build_raw_line(
        url="https://example.com/flu-shot-article",
        themes_field="TAX_DISEASE_INFLUENZA,626;GENERAL_HEALTH,600",
        locations_field="1#United States#US#US##39.8#-98.5#US#580",
    )
    record = parse_line(raw)
    assert record is not None
    assert record.url == "https://example.com/flu-shot-article"
    assert len(record.themes) == 2
    assert record.themes[0].theme == "TAX_DISEASE_INFLUENZA"
    assert record.themes[0].char_offset == 626
    assert len(record.locations) == 1
    assert record.locations[0].country_fips == "US"


def test_parse_line_skips_malformed_location_entry():
    raw = _build_raw_line(
        url="https://example.com/x",
        themes_field="TAX_DISEASE_FLU,10",
        locations_field="1#Incomplete#US",  # only 3 of the expected 9 sub-fields
    )
    record = parse_line(raw)
    assert record is not None
    assert record.locations == ()  # malformed entry skipped, not guessed at


def test_parse_line_returns_none_for_empty_url():
    raw = _build_raw_line(url="", themes_field="TAX_DISEASE_FLU,10", locations_field="")
    assert parse_line(raw) is None


def test_is_flu_candidate_true_for_theme_and_location_match():
    record = parse_line(_build_raw_line("https://x", "TAX_DISEASE_FLU,10", _US_LOCATION))
    assert has_theme_match(record)
    assert has_location_match(record, _TEST_COUNTRIES)
    assert is_flu_candidate(record, _TEST_COUNTRIES)
    assert len(flu_theme_hits(record)) == 1


def test_is_flu_candidate_false_when_theme_matches_but_no_target_country_mentioned():
    """Theme alone isn't enough -- Stage 5 requires both conditions."""
    record = parse_line(_build_raw_line("https://x", "TAX_DISEASE_FLU,10", ""))
    assert has_theme_match(record)
    assert not has_location_match(record, _TEST_COUNTRIES)
    assert not is_flu_candidate(record, _TEST_COUNTRIES)


def test_is_flu_candidate_false_when_location_matches_but_no_relevant_theme():
    """Location alone isn't enough either."""
    record = parse_line(_build_raw_line("https://x", "TAX_DISEASE_CANCER,10", _US_LOCATION))
    assert not has_theme_match(record)
    assert has_location_match(record, _TEST_COUNTRIES)
    assert not is_flu_candidate(record, _TEST_COUNTRIES)
    assert flu_theme_hits(record) == []


def test_is_flu_candidate_false_when_exclude_theme_present():
    """An avian-flu theme overrides a human-flu theme match, even when
    both appear on the same record and a target country is mentioned."""
    record = parse_line(_build_raw_line(
        "https://x", "TAX_DISEASE_FLU,10;TAX_DISEASE_AVIAN_INFLUENZA,20", _US_LOCATION,
    ))
    assert has_excluded_theme(record)
    assert not is_flu_candidate(record, _TEST_COUNTRIES)


def test_location_filter_respects_the_passed_in_country_set():
    """A location filter scoped to {USA, IND} shouldn't match an article
    that only mentions a country outside that set -- this is what makes
    `--countries USA` on the CLI actually narrow the location filter,
    rather than silently falling back to the full cohort."""
    kenya_location = "1#Kenya#KE#KE##1.0#38.0#KE#100"
    record = parse_line(_build_raw_line("https://x", "TAX_DISEASE_FLU,10", kenya_location))
    assert countries_mentioned(record, _TEST_COUNTRIES) == set()
    assert not is_flu_candidate(record, _TEST_COUNTRIES)
    # the same record WOULD match against a country set that includes Kenya
    assert countries_mentioned(record, {"KEN": "KE"}) == {"KEN"}
