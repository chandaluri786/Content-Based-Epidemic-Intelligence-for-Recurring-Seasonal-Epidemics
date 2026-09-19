"""One-off Step 2 ingestion pass for the cohort countries that only had
spike-era single-day content estimates -- matching only, no LLM calls.
Reuses the same validated building blocks as pipeline/cli/run_step2_ingest.py
(window builder, raw downloader, manifest, flu filter) but uses its own
manifest file (manifest_batch2.jsonl) instead of the shared manifest.jsonl:
IngestionManifest.is_done() keys purely by GDELT 15-minute timestamp, with no
awareness of which countries were checked against that timestamp. USA 2023 +
KEN 2023 (the pilot) already settled some of this batch's days in the shared
manifest; reusing it here would silently skip re-matching those days against
this batch's countries and undercount them with no error. A fresh manifest
forces every day in this batch's own window to be checked against this
batch's target countries. (This is a real gap in the shared manifest's design
worth fixing before any future incremental full-scale Step 2 run adds new
countries/years on top of already-ingested ones -- flagged in tasks.md, not
fixed here.)

Originally covered GBR/JPN/AUS/IND/BRA/IDN. Team decision: dropped GBR and
JPN to keep a uniform 6-country cohort with one onset-detection method (no
per-country UKHSA/peak-proxy exceptions) -- see pipeline/config.py. Their
already-collected matches in data/gdelt_matched/{GBR,JPN}.jsonl are kept on
disk but no longer targeted by this script. TARGET_COUNTRIES below now
reflects the real cohort (config.COUNTRIES with included_in_gdelt_cohort has
since been updated to match), so it could be read from there instead of
hardcoded -- left explicit here since this script predates that flag flip.

Usage:
    python -m investigation.run_step2_remaining_countries [--max-days N]
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
MANIFEST_PATH = DATA_DIR / "gdelt_manifest" / "manifest_batch2.jsonl"

TARGET_COUNTRIES = ["AUS", "IND", "BRA", "IDN"]


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
            if r["country_iso3"] not in TARGET_COUNTRIES:
                continue
            if not r["onset_date"]:
                continue
            rows.append((r["country_iso3"], int(r["year"]), date.fromisoformat(r["onset_date"])))
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
