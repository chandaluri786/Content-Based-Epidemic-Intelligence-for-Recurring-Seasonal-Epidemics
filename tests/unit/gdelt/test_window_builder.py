from datetime import date

import pytest

from pipeline.gdelt.window_builder import (
    build_date_to_countries_index,
    build_window_for_country_season,
    build_windows_from_ground_truth,
    compute_calendar_date_union,
)
from pipeline.ground_truth.ground_truth_builder import CountrySeasonOnset


def onset_row(iso3, year, onset_date, included=True):
    return CountrySeasonOnset(
        country_iso3=iso3,
        country_display=iso3,
        year=year,
        source="FluNet",
        onset_method="positivity_2wk",
        onset_iso_week=5,
        onset_date=onset_date,
        value_at_onset=12.0,
        data_quality_flag="ok",
        included_in_gdelt_cohort=included,
    )


@pytest.mark.unit
class TestBuildWindowForCountrySeason:
    def test_onset_date_is_preserved(self):
        window = build_window_for_country_season(
            "USA", 2023, date(2023, 2, 1), weeks_before=10, weeks_after=2
        )
        assert window.onset_date == date(2023, 2, 1)
        assert window.country_iso3 == "USA"
        assert window.season_year == 2023

    def test_window_end_is_after_onset(self):
        window = build_window_for_country_season(
            "USA", 2023, date(2023, 2, 1), weeks_before=10, weeks_after=2
        )
        assert window.window_end_date == date(2023, 2, 15)

    def test_window_start_is_before_onset(self):
        window = build_window_for_country_season(
            "USA", 2023, date(2023, 2, 1), weeks_before=10, weeks_after=2
        )
        assert window.window_start_date == date(2022, 11, 23)


@pytest.mark.unit
class TestBuildWindowsFromGroundTruth:
    def test_excludes_rows_without_a_cohort_flag(self):
        rows = [
            onset_row("USA", 2023, date(2023, 2, 1), included=True),
            onset_row("BRA", 2023, date(2023, 2, 1), included=False),
        ]
        windows = build_windows_from_ground_truth(rows)
        assert [w.country_iso3 for w in windows] == ["USA"]

    def test_excludes_rows_with_no_onset_date(self):
        rows = [onset_row("USA", 2023, None, included=True)]
        windows = build_windows_from_ground_truth(rows)
        assert windows == []

    def test_includes_multiple_valid_rows(self):
        rows = [
            onset_row("USA", 2022, date(2022, 2, 1)),
            onset_row("USA", 2023, date(2023, 2, 1)),
        ]
        windows = build_windows_from_ground_truth(rows)
        assert len(windows) == 2


@pytest.mark.unit
class TestComputeCalendarDateUnion:
    def test_union_of_overlapping_windows_has_no_duplicates(self):
        w1 = build_window_for_country_season(
            "USA", 2023, date(2023, 1, 10), weeks_before=1, weeks_after=1
        )
        w2 = build_window_for_country_season(
            "GBR", 2023, date(2023, 1, 12), weeks_before=1, weeks_after=1
        )
        union = compute_calendar_date_union([w1, w2])
        assert date(2023, 1, 10) in union
        expected_days = (w1.window_end_date - w1.window_start_date).days + 1
        assert len(union) < 2 * expected_days  # overlap reduces the union below the naive sum

    def test_single_window_union_size_matches_day_count(self):
        w = build_window_for_country_season(
            "USA", 2023, date(2023, 1, 10), weeks_before=1, weeks_after=1
        )
        union = compute_calendar_date_union([w])
        assert len(union) == (w.window_end_date - w.window_start_date).days + 1

    def test_empty_windows_returns_empty_set(self):
        assert compute_calendar_date_union([]) == set()


@pytest.mark.unit
class TestBuildDateToCountriesIndex:
    def test_a_shared_day_lists_both_countries(self):
        w1 = build_window_for_country_season(
            "USA", 2023, date(2023, 1, 10), weeks_before=0, weeks_after=0
        )
        w2 = build_window_for_country_season(
            "GBR", 2023, date(2023, 1, 10), weeks_before=0, weeks_after=0
        )
        index = build_date_to_countries_index([w1, w2])
        assert index[date(2023, 1, 10)] == ["GBR", "USA"]

    def test_a_day_only_in_one_window_lists_only_that_country(self):
        w1 = build_window_for_country_season(
            "USA", 2023, date(2023, 1, 10), weeks_before=0, weeks_after=0
        )
        index = build_date_to_countries_index([w1])
        assert index[date(2023, 1, 10)] == ["USA"]
