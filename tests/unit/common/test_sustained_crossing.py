import pytest

from pipeline.common.sustained_crossing import find_sustained_crossing


@pytest.mark.unit
class TestFindSustainedCrossing:
    def test_no_data_returns_none(self):
        assert find_sustained_crossing([], threshold=10.0, sustain_periods=2) is None

    def test_all_zero_series_returns_none(self):
        values = [0.0] * 10
        assert find_sustained_crossing(values, threshold=10.0, sustain_periods=2) is None

    def test_single_period_spike_that_does_not_sustain_returns_none(self):
        values = [0, 0, 15, 0, 0]
        assert find_sustained_crossing(values, threshold=10.0, sustain_periods=2) is None

    def test_exactly_two_period_sustained_crossing_returns_first_index(self):
        values = [0, 0, 12, 13, 0]
        assert find_sustained_crossing(values, threshold=10.0, sustain_periods=2) == 2

    def test_more_than_two_period_sustained_crossing_returns_first_index(self):
        values = [0, 12, 13, 14, 15]
        assert find_sustained_crossing(values, threshold=10.0, sustain_periods=2) == 1

    def test_threshold_exactly_equal_counts_as_crossing(self):
        values = [10.0, 10.0]
        assert find_sustained_crossing(values, threshold=10.0, sustain_periods=2) == 0

    def test_just_below_threshold_does_not_count(self):
        values = [9.999, 9.999]
        assert find_sustained_crossing(values, threshold=10.0, sustain_periods=2) is None

    def test_none_values_in_series_are_treated_as_not_crossing(self):
        values = [None, 12, 13]
        assert find_sustained_crossing(values, threshold=10.0, sustain_periods=2) == 1

    def test_sustain_periods_of_one_returns_first_crossing_index(self):
        values = [0, 0, 11]
        assert find_sustained_crossing(values, threshold=10.0, sustain_periods=1) == 2

    def test_series_shorter_than_sustain_periods_returns_none(self):
        values = [15]
        assert find_sustained_crossing(values, threshold=10.0, sustain_periods=2) is None

    def test_search_start_index_skips_earlier_crossings(self):
        values = [15, 16, 0, 0, 12, 13]
        assert (
            find_sustained_crossing(values, threshold=10.0, sustain_periods=2, start_index=2) == 4
        )

    def test_sustain_periods_less_than_one_raises(self):
        with pytest.raises(ValueError):
            find_sustained_crossing([10, 10], threshold=10.0, sustain_periods=0)
