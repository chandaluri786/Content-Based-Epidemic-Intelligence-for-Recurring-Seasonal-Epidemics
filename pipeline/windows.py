"""
Stage 2: build each country-season's ingestion window, and the union of
every unique calendar day across the whole cohort.

A day shared by two countries' windows (e.g. USA and AUS both needing
2023-12-04) should only be downloaded once -- unique_days_across_cohort()
exists so Stage 3 can drive itself off unique days rather than looping
per-country-season and re-downloading shared days.
"""

from __future__ import annotations

from datetime import date, timedelta

from config import WEEKS_AFTER_ONSET, WEEKS_BEFORE_ONSET
from models import CountrySeasonWindow
from pipeline.ground_truth import CountrySeasonOnset


def build_window(onset: CountrySeasonOnset) -> CountrySeasonWindow:
    return CountrySeasonWindow(
        country_iso3=onset.country_iso3,
        season_year=onset.season_year,
        onset_date=onset.onset_date,
        window_start=onset.onset_date - timedelta(weeks=WEEKS_BEFORE_ONSET),
        window_end=onset.onset_date + timedelta(weeks=WEEKS_AFTER_ONSET),
    )


def iter_days(window: CountrySeasonWindow):
    current = window.window_start
    while current <= window.window_end:
        yield current
        current += timedelta(days=1)


def unique_days_across_cohort(cohort_windows: list[CountrySeasonWindow]) -> set[date]:
    """Every calendar day needed by at least one window, deduplicated.
    This is the only thing Stage 3 needs from this module -- which days to
    download. (An earlier version also exposed a day-to-active-countries
    index for country bucketing; that stage was removed -- see README
    "Stage 6" -- so that index was removed too rather than left unused.)"""
    days: set[date] = set()
    for window in cohort_windows:
        days.update(iter_days(window))
    return days
