"""Baseline mean/stdev over the first N weeks of a country-season window
(Step 6), used to set the statistical crossing threshold in crossing_rule.py.
"""

import statistics
from dataclasses import dataclass

from pipeline.config import BASELINE_WEEKS, DETECTION_MIN_ABSOLUTE_FLOOR, DETECTION_Z_SCORE


@dataclass(frozen=True)
class BaselineStats:
    mean: float
    stdev: float


def compute_baseline(
    weekly_counts: list[float], n_baseline_weeks: int = BASELINE_WEEKS
) -> BaselineStats:
    """Sample mean/stdev of the first n_baseline_weeks values (or all of them,
    if the series is shorter). Empty series and single-value series (where
    sample stdev is undefined) both yield stdev=0.0."""
    baseline_values = weekly_counts[:n_baseline_weeks]

    if not baseline_values:
        return BaselineStats(mean=0.0, stdev=0.0)

    mean = statistics.mean(baseline_values)
    stdev = statistics.stdev(baseline_values) if len(baseline_values) >= 2 else 0.0
    return BaselineStats(mean=mean, stdev=stdev)


def baseline_threshold(
    stats: BaselineStats,
    z: float = DETECTION_Z_SCORE,
    min_absolute_floor: float = DETECTION_MIN_ABSOLUTE_FLOOR,
) -> float:
    """mean + z*stdev, floored at min_absolute_floor so a near-zero-variance
    baseline can't make a single article count as a crossing."""
    return max(stats.mean + z * stats.stdev, min_absolute_floor)
