"""Step 2 full-window ingestion for USA and Kenya's remaining seasons --
matching only, no LLM calls. USA and KEN each already have one season
ingested (2023, the Step 2 pilot: 6,179 USA + 8 KEN matched articles, in
data/gdelt_matched/{USA,KEN}.jsonl via the shared manifest.jsonl). This
script covers every *other* defined-onset season for these two countries
(USA: 2015,2016,2017,2018,2019,2020,2022,2024 -- 2021 has no onset found;
KEN: 2016,2018,2019,2020,2021,2022,2024 -- 2015 has no data, 2017 has no
onset found), so both reach full 2015-2024 per-season coverage like
AUS/IND/BRA/IDN already have.

2023 is explicitly excluded from TARGET rows below (not re-requested) --
each season's GDELT window is `[onset - 10 weeks, onset + 2 weeks]`
(pipeline/config.py), and every other USA/KEN season is calendar-months
away from the 2023 window with no overlap, so excluding it here cannot
cause the 2023 pilot data to be silently undercounted or duplicated.

Reuses the same validated building blocks as pipeline/cli/run_step2_ingest.py
and investigation/run_step2_remaining_countries.py, but (like that script)
uses its own manifest file (manifest_batch3.jsonl) rather than the shared
manifest.jsonl or manifest_batch2.jsonl: IngestionManifest.is_done() keys
purely by GDELT 15-minute timestamp, with no awareness of which countries
were checked against that timestamp. Both prior manifests may have already
settled some of this batch's days against other countries (AUS/IND/BRA/IDN
in batch2, USA/KEN's own 2023 window in the shared manifest) -- reusing
either here would silently skip re-matching those days against USA/KEN's
new season windows and undercount them with no error. A fresh manifest
forces every day in this batch's own window to be checked against USA/KEN.
Matches are appended to the existing data/gdelt_matched/{USA,KEN}.jsonl
files, alongside the pilot's already-collected lines.

Usage:
    python -m investigation.run_step2_usa_ken [--max-days N]
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
    build_window_for_country_season,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth" / "country_seasons.csv"
MATCHED_DIR = DATA_DIR / "gdelt_matched"
MANIFEST_PATH = DATA_DIR / "gdelt_manifest" / "manifest_batch3.jsonl"

TARGET_COUNTRIES = ["USA", "KEN"]
ALREADY_INGESTED_YEARS = {"USA": {2023}, "KEN": {2023}}


class ThreadSafeMatchWriter:
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


def load_target_rows(path: Path) -> list[tuple[str, int, date]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            iso3 = r["country_iso3"]
            if iso3 not in TARGET_COUNTRIES:
                continue
            if not r["onset_date"]:
                continue
            year = int(r["year"])
            if year in ALREADY_INGESTED_YEARS.get(iso3, set()):
                continue
            rows.append((iso3, year, date.fromisoformat(r["onset_date"])))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-days", type=int, default=None, help="Process at most N unique days")
    args = parser.parse_args()

    rows = load_target_rows(GROUND_TRUTH_PATH)
    windows = [build_window_for_country_season(iso3, year, onset) for iso3, year, onset in rows]
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
        rate = elapsed / i
        remaining = (len(dates) - i) * rate
        print(
            f"[{i}/{len(dates)}] {day} done ({','.join(target_countries)}) -- "
            f"elapsed {elapsed / 3600:.2f}h, ETA {remaining / 3600:.2f}h, "
            f"total matched so far {manifest.total_matched()}",
            flush=True,
        )

    print(f"Done. Total matched articles (this batch's manifest): {manifest.total_matched()}")


if __name__ == "__main__":
    main()
