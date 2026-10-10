"""
Unit tests for pooled-article season assignment
(dataset_prep/season_assign.py). No network. Run with: pytest
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_prep.season_assign import assign, build_day_index
from models import CountrySeasonWindow

COUNTRIES = {"USA": "US", "AUS": "AS", "IND": "IN"}


def _window(country: str, season: int, start: date, end: date) -> CountrySeasonWindow:
    return CountrySeasonWindow(country_iso3=country, season_year=season, onset_date=start,
                               window_start=start, window_end=end)


def _record(dt: str, fips: list[str]) -> dict:
    return {"gkg_record_id": "R1", "datetime": dt,
            "locations": [{"name": f, "country_fips": f, "offset": i} for i, f in enumerate(fips)]}


WINDOWS = [
    _window("USA", 2023, date(2023, 9, 25), date(2023, 12, 25)),
    _window("AUS", 2023, date(2023, 10, 1), date(2023, 12, 31)),
    _window("IND", 2023, date(2023, 3, 1), date(2023, 5, 1)),
]


def test_country_seasons_lists_every_window_containing_the_date():
    index = build_day_index(WINDOWS)
    result = assign(_record("2023-11-01T10:00:00", ["US"]), index, COUNTRIES)
    assert result.country_seasons == ("AUS-2023", "USA-2023")


def test_sampling_country_is_the_most_mentioned_country_with_an_active_window():
    index = build_day_index(WINDOWS)
    result = assign(_record("2023-11-01T10:00:00", ["US", "AS", "AS", "IN", "IN", "IN"]), index, COUNTRIES)
    assert result.sampling_country == "AUS"           # IND is mentioned most but has no window that day
    assert result.sampling_season == "AUS-2023"


def test_sampling_country_ties_break_by_cohort_order():
    index = build_day_index(WINDOWS)
    result = assign(_record("2023-11-01T10:00:00", ["AS", "US"]), index, COUNTRIES)
    assert result.sampling_country == "USA"


def test_article_outside_every_window_is_unassigned():
    index = build_day_index(WINDOWS)
    result = assign(_record("2023-07-01T10:00:00", ["US"]), index, COUNTRIES)
    assert result.country_seasons == ()
    assert result.sampling_country is None
    assert result.sampling_season is None


def test_article_mentioning_no_active_country_is_unassigned():
    index = build_day_index(WINDOWS)
    result = assign(_record("2023-11-01T10:00:00", ["IN"]), index, COUNTRIES)
    assert result.country_seasons == ("AUS-2023", "USA-2023")
    assert result.sampling_country is None


def test_build_day_index_rejects_same_country_overlap():
    """The invariant that keeps dev and test apart: one season per country per day."""
    overlapping = [_window("USA", 2023, date(2023, 9, 25), date(2023, 12, 18)),
                   _window("USA", 2024, date(2023, 10, 23), date(2024, 1, 15))]
    with pytest.raises(ValueError, match="USA"):
        build_day_index(overlapping)
