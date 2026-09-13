"""Lead-time distribution summary across the cohort (Step 8).

This is the headline result of the project: does the content signal lead the
frequency baseline, and by how much, across the evaluated country-seasons.
"""

import statistics
from dataclasses import dataclass

from pipeline.detection.lead_time import LeadTimeRow


@dataclass(frozen=True)
class LeadTimeSummary:
    n_total: int
    n_excluded: int
    n_content_detected: int
    n_frequency_detected: int
    content_lead_mean_days: float | None
    content_lead_median_days: float | None
    content_lead_stdev_days: float | None
    frequency_lead_mean_days: float | None
    frequency_lead_median_days: float | None
    frequency_lead_stdev_days: float | None
    content_win_rate: float | None


def _stats(values: list[int]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    mean = statistics.mean(values)
    median = statistics.median(values)
    stdev = statistics.stdev(values) if len(values) >= 2 else 0.0
    return mean, median, stdev


def summarize_lead_times(rows: list[LeadTimeRow]) -> LeadTimeSummary:
    content_leads = [r.content_lead_time_days for r in rows if r.content_lead_time_days is not None]
    frequency_leads = [
        r.frequency_lead_time_days for r in rows if r.frequency_lead_time_days is not None
    ]
    comparable = [r.content_beats_frequency for r in rows if r.content_beats_frequency is not None]

    content_mean, content_median, content_stdev = _stats(content_leads)
    frequency_mean, frequency_median, frequency_stdev = _stats(frequency_leads)
    win_rate = (sum(comparable) / len(comparable)) if comparable else None

    return LeadTimeSummary(
        n_total=len(rows),
        n_excluded=sum(1 for r in rows if r.excluded_reason is not None),
        n_content_detected=len(content_leads),
        n_frequency_detected=len(frequency_leads),
        content_lead_mean_days=content_mean,
        content_lead_median_days=content_median,
        content_lead_stdev_days=content_stdev,
        frequency_lead_mean_days=frequency_mean,
        frequency_lead_median_days=frequency_median,
        frequency_lead_stdev_days=frequency_stdev,
        content_win_rate=win_rate,
    )
