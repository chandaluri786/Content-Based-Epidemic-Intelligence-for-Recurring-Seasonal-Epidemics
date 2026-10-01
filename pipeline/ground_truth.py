"""
Stage 1: Ground truth onset dates from WHO FluNet.

For each country, pulls weekly influenza surveillance data and determines
the first sustained (>=ONSET_SUSTAIN_WEEKS consecutive weeks) period of
>=ONSET_POSITIVITY_THRESHOLD_PCT test positivity per season -- the date the
rest of the pipeline's ingestion windows are built around.

Source: WHO FluNet public API, no auth required, confirmed live.
https://xmart-api-public.who.int/FLUMART/VIW_FNT
Schema confirmed by a direct sample call before writing this (COUNTRY_CODE
is ISO3, e.g. "USA"; dates are in ISO_WEEKSTARTDATE as YYYY-MM-DD strings).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from config import FLUNET_API_URL, ONSET_POSITIVITY_THRESHOLD_PCT, ONSET_SUSTAIN_WEEKS


@dataclass(frozen=True)
class CountrySeasonOnset:
    country_iso3: str
    season_year: int
    onset_date: date


def _fetch_weekly_rows(country_iso3: str, start_year: int) -> list[dict]:
    """Pulls every weekly FluNet row for one country from start_year
    onward, following OData pagination ('@odata.nextLink') until exhausted."""
    filt = f"COUNTRY_CODE eq '{country_iso3}' and ISO_YEAR ge {start_year}"
    url = (
        f"{FLUNET_API_URL}?$filter={urllib.parse.quote(filt)}"
        f"&$orderby=ISO_WEEKSTARTDATE&$top=1000&$format=json"
    )
    rows: list[dict] = []
    while url:
        with urllib.request.urlopen(url, timeout=30) as resp:
            payload = json.loads(resp.read())
        rows.extend(payload["value"])
        url = payload.get("@odata.nextLink")
    return rows


def compute_season_onsets(country_iso3: str, start_year: int) -> list[CountrySeasonOnset]:
    """One onset per season that has a defined onset. Seasons without a
    sustained positivity period above threshold are silently skipped --
    by design, the pipeline simply produces no ingestion window for that
    season rather than guessing one."""
    rows = _fetch_weekly_rows(country_iso3, start_year)

    by_year: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("SPEC_PROCESSED_NB"):  # weeks with no denominator can't yield a positivity rate
            by_year[row["ISO_YEAR"]].append(row)

    onsets: list[CountrySeasonOnset] = []
    for year, weeks in sorted(by_year.items()):
        weeks.sort(key=lambda r: r["ISO_WEEKSTARTDATE"])
        positivity = [100 * (w["INF_ALL"] or 0) / w["SPEC_PROCESSED_NB"] for w in weeks]

        for start_idx in range(len(weeks) - ONSET_SUSTAIN_WEEKS + 1):
            window = positivity[start_idx:start_idx + ONSET_SUSTAIN_WEEKS]
            if all(p >= ONSET_POSITIVITY_THRESHOLD_PCT for p in window):
                onsets.append(CountrySeasonOnset(
                    country_iso3=country_iso3,
                    season_year=year,
                    onset_date=date.fromisoformat(weeks[start_idx]["ISO_WEEKSTARTDATE"]),
                ))
                break  # only the first sustained onset of each season
    return onsets
