"""Lead-time computation and the content-vs-frequency comparison (Step 6).

This comparison is the entire point of the project: for each country-season,
does the LLM-filtered content signal cross its detection threshold earlier
than the no-LLM frequency-count baseline, relative to the official
FluNet/UKHSA onset date?
"""

from dataclasses import dataclass
from datetime import date

from pipeline.config import MIN_TOTAL_ARTICLES_FOR_DETECTION
from pipeline.detection.crossing_rule import (
    compute_content_signal_date,
    compute_frequency_signal_date,
)
from pipeline.join.epiweek_join import CountryWeekJoined


@dataclass(frozen=True)
class LeadTimeRow:
    country_iso3: str
    season_year: int
    official_onset_date: date
    official_onset_method: str
    content_signal_date: date | None
    content_lead_time_days: int | None
    frequency_signal_date: date | None
    frequency_lead_time_days: int | None
    content_beats_frequency: bool | None
    excluded_reason: str | None


def compute_lead_time_days(signal_date: date | None, official_onset_date: date) -> int | None:
    """signal_date - official_onset_date, in days. Negative means the system
    detected the signal before the official onset (a lead)."""
    if signal_date is None:
        return None
    return (signal_date - official_onset_date).days


def _content_beats_frequency(
    content_lead_days: int | None, frequency_lead_days: int | None
) -> bool | None:
    if content_lead_days is None and frequency_lead_days is None:
        return None
    if content_lead_days is None:
        return False
    if frequency_lead_days is None:
        return True
    return content_lead_days < frequency_lead_days


def build_lead_time_row(
    country_iso3: str,
    season_year: int,
    official_onset_date: date,
    official_onset_method: str,
    weeks: list[CountryWeekJoined],
    min_total_articles: int = MIN_TOTAL_ARTICLES_FOR_DETECTION,
) -> LeadTimeRow:
    total_articles = sum(w.frequency_raw_count for w in weeks) + sum(
        w.content_relevant_count for w in weeks
    )

    if total_articles < min_total_articles:
        return LeadTimeRow(
            country_iso3=country_iso3,
            season_year=season_year,
            official_onset_date=official_onset_date,
            official_onset_method=official_onset_method,
            content_signal_date=None,
            content_lead_time_days=None,
            frequency_signal_date=None,
            frequency_lead_time_days=None,
            content_beats_frequency=None,
            excluded_reason="insufficient_data",
        )

    content_signal_date = compute_content_signal_date(weeks)
    frequency_signal_date = compute_frequency_signal_date(weeks)
    content_lead = compute_lead_time_days(content_signal_date, official_onset_date)
    frequency_lead = compute_lead_time_days(frequency_signal_date, official_onset_date)

    return LeadTimeRow(
        country_iso3=country_iso3,
        season_year=season_year,
        official_onset_date=official_onset_date,
        official_onset_method=official_onset_method,
        content_signal_date=content_signal_date,
        content_lead_time_days=content_lead,
        frequency_signal_date=frequency_signal_date,
        frequency_lead_time_days=frequency_lead,
        content_beats_frequency=_content_beats_frequency(content_lead, frequency_lead),
        excluded_reason=None,
    )
