from datetime import date

import pytest

from pipeline.ground_truth.onset_detection import (
    OnsetResult,
    WeeklyValue,
    find_onset_flat_rule,
    find_onset_peak_proxy,
)


def week(iso_year: int, iso_week: int, value: float | None) -> WeeklyValue:
    return WeeklyValue(iso_year=iso_year, iso_week=iso_week, value=value)


@pytest.mark.unit
class TestFindOnsetFlatRule:
    def test_no_data_returns_none(self):
        assert find_onset_flat_rule([]) is None

    def test_all_below_threshold_returns_none(self):
        series = [week(2023, w, 5.0) for w in range(1, 10)]
        assert find_onset_flat_rule(series) is None

    def test_single_week_spike_that_does_not_sustain_returns_none(self):
        series = [week(2023, 1, 2.0), week(2023, 2, 15.0), week(2023, 3, 2.0)]
        assert find_onset_flat_rule(series) is None

    def test_two_week_sustained_crossing_returns_onset_at_first_week(self):
        series = [week(2023, 1, 2.0), week(2023, 2, 12.0), week(2023, 3, 13.0)]
        result = find_onset_flat_rule(series)
        assert result == OnsetResult(
            onset_iso_year=2023,
            onset_iso_week=2,
            onset_date=date.fromisocalendar(2023, 2, 1),
            value_at_onset=12.0,
            onset_method="positivity_2wk",
        )

    def test_none_values_do_not_count_as_crossing(self):
        series = [week(2023, 1, None), week(2023, 2, 12.0), week(2023, 3, 13.0)]
        result = find_onset_flat_rule(series)
        assert result.onset_iso_week == 2

    def test_unsorted_input_is_sorted_before_evaluation(self):
        series = [week(2023, 3, 13.0), week(2023, 1, 2.0), week(2023, 2, 12.0)]
        result = find_onset_flat_rule(series)
        assert result.onset_iso_week == 2

    def test_crossing_spanning_year_boundary(self):
        series = [week(2022, 52, 12.0), week(2023, 1, 13.0)]
        result = find_onset_flat_rule(series)
        assert (result.onset_iso_year, result.onset_iso_week) == (2022, 52)


@pytest.mark.unit
class TestFindOnsetPeakProxy:
    def test_no_data_returns_none(self):
        assert find_onset_peak_proxy([]) is None

    def test_all_none_returns_none(self):
        series = [week(2023, w, None) for w in range(1, 5)]
        assert find_onset_peak_proxy(series) is None

    def test_returns_the_peak_week(self):
        series = [week(2023, 1, 5.0), week(2023, 2, 40.0), week(2023, 3, 10.0)]
        result = find_onset_peak_proxy(series)
        assert result.onset_iso_week == 2
        assert result.onset_method == "peak_count_proxy"
        assert result.value_at_onset == 40.0

    def test_ties_broken_by_earliest_week(self):
        series = [week(2023, 1, 40.0), week(2023, 2, 40.0), week(2023, 3, 10.0)]
        result = find_onset_peak_proxy(series)
        assert result.onset_iso_week == 1
