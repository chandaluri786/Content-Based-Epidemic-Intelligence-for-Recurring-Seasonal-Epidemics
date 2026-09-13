"""Step 2: GDELT raw-mirror ingestion for the flu cohort.

Reads data/ground_truth/country_seasons.csv (Step 1's output), builds one
ingestion window per included country-season with a defined onset, dedupes
the ingestion by calendar day across the whole selection, and writes matched
flu-candidate URLs to data/gdelt_matched/{iso3}.jsonl.

Usage:
    python -m pipeline.cli.run_step2_ingest [--countries USA,KEN] [--years 2023,2024] [--max-days N]
"""

import argparse
import csv
import json
import threading
import time
from datetime import date
from pathlib import Path

from pipeline.gdelt.manifest import IngestionManifest
from pipeline.gdelt.raw_downloader import run_ingestion_for_day
from pipeline.gdelt.window_builder import (
    build_date_to_countries_index,
    build_windows_from_ground_truth,
)
from pipeline.ground_truth.ground_truth_builder import CountrySeasonOnset

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth" / "country_seasons.csv"
MATCHED_DIR = DATA_DIR / "gdelt_matched"
MANIFEST_PATH = DATA_DIR / "gdelt_manifest" / "manifest.jsonl"


def load_ground_truth(path: Path) -> list[CountrySeasonOnset]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            onset_date = date.fromisoformat(r["onset_date"]) if r["onset_date"] else None
            rows.append(
                CountrySeasonOnset(
                    country_iso3=r["country_iso3"],
                    country_display=r["country_display"],
                    year=int(r["year"]),
                    source=r["source"],
                    onset_method=r["onset_method"],
                    onset_iso_week=int(r["onset_iso_week"]) if r["onset_iso_week"] else None,
                    onset_date=onset_date,
                    value_at_onset=float(r["value_at_onset"]) if r["value_at_onset"] else None,
                    data_quality_flag=r["data_quality_flag"],
                    included_in_gdelt_cohort=r["included_in_gdelt_cohort"] == "True",
                )
            )
    return rows


class ThreadSafeMatchWriter:
    """One JSONL file per country, each protected by its own lock -- safe to
    call from run_ingestion_for_day's concurrent workers."""

    def __init__(self, out_dir: Path) -> None:
        self._out_dir = out_dir
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, iso3: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(iso3, threading.Lock())

    def __call__(self, iso3: str, stamp: str, url: str) -> None:
        path = self._out_dir / f"{iso3}.jsonl"
        with self._lock_for(iso3), path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"stamp": stamp, "url": url}) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--countries", type=str, default=None, help="Comma-separated ISO3 filter")
    parser.add_argument("--years", type=str, default=None, help="Comma-separated year filter")
    parser.add_argument("--max-days", type=int, default=None, help="Process at most N unique days")
    args = parser.parse_args()

    rows = load_ground_truth(GROUND_TRUTH_PATH)
    if args.countries:
        wanted = set(args.countries.split(","))
        rows = [r for r in rows if r.country_iso3 in wanted]
    if args.years:
        wanted_years = {int(y) for y in args.years.split(",")}
        rows = [r for r in rows if r.year in wanted_years]

    windows = build_windows_from_ground_truth(rows)
    print(f"{len(windows)} country-season windows selected:")
    for w in windows:
        print(f"  {w.country_iso3} {w.season_year}: {w.window_start_date} to {w.window_end_date}")

    date_index = build_date_to_countries_index(windows)
    dates = sorted(date_index)
    if args.max_days:
        dates = dates[: args.max_days]
    print(f"{len(dates)} unique calendar days to process")

    MATCHED_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest = IngestionManifest(str(MANIFEST_PATH))
    write_match = ThreadSafeMatchWriter(MATCHED_DIR)

    start = time.monotonic()
    for i, day in enumerate(dates, 1):
        target_countries = date_index[day]
        run_ingestion_for_day(
            day.strftime("%Y%m%d"),
            target_countries,
            manifest,
            write_match=write_match,
            disk_path=str(DATA_DIR),
        )
        elapsed = time.monotonic() - start
        print(
            f"[{i}/{len(dates)}] {day} done ({','.join(target_countries)}) -- "
            f"elapsed {elapsed:.0f}s, total matched so far {manifest.total_matched()}"
        )

    print(f"Done. Total matched articles: {manifest.total_matched()}")


if __name__ == "__main__":
    main()
