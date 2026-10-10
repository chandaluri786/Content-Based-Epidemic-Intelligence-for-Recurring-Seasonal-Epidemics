"""
Stage 2: build each country-season's ingestion window, and the union of
every unique calendar day across the whole cohort.

A day shared by two countries' windows (e.g. USA and AUS both needing
2023-12-04) should only be downloaded once -- unique_days_across_cohort()
exists so Stage 3 can drive itself off unique days rather than looping
per-country-season and re-downloading shared days.

Overlap ACROSS countries is expected and fine. Overlap WITHIN one country
is not: two seasons of the same country sharing days means an article can
belong to both, which breaks the calibration/held-out season split used
for dev vs test labeling. drop_overlapping() enforces that invariant.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from config import GDELT_EARLIEST_AVAILABLE_DATE, WEEKS_AFTER_ONSET, WEEKS_BEFORE_ONSET
from models import CountrySeasonWindow
from pipeline.ground_truth import CountrySeasonOnset

logger = logging.getLogger(__name__)


def build_window(onset: CountrySeasonOnset) -> CountrySeasonWindow:
    return CountrySeasonWindow(
        country_iso3=onset.country_iso3,
        season_year=onset.season_year,
        onset_date=onset.onset_date,
        window_start=onset.onset_date - timedelta(weeks=WEEKS_BEFORE_ONSET),
        window_end=onset.onset_date + timedelta(weeks=WEEKS_AFTER_ONSET),
    )


def season_id(window: CountrySeasonWindow) -> str:
    return f"{window.country_iso3}-{window.season_year}"


def drop_before_gdelt(windows: list[CountrySeasonWindow], earliest: date) -> list[CountrySeasonWindow]:
    """Windows starting before GDELT's first file can't be ingested in full."""
    kept = [w for w in windows if w.window_start >= earliest]
    for w in windows:
        if w.window_start < earliest:
            logger.warning("Dropping %s: window starts %s, before GDELT data begins (%s)",
                           season_id(w), w.window_start, earliest)
    return kept


def drop_overlapping(windows: list[CountrySeasonWindow]) -> list[CountrySeasonWindow]:
    """Within each country, keeps windows in start order and drops any that
    shares a day with the last kept one. Returns a new list in the input's
    order; the input is not modified."""
    dropped: set[int] = set()
    last_end_by_country: dict[str, date] = {}
    for i in sorted(range(len(windows)), key=lambda i: (windows[i].country_iso3, windows[i].window_start)):
        window = windows[i]
        last_end = last_end_by_country.get(window.country_iso3)
        if last_end is not None and window.window_start <= last_end:
            logger.warning("Dropping %s (%s to %s): overlaps the previous %s window ending %s",
                           season_id(window), window.window_start, window.window_end,
                           window.country_iso3, last_end)
            dropped.add(i)
            continue
        last_end_by_country[window.country_iso3] = window.window_end
    return [w for i, w in enumerate(windows) if i not in dropped]


def usable_windows(onsets: list[CountrySeasonOnset]) -> list[CountrySeasonWindow]:
    """Stage 2 proper: one window per onset, minus windows GDELT can't
    cover and same-country overlaps."""
    built = [build_window(onset) for onset in onsets]
    return drop_overlapping(drop_before_gdelt(built, date.fromisoformat(GDELT_EARLIEST_AVAILABLE_DATE)))


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


def save_windows(windows: list[CountrySeasonWindow], path: Path) -> None:
    rows = [
        {
            "season_id": season_id(w),
            "country": w.country_iso3,
            "season_year": w.season_year,
            "onset_date": w.onset_date.isoformat(),
            "window_start": w.window_start.isoformat(),
            "window_end": w.window_end.isoformat(),
        }
        for w in windows
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2))


def load_windows(path: Path) -> list[CountrySeasonWindow]:
    return [
        CountrySeasonWindow(
            country_iso3=row["country"],
            season_year=row["season_year"],
            onset_date=date.fromisoformat(row["onset_date"]),
            window_start=date.fromisoformat(row["window_start"]),
            window_end=date.fromisoformat(row["window_end"]),
        )
        for row in json.loads(path.read_text())
    ]
