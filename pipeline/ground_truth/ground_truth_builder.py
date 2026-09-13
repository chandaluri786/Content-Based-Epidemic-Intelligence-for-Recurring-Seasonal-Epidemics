"""Per-country method dispatch -> unified country-season ground-truth table.

Dispatch is explicit and hardcoded (config.COUNTRIES[iso3].onset_method plus a
UK_ISO3 special case for source selection), not an implicit try/fallback, so
which source and rule produced each row is deterministic and auditable.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pipeline.config import COUNTRIES, UK_ISO3, YEARS, CountryDef, OnsetMethod
from pipeline.ground_truth.flunet_client import fetch_country_year_records
from pipeline.ground_truth.onset_detection import (
    OnsetResult,
    WeeklyValue,
    find_onset_flat_rule,
    find_onset_peak_proxy,
)
from pipeline.ground_truth.ukhsa_client import fetch_all_weekly_records

DataQualityFlag = Literal["ok", "no_data", "no_onset_found", "proxy_lower_rigor"]


@dataclass(frozen=True)
class CountrySeasonOnset:
    country_iso3: str
    country_display: str
    year: int
    source: Literal["FluNet", "UKHSA"]
    onset_method: OnsetMethod
    onset_iso_week: int | None
    onset_date: date | None
    value_at_onset: float | None
    data_quality_flag: DataQualityFlag
    included_in_gdelt_cohort: bool


def _flunet_row_to_positivity(row: dict[str, Any]) -> WeeklyValue:
    iso_year = int(row["ISO_YEAR"])
    iso_week = int(row["ISO_WEEK"])
    try:
        processed = float(row.get("SPEC_PROCESSED_NB") or 0)
        inf_all = float(row.get("INF_ALL") or 0)
        value = (inf_all / processed * 100) if processed > 0 else None
    except (ValueError, TypeError):
        value = None
    return WeeklyValue(iso_year=iso_year, iso_week=iso_week, value=value)


def _flunet_row_to_raw_count(row: dict[str, Any]) -> WeeklyValue:
    iso_year = int(row["ISO_YEAR"])
    iso_week = int(row["ISO_WEEK"])
    try:
        value = float(row["INF_ALL"]) if row.get("INF_ALL") else None
    except (ValueError, TypeError):
        value = None
    return WeeklyValue(iso_year=iso_year, iso_week=iso_week, value=value)


def _ukhsa_row_to_positivity(row: dict[str, Any]) -> WeeklyValue:
    return WeeklyValue(
        iso_year=int(row["year"]),
        iso_week=int(row["epiweek"]),
        value=float(row["metric_value"]) if row.get("metric_value") is not None else None,
    )


def _quality_flag_for(onset: OnsetResult | None, had_data: bool, is_proxy: bool) -> DataQualityFlag:
    if not had_data:
        return "no_data"
    if onset is None:
        return "no_onset_found"
    return "proxy_lower_rigor" if is_proxy else "ok"


def _build_row(
    country_iso3: str,
    country_def: CountryDef,
    year: int,
    source: Literal["FluNet", "UKHSA"],
    series: list[WeeklyValue],
    had_data: bool,
) -> CountrySeasonOnset:
    is_proxy = country_def.onset_method == "peak_count_proxy"
    onset = find_onset_peak_proxy(series) if is_proxy else find_onset_flat_rule(series)

    return CountrySeasonOnset(
        country_iso3=country_iso3,
        country_display=country_def.name,
        year=year,
        source=source,
        onset_method=country_def.onset_method,
        onset_iso_week=onset.onset_iso_week if onset else None,
        onset_date=onset.onset_date if onset else None,
        value_at_onset=onset.value_at_onset if onset else None,
        data_quality_flag=_quality_flag_for(onset, had_data, is_proxy),
        included_in_gdelt_cohort=country_def.included_in_gdelt_cohort,
    )


def build_ground_truth_table(
    countries: dict[str, CountryDef] = COUNTRIES,
    years: list[int] = YEARS,
    flunet_fetch: Callable[..., list[dict[str, Any]]] = fetch_country_year_records,
    ukhsa_fetch: Callable[..., list[dict[str, Any]]] = fetch_all_weekly_records,
) -> list[CountrySeasonOnset]:
    """Build one row per (country, year) using each country's configured
    onset method and source. UKHSA is fetched once (its endpoint returns the
    full multi-year series in one call) and grouped by year, rather than
    re-fetched per year like FluNet's per-country-year API."""
    rows: list[CountrySeasonOnset] = []

    ukhsa_series_by_year: dict[int, list[WeeklyValue]] | None = None
    if UK_ISO3 in countries:
        ukhsa_records = ukhsa_fetch()
        ukhsa_series_by_year = {}
        for record in ukhsa_records:
            weekly = _ukhsa_row_to_positivity(record)
            ukhsa_series_by_year.setdefault(weekly.iso_year, []).append(weekly)

    for iso3, country_def in countries.items():
        for year in years:
            if iso3 == UK_ISO3:
                series = ukhsa_series_by_year.get(year, []) if ukhsa_series_by_year else []
                rows.append(
                    _build_row(iso3, country_def, year, "UKHSA", series, had_data=bool(series))
                )
                continue

            raw_rows = flunet_fetch(iso3, year)
            converter = (
                _flunet_row_to_raw_count
                if country_def.onset_method == "peak_count_proxy"
                else _flunet_row_to_positivity
            )
            series = [converter(r) for r in raw_rows]
            rows.append(
                _build_row(iso3, country_def, year, "FluNet", series, had_data=bool(raw_rows))
            )

    return rows
