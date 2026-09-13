"""Per-country-season GDELT ingestion windows, and the calendar-date union
across the whole cohort used to deduplicate downloads (Step 2).

A country-season whose window overlaps another's in absolute calendar time
(e.g. USA/UK/Japan sharing Northern Hemisphere winter timing in the same
year) should have that shared day downloaded once, not once per country-season
-- compute_calendar_date_union and build_date_to_countries_index exist so the
downloader can drive itself off unique days rather than per-window loops.
"""

from datetime import date, timedelta

from pipeline.common.epiweek import shift_weeks
from pipeline.config import BASELINE_WEEKS, GDELT_WEEKS_AFTER_ONSET, GDELT_WEEKS_BEFORE_ONSET
from pipeline.ground_truth.ground_truth_builder import CountrySeasonOnset
from pipeline.join.epiweek_join import CountrySeasonWindow


def build_window_for_country_season(
    country_iso3: str,
    season_year: int,
    onset_date: date,
    weeks_before: int = GDELT_WEEKS_BEFORE_ONSET,
    weeks_after: int = GDELT_WEEKS_AFTER_ONSET,
    baseline_weeks: int = BASELINE_WEEKS,
) -> CountrySeasonWindow:
    return CountrySeasonWindow(
        country_iso3=country_iso3,
        season_year=season_year,
        window_start_date=shift_weeks(onset_date, -weeks_before),
        window_end_date=shift_weeks(onset_date, weeks_after),
        onset_date=onset_date,
        baseline_weeks=baseline_weeks,
    )


def build_windows_from_ground_truth(rows: list[CountrySeasonOnset]) -> list[CountrySeasonWindow]:
    """One window per ground-truth row that is both in the GDELT cohort and
    has a defined onset date. Rows failing either condition (e.g. Brazil/
    Indonesia, or a no-onset-found year) are silently skipped -- they simply
    produce no ingestion window, which is the intended behavior."""
    return [
        build_window_for_country_season(row.country_iso3, row.year, row.onset_date)
        for row in rows
        if row.included_in_gdelt_cohort and row.onset_date is not None
    ]


def _iter_calendar_days(window: CountrySeasonWindow):
    current = window.window_start_date
    while current <= window.window_end_date:
        yield current
        current += timedelta(days=1)


def compute_calendar_date_union(windows: list[CountrySeasonWindow]) -> set[date]:
    union: set[date] = set()
    for window in windows:
        union.update(_iter_calendar_days(window))
    return union


def build_date_to_countries_index(windows: list[CountrySeasonWindow]) -> dict[date, list[str]]:
    index: dict[date, set[str]] = {}
    for window in windows:
        for day in _iter_calendar_days(window):
            index.setdefault(day, set()).add(window.country_iso3)
    return {day: sorted(countries) for day, countries in index.items()}
