"""Content-based and frequency-baseline detection rules (Step 6).

Both rules are the same statistical test (baseline mean/stdev from the first
BASELINE_WEEKS, then a sustained crossing of mean + z*stdev, floored) applied
to different columns of the same joined weekly rows -- content_relevant_count
(LLM-filtered) for the content signal, frequency_raw_count (no LLM) for the
baseline -- so the two methods are directly comparable on identical data.
"""

from collections.abc import Callable
from datetime import date

from pipeline.common.sustained_crossing import find_sustained_crossing
from pipeline.config import (
    BASELINE_WEEKS,
    DETECTION_MIN_ABSOLUTE_FLOOR,
    DETECTION_SUSTAIN_WEEKS,
    DETECTION_Z_SCORE,
)
from pipeline.detection.baseline_stats import baseline_threshold, compute_baseline
from pipeline.join.epiweek_join import CountryWeekJoined

CountGetter = Callable[[CountryWeekJoined], int]


def compute_first_crossing_date(
    weeks: list[CountryWeekJoined],
    count_getter: CountGetter,
    baseline_weeks: int = BASELINE_WEEKS,
    z: float = DETECTION_Z_SCORE,
    min_absolute_floor: float = DETECTION_MIN_ABSOLUTE_FLOOR,
    sustain_weeks: int = DETECTION_SUSTAIN_WEEKS,
) -> date | None:
    """First date (post-baseline) where count_getter's weekly value is
    sustained >= the baseline-derived threshold for sustain_weeks in a row."""
    if not weeks:
        return None

    counts = [count_getter(w) for w in weeks]
    stats = compute_baseline(counts, n_baseline_weeks=baseline_weeks)
    threshold = baseline_threshold(stats, z=z, min_absolute_floor=min_absolute_floor)

    index = find_sustained_crossing(
        counts, threshold=threshold, sustain_periods=sustain_weeks, start_index=baseline_weeks
    )
    if index is None:
        return None

    return weeks[index].week_start_date


def compute_content_signal_date(weeks: list[CountryWeekJoined]) -> date | None:
    return compute_first_crossing_date(weeks, lambda w: w.content_relevant_count)


def compute_frequency_signal_date(weeks: list[CountryWeekJoined]) -> date | None:
    return compute_first_crossing_date(weeks, lambda w: w.frequency_raw_count)
