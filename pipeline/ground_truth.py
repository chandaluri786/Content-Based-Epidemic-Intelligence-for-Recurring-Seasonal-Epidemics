"""
Stage 1: Ground truth onset dates from WHO FluNet.

For each country, pulls weekly influenza surveillance data and finds, per
season frame, the first rising edge into sustained activity: a run of
>=ONSET_SUSTAIN_WEEKS consecutive weeks at >=ONSET_POSITIVITY_THRESHOLD_PCT
test positivity, immediately preceded by >=ONSET_MIN_WEEKS_BELOW weeks
below it. That week is the date the rest of the pipeline's ingestion
windows are built around. The threshold can be overridden per country
(config.ONSET_THRESHOLD_PCT_BY_COUNTRY) for countries whose baseline sits
above the default.

Why a rising edge, and why season frames rather than calendar years: the
earlier version grouped weeks by ISO_YEAR and took the first above-threshold
run in each, so any season still active on January 1 got a fake onset in
ISO week 1 (19 of 45 onsets in the 2015-2024 runs), and one northern season
could produce two overlapping windows (USA "2023" and "2024" were both the
2023-24 season). Frames come from config.SEASON_START_MONTH -- July for the
USA's northern season, March for AUS, calendar year elsewhere.

FluNet reports one row per origin source (SENTINEL / NONSENTINEL /
NOTDEFINED) per week; rows are pooled into one positivity value per week
before any onset logic runs.

Source: WHO FluNet public API, no auth required, confirmed live.
https://xmart-api-public.who.int/FLUMART/VIW_FNT
Schema confirmed by a direct sample call before writing this (COUNTRY_CODE
is ISO3, e.g. "USA"; dates are in ISO_WEEKSTARTDATE as YYYY-MM-DD strings).
The API ignores OData server-driven paging (it never returns
@odata.nextLink), so results are paged explicitly with $skip.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from config import (
    DEFAULT_SEASON_START_MONTH,
    FLUNET_API_URL,
    ONSET_MIN_WEEKS_BELOW,
    ONSET_POSITIVITY_THRESHOLD_PCT,
    ONSET_SUSTAIN_WEEKS,
    ONSET_THRESHOLD_PCT_BY_COUNTRY,
    SEASON_START_MONTH,
)

logger = logging.getLogger(__name__)

FLUNET_PAGE_SIZE = 1000
FLUNET_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class CountrySeasonOnset:
    country_iso3: str
    season_year: int
    onset_date: date


@dataclass(frozen=True)
class WeeklyPositivity:
    week_start: date
    positivity_pct: float


def _get_page(country_iso3: str, start_year: int, end_year: int, skip: int, page_size: int) -> list[dict]:
    filt = f"COUNTRY_CODE eq '{country_iso3}' and ISO_YEAR ge {start_year} and ISO_YEAR le {end_year}"
    # Secondary sort key keeps the row order stable across pages -- several
    # rows share each ISO_WEEKSTARTDATE (one per origin source).
    url = (
        f"{FLUNET_API_URL}?$filter={urllib.parse.quote(filt)}"
        f"&$orderby=ISO_WEEKSTARTDATE,ORIGIN_SOURCE&$top={page_size}&$skip={skip}&$format=json"
    )
    with urllib.request.urlopen(url, timeout=FLUNET_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read())["value"]


def _fetch_weekly_rows(country_iso3: str, start_year: int, end_year: int,
                       page_size: int = FLUNET_PAGE_SIZE) -> list[dict]:
    """Pulls every weekly FluNet row for one country within
    [start_year, end_year] inclusive, paging with $skip until a short page."""
    rows: list[dict] = []
    skip = 0
    while True:
        page = _get_page(country_iso3, start_year, end_year, skip, page_size)
        rows.extend(page)
        if len(page) < page_size:
            return rows
        skip += page_size


def weekly_positivity(rows: list[dict]) -> list[WeeklyPositivity]:
    """One pooled positivity value per week, sorted by week. Weeks with no
    specimens processed can't yield a rate and are left out, as are weeks
    reporting more positives than specimens (a data error -- FluNet has at
    least one, BRA at 125%)."""
    processed: dict[str, int] = defaultdict(int)
    positive: dict[str, int] = defaultdict(int)
    for row in rows:
        week = row["ISO_WEEKSTARTDATE"]
        processed[week] += row.get("SPEC_PROCESSED_NB") or 0
        positive[week] += row.get("INF_ALL") or 0

    series: list[WeeklyPositivity] = []
    for week in sorted(processed):
        if processed[week] <= 0:
            continue
        if positive[week] > processed[week]:
            logger.warning("Skipping FluNet week %s: %d positives > %d specimens", week, positive[week], processed[week])
            continue
        series.append(WeeklyPositivity(week_start=date.fromisoformat(week),
                                       positivity_pct=100 * positive[week] / processed[week]))
    return series


def season_year_of(day: date, frame_start_month: int) -> int:
    """The season a date belongs to, named by the year its frame starts."""
    return day.year if day.month >= frame_start_month else day.year - 1


def onset_threshold_for(country_iso3: str) -> float:
    return ONSET_THRESHOLD_PCT_BY_COUNTRY.get(country_iso3, ONSET_POSITIVITY_THRESHOLD_PCT)


def _is_contiguous(weeks: list[WeeklyPositivity]) -> bool:
    """No reporting gaps -- skipped weeks would otherwise let "4 weeks
    below" or the sustained run silently span months."""
    return all(b.week_start - a.week_start == timedelta(weeks=1) for a, b in zip(weeks, weeks[1:]))


