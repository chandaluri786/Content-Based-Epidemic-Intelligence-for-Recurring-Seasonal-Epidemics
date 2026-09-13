"""Cross-document linking (Step 5): deterministic join by country x epi-week.

The dense join (every ISO week in every window present, zero-filled) is the
single most likely place for a silent bug: omitting a true zero-week skews
detection/baseline_stats.py's baseline upward and can suppress a real
crossing in detection/crossing_rule.py.
"""

from dataclasses import dataclass
from datetime import date

from pipeline.common.epiweek import iso_week_of, iter_weekly_dates

WeekKey = tuple[str, int, int]  # (country_iso3, iso_year, iso_week)


@dataclass(frozen=True)
class ArticleWeekRecord:
    country_iso3: str
    iso_year: int
    iso_week: int
    is_relevant: bool


@dataclass(frozen=True)
class CountrySeasonWindow:
    country_iso3: str
    season_year: int
    window_start_date: date
    window_end_date: date
    onset_date: date
    baseline_weeks: int


@dataclass(frozen=True)
class CountryWeekJoined:
    country_iso3: str
    season_year: int
    iso_year: int
    iso_week: int
    week_start_date: date
    content_relevant_count: int
    frequency_raw_count: int
    is_baseline_week: bool
    days_from_onset: int


def build_week_counts(records: list[ArticleWeekRecord], relevant_only: bool) -> dict[WeekKey, int]:
    """Count articles per (country, iso_year, iso_week). When relevant_only is
    True, only records with is_relevant=True are counted (the content signal);
    when False, every record is counted (the no-LLM frequency baseline)."""
    counts: dict[WeekKey, int] = {}
    for record in records:
        if relevant_only and not record.is_relevant:
            continue
        key = (record.country_iso3, record.iso_year, record.iso_week)
        counts[key] = counts.get(key, 0) + 1
    return counts


def join_to_ground_truth(
    relevant_counts: dict[WeekKey, int],
    raw_counts: dict[WeekKey, int],
    windows: list[CountrySeasonWindow],
) -> list[CountryWeekJoined]:
    """Produce one dense row per week in each country-season window, zero-
    filled where no articles were found."""
    rows: list[CountryWeekJoined] = []

    for window in windows:
        for week_index, week_start in enumerate(
            iter_weekly_dates(window.window_start_date, window.window_end_date)
        ):
            iso_year, iso_week = iso_week_of(week_start)
            key = (window.country_iso3, iso_year, iso_week)
            rows.append(
                CountryWeekJoined(
                    country_iso3=window.country_iso3,
                    season_year=window.season_year,
                    iso_year=iso_year,
                    iso_week=iso_week,
                    week_start_date=week_start,
                    content_relevant_count=relevant_counts.get(key, 0),
                    frequency_raw_count=raw_counts.get(key, 0),
                    is_baseline_week=week_index < window.baseline_weeks,
                    days_from_onset=(week_start - window.onset_date).days,
                )
            )

    return rows
