from datetime import date

import pytest

from pipeline.join.epiweek_join import (
    ArticleWeekRecord,
    CountrySeasonWindow,
    build_week_counts,
    join_to_ground_truth,
)


@pytest.mark.unit
class TestBuildWeekCounts:
    def test_counts_all_records_when_relevant_only_is_false(self):
        records = [
            ArticleWeekRecord("USA", 2023, 1, is_relevant=False),
            ArticleWeekRecord("USA", 2023, 1, is_relevant=True),
            ArticleWeekRecord("USA", 2023, 2, is_relevant=True),
        ]
        counts = build_week_counts(records, relevant_only=False)
        assert counts == {("USA", 2023, 1): 2, ("USA", 2023, 2): 1}

    def test_counts_only_relevant_records_when_relevant_only_is_true(self):
        records = [
            ArticleWeekRecord("USA", 2023, 1, is_relevant=False),
            ArticleWeekRecord("USA", 2023, 1, is_relevant=True),
        ]
        counts = build_week_counts(records, relevant_only=True)
        assert counts == {("USA", 2023, 1): 1}

    def test_empty_records_returns_empty_dict(self):
        assert build_week_counts([], relevant_only=True) == {}

    def test_separates_counts_by_country(self):
        records = [
            ArticleWeekRecord("USA", 2023, 1, is_relevant=True),
            ArticleWeekRecord("GBR", 2023, 1, is_relevant=True),
        ]
        counts = build_week_counts(records, relevant_only=True)
        assert counts == {("USA", 2023, 1): 1, ("GBR", 2023, 1): 1}


@pytest.mark.unit
class TestJoinToGroundTruth:
    def test_dense_join_includes_zero_weeks(self):
        window = CountrySeasonWindow(
            country_iso3="USA",
            season_year=2023,
            window_start_date=date(2023, 1, 2),
            window_end_date=date(2023, 1, 16),
            onset_date=date(2023, 1, 9),
            baseline_weeks=1,
        )
        rows = join_to_ground_truth(
            relevant_counts={("USA", 2023, 2): 5},
            raw_counts={},
            windows=[window],
        )
        assert len(rows) == 3
        assert [r.content_relevant_count for r in rows] == [0, 5, 0]
        assert [r.frequency_raw_count for r in rows] == [0, 0, 0]

    def test_is_baseline_week_flags_the_first_n_weeks(self):
        window = CountrySeasonWindow(
            country_iso3="USA",
            season_year=2023,
            window_start_date=date(2023, 1, 2),
            window_end_date=date(2023, 1, 23),
            onset_date=date(2023, 1, 16),
            baseline_weeks=2,
        )
        rows = join_to_ground_truth(relevant_counts={}, raw_counts={}, windows=[window])
        assert [r.is_baseline_week for r in rows] == [True, True, False, False]

    def test_days_from_onset_is_computed_relative_to_onset_date(self):
        window = CountrySeasonWindow(
            country_iso3="USA",
            season_year=2023,
            window_start_date=date(2023, 1, 2),
            window_end_date=date(2023, 1, 16),
            onset_date=date(2023, 1, 9),
            baseline_weeks=1,
        )
        rows = join_to_ground_truth(relevant_counts={}, raw_counts={}, windows=[window])
        assert [r.days_from_onset for r in rows] == [-7, 0, 7]

    def test_multiple_windows_produce_independent_rows(self):
        window_a = CountrySeasonWindow(
            "USA", 2023, date(2023, 1, 2), date(2023, 1, 2), date(2023, 1, 2), 1
        )
        window_b = CountrySeasonWindow(
            "GBR", 2023, date(2023, 1, 2), date(2023, 1, 2), date(2023, 1, 2), 1
        )
        rows = join_to_ground_truth(relevant_counts={}, raw_counts={}, windows=[window_a, window_b])
        assert {r.country_iso3 for r in rows} == {"USA", "GBR"}

    def test_frequency_count_is_independent_of_relevant_count(self):
        window = CountrySeasonWindow(
            "USA", 2023, date(2023, 1, 2), date(2023, 1, 2), date(2023, 1, 2), 1
        )
        rows = join_to_ground_truth(
            relevant_counts={("USA", 2023, 1): 2},
            raw_counts={("USA", 2023, 1): 10},
            windows=[window],
        )
        assert rows[0].content_relevant_count == 2
        assert rows[0].frequency_raw_count == 10

    def test_year_boundary_window_produces_correct_iso_weeks(self):
        window = CountrySeasonWindow(
            "USA", 2023, date(2022, 12, 26), date(2023, 1, 9), date(2023, 1, 2), 1
        )
        rows = join_to_ground_truth(relevant_counts={}, raw_counts={}, windows=[window])
        assert [(r.iso_year, r.iso_week) for r in rows] == [(2022, 52), (2023, 1), (2023, 2)]