def _is_rising_edge(series: list[WeeklyPositivity], i: int, threshold_pct: float) -> bool:
    """Week i starts a sustained run that follows enough below-threshold weeks,
    all consecutive calendar weeks. The lookback may reach into the previous frame."""
    if i < ONSET_MIN_WEEKS_BELOW or i + ONSET_SUSTAIN_WEEKS > len(series):
        return False
    before = series[i - ONSET_MIN_WEEKS_BELOW:i]
    run = series[i:i + ONSET_SUSTAIN_WEEKS]
    if not _is_contiguous(before + run):
        return False
    return (all(w.positivity_pct < threshold_pct for w in before)
            and all(w.positivity_pct >= threshold_pct for w in run))


def find_onsets(series: list[WeeklyPositivity], country_iso3: str, frame_start_month: int,
                start_year: int, end_year: int) -> list[CountrySeasonOnset]:
    """First rising edge in each season frame whose season_year is in
    [start_year, end_year]. Frames without one get no onset -- by design,
    the pipeline produces no window for that season rather than guessing."""
    threshold_pct = onset_threshold_for(country_iso3)
    onsets: dict[int, CountrySeasonOnset] = {}
    for i, week in enumerate(series):
        season = season_year_of(week.week_start, frame_start_month)
        if not start_year <= season <= end_year or season in onsets:
            continue
        if _is_rising_edge(series, i, threshold_pct):
            onsets[season] = CountrySeasonOnset(country_iso3=country_iso3, season_year=season,
                                                onset_date=week.week_start)
    return [onsets[season] for season in sorted(onsets)]


def frame_start_month_for(country_iso3: str) -> int:
    return SEASON_START_MONTH.get(country_iso3, DEFAULT_SEASON_START_MONTH)


def compute_season_onsets(country_iso3: str, start_year: int, end_year: int) -> list[CountrySeasonOnset]:
    """One onset per season year in [start_year, end_year] inclusive that
    has a rising edge. Fetches a year either side: the year before for the
    below-threshold lookback, the year after for frames that span the new
    year."""
    rows = _fetch_weekly_rows(country_iso3, start_year - 1, end_year + 1)
    return find_onsets(weekly_positivity(rows), country_iso3, frame_start_month_for(country_iso3),
                       start_year, end_year)
