import pytest

from pipeline.detection.baseline_stats import BaselineStats, baseline_threshold, compute_baseline


@pytest.mark.unit
class TestComputeBaseline:
    def test_computes_mean_and_stdev_from_first_n_weeks(self):
        stats = compute_baseline([2, 4, 6, 8, 100, 100], n_baseline_weeks=4)
        assert stats.mean == pytest.approx(5.0)
        assert stats.stdev == pytest.approx(2.581988897)

    def test_series_shorter_than_n_baseline_weeks_uses_all_available(self):
        stats = compute_baseline([2, 4], n_baseline_weeks=4)
        assert stats.mean == pytest.approx(3.0)

    def test_empty_series_returns_zero_stats(self):
        stats = compute_baseline([], n_baseline_weeks=4)
        assert stats == BaselineStats(mean=0.0, stdev=0.0)

    def test_single_value_baseline_has_zero_stdev(self):
        stats = compute_baseline([5], n_baseline_weeks=4)
        assert stats.mean == 5.0
        assert stats.stdev == 0.0

    def test_all_zero_baseline_has_zero_mean_and_stdev(self):
        stats = compute_baseline([0, 0, 0, 0], n_baseline_weeks=4)
        assert stats == BaselineStats(mean=0.0, stdev=0.0)


@pytest.mark.unit
class TestBaselineThreshold:
    def test_threshold_is_mean_plus_z_times_stdev(self):
        stats = BaselineStats(mean=10.0, stdev=2.0)
        assert baseline_threshold(stats, z=2.0, min_absolute_floor=0) == pytest.approx(14.0)

    def test_floor_is_applied_when_zero_variance_baseline_would_undercut_it(self):
        stats = BaselineStats(mean=0.0, stdev=0.0)
        assert baseline_threshold(stats, z=2.0, min_absolute_floor=3) == 3.0

    def test_floor_does_not_reduce_a_naturally_higher_threshold(self):
        stats = BaselineStats(mean=10.0, stdev=5.0)
        assert baseline_threshold(stats, z=2.0, min_absolute_floor=3) == pytest.approx(20.0)
