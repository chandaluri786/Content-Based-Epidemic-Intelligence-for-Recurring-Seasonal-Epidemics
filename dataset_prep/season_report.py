"""
Step 2 of pool preparation: the full-cohort season windows, plus a
per-season diagnostic table for reviewing the onset rule before any
gap-fill download.

Each country's FluNet series is fetched once and reused for both the
onsets (via pipeline.ground_truth.find_onsets, the same code Stage 1 runs)
and the diagnostics, so the table always explains exactly the windows that
were saved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from models import CountrySeasonWindow
from pipeline import windows
from pipeline.ground_truth import (
    CountrySeasonOnset,
    WeeklyPositivity,
    _fetch_weekly_rows,
    find_onsets,
    frame_start_month_for,
    onset_threshold_for,
    season_year_of,
    weekly_positivity,
)


@dataclass(frozen=True)
class SeasonDiagnostic:
    season_id: str
    country: str
    season_year: int
    onset_date: date | None
    onset_iso_week: int | None
    weeks_reported: int
    threshold_pct: float
    weeks_at_or_above_threshold: int
    peak_positivity_pct: float | None
    status: str


def _status(onset: CountrySeasonOnset | None, frame_weeks: list[WeeklyPositivity],
            kept_ids: set[str], sid: str, threshold_pct: float) -> str:
    if onset is not None:
        return "window" if sid in kept_ids else "dropped (pre-GDELT or overlap)"
    if not frame_weeks:
        return "no FluNet data"
    if all(w.positivity_pct < threshold_pct for w in frame_weeks):
        return "never reaches threshold"
    return "no rising edge"


def diagnose_country(country: str, series: list[WeeklyPositivity], onsets: list[CountrySeasonOnset],
                     kept_ids: set[str], start_year: int, end_year: int) -> list[SeasonDiagnostic]:
    month = frame_start_month_for(country)
    threshold_pct = onset_threshold_for(country)
    onset_by_season = {o.season_year: o for o in onsets}
    rows: list[SeasonDiagnostic] = []
    for season in range(start_year, end_year + 1):
        frame_weeks = [w for w in series if season_year_of(w.week_start, month) == season]
        onset = onset_by_season.get(season)
        sid = f"{country}-{season}"
        rows.append(SeasonDiagnostic(
            season_id=sid,
            country=country,
            season_year=season,
            onset_date=onset.onset_date if onset else None,
            onset_iso_week=onset.onset_date.isocalendar().week if onset else None,
            weeks_reported=len(frame_weeks),
            threshold_pct=threshold_pct,
            weeks_at_or_above_threshold=sum(w.positivity_pct >= threshold_pct for w in frame_weeks),
            peak_positivity_pct=round(max(w.positivity_pct for w in frame_weeks), 1) if frame_weeks else None,
            status=_status(onset, frame_weeks, kept_ids, sid, threshold_pct),
        ))
    return rows


def build_cohort(countries: list[str], start_year: int, end_year: int
                 ) -> tuple[list[CountrySeasonWindow], list[SeasonDiagnostic]]:
    """Windows for the whole cohort, and one diagnostic row per country-season."""
    series_by_country: dict[str, list[WeeklyPositivity]] = {}
    all_onsets: list[CountrySeasonOnset] = []
    for country in countries:
        series = weekly_positivity(_fetch_weekly_rows(country, start_year - 1, end_year + 1))
        series_by_country[country] = series
        all_onsets.extend(find_onsets(series, country, frame_start_month_for(country), start_year, end_year))

    cohort = windows.usable_windows(all_onsets)
    kept_ids = {windows.season_id(w) for w in cohort}
    diagnostics = [
        row
        for country in countries
        for row in diagnose_country(country, series_by_country[country],
                                    [o for o in all_onsets if o.country_iso3 == country],
                                    kept_ids, start_year, end_year)
    ]
    return cohort, diagnostics


def format_table(diagnostics: list[SeasonDiagnostic]) -> str:
    header = f"{'season':10} {'onset':10} {'isowk':>5} {'weeks':>5} {'thr%':>5} {'>=thr':>5} {'peak%':>6}  status"
    lines = [header, "-" * len(header)]
    for d in diagnostics:
        lines.append(
            f"{d.season_id:10} {d.onset_date.isoformat() if d.onset_date else '-':10} "
            f"{d.onset_iso_week if d.onset_iso_week else '-':>5} {d.weeks_reported:>5} {d.threshold_pct:>5g} "
            f"{d.weeks_at_or_above_threshold:>5} "
            f"{d.peak_positivity_pct if d.peak_positivity_pct is not None else '-':>6}  {d.status}"
        )
    return "\n".join(lines)
