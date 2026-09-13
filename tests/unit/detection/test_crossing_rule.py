from datetime import date, timedelta

import pytest

from pipeline.detection.crossing_rule import (
    compute_content_signal_date,
    compute_first_crossing_date,
    compute_frequency_signal_date,
)
from pipeline.join.epiweek_join import CountryWeekJoined


def make_week(week_index: int, relevant: int, raw: int) -> CountryWeekJoined:
    week_start = date(2023, 1, 2) + timedelta(weeks=week_index)
    return CountryWeekJoined(
        country_iso3="USA",
        season_year=2023,
        iso_year=2023,
        iso_week=week_index + 1,
        week_start_date=week_start,
        content_relevant_count=relevant,
        frequency_raw_count=raw,
        is_baseline_week=week_index < 4,
        days_from_onset=0,
    )


@pytest.mark.unit
class TestComputeFirstCrossingDate:
    def test_no_crossing_returns_none(self):
        weeks = [make_week(i, 0, 0) for i in range(8)]
        result = compute_first_crossing_date(weeks, lambda w: w.content_relevant_count)
        assert result is None

    def test_returns_the_week_start_date_of_the_first_sustained_crossing(self):
        counts = [1, 1, 1, 1, 10, 12, 0, 0]
        weeks = [make_week(i, c, 0) for i, c in enumerate(counts)]
        result = compute_first_crossing_date(weeks, lambda w: w.content_relevant_count)
        assert result == date(2023, 1, 2) + timedelta(weeks=4)

    def test_crossing_within_baseline_period_is_not_counted(self):
        # A spike inside the first 4 (baseline) weeks is excluded from the scan
        # (it also raises the baseline's own mean/stdev, so it self-inflates
        # the threshold it would have needed to cross).
        counts = [50, 50, 0, 0, 0, 0, 0, 0]
        weeks = [make_week(i, c, 0) for i, c in enumerate(counts)]
        result = compute_first_crossing_date(
            weeks, lambda w: w.content_relevant_count, baseline_weeks=4
        )
        assert result is None

    def test_empty_weeks_returns_none(self):
        assert compute_first_crossing_date([], lambda w: w.content_relevant_count) is None


@pytest.mark.unit
class TestComputeContentAndFrequencySignalDates:
    def test_content_and_frequency_are_computed_independently(self):
        weeks = [make_week(i, relevant=0, raw=(15 if i >= 4 else 0)) for i in range(8)]
        # Bump content counts only in later weeks, well past frequency's crossing.
        weeks[6] = CountryWeekJoined(**{**weeks[6].__dict__, "content_relevant_count": 15})
        weeks[7] = CountryWeekJoined(**{**weeks[7].__dict__, "content_relevant_count": 15})

        content_date = compute_content_signal_date(weeks)
        frequency_date = compute_frequency_signal_date(weeks)

        assert frequency_date == date(2023, 1, 2) + timedelta(weeks=4)
        assert content_date == date(2023, 1, 2) + timedelta(weeks=6)
