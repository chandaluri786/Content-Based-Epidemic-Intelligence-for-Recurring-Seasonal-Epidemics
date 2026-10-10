"""
Step 2 of pool preparation: tie each pooled article to the country-season
windows its scan date falls in, and pick the one country it is sampled
under.

- country_seasons: every window, any country, containing the date.
- sampling_country: among those windows' countries, the one the article's
  GDELT locations mention most often (ties broken by TARGET_COUNTRIES
  order). Only used for stratified sampling -- labelers record where the
  cases actually are separately.
- sampling_season: that country's season id -- the unit the calibration /
  held-out split is drawn over.

Articles in no window, or mentioning none of the countries whose windows
contain their date, get no sampling_country and stay out of the sample.

Same-country overlap is rejected outright: it is exactly what let one
article belong to two seasons of the same country, i.e. to both dev and
test.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from models import CountrySeasonWindow
from pipeline.windows import iter_days, season_id


@dataclass(frozen=True)
class SeasonAssignment:
    gkg_record_id: str
    datetime: str
    country_seasons: tuple[str, ...]
    sampling_country: str | None
    sampling_season: str | None


DayIndex = dict[date, dict[str, str]]   # day -> {country: season_id}


def build_day_index(windows: list[CountrySeasonWindow]) -> DayIndex:
    index: DayIndex = {}
    for window in windows:
        for day in iter_days(window):
            active = index.setdefault(day, {})
            if window.country_iso3 in active:
                raise ValueError(
                    f"{window.country_iso3} has two seasons on {day}: {active[window.country_iso3]} and "
                    f"{season_id(window)} -- same-country windows must not overlap"
                )
            active[window.country_iso3] = season_id(window)
    return index


def assign(record: dict, index: DayIndex, target_countries: dict[str, str]) -> SeasonAssignment:
    active = index.get(date.fromisoformat(record["datetime"][:10]), {})
    mentions = Counter(loc.get("country_fips") for loc in record.get("locations", []))
    cohort_order = list(target_countries)

    candidates = [(mentions[target_countries[c]], -cohort_order.index(c), c) for c in active]
    best = max(candidates, default=None)
    sampling_country = best[2] if best and best[0] > 0 else None

    return SeasonAssignment(
        gkg_record_id=record["gkg_record_id"],
        datetime=record["datetime"],
        country_seasons=tuple(sorted(active.values())),
        sampling_country=sampling_country,
        sampling_season=active[sampling_country] if sampling_country else None,
    )


def iter_assignments(pool_path: Path, windows: list[CountrySeasonWindow],
                     target_countries: dict[str, str]) -> Iterator[SeasonAssignment]:
    index = build_day_index(windows)
    with pool_path.open(encoding="utf-8") as f:
        for line in f:
            yield assign(json.loads(line), index, target_countries)


def write_assignments(pool_path: Path, windows: list[CountrySeasonWindow],
                      target_countries: dict[str, str], out_path: Path) -> dict:
    """Writes one JSON line per pooled article; returns summary counts."""
    per_season: Counter[str] = Counter()
    outside_windows = no_active_country = total = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out:
        for a in iter_assignments(pool_path, windows, target_countries):
            total += 1
            if not a.country_seasons:
                outside_windows += 1
            elif a.sampling_season is None:
                no_active_country += 1
            else:
                per_season[a.sampling_season] += 1
            out.write(json.dumps(asdict(a)) + "\n")
    return {
        "articles": total,
        "assigned": sum(per_season.values()),
        "outside_all_windows": outside_windows,
        "in_window_but_no_active_country_mentioned": no_active_country,
        "per_sampling_season": dict(sorted(per_season.items())),
    }
