"""Raw 15-minute GKG mirror ingestion (Step 2): fetch each zip fully
in-memory, filter to flu-candidate URLs for the target countries, and record
progress in a resumable manifest. Never writes the raw zip to disk -- the
disk-space guard exists for the small matched-output/log files this produces,
and to abort a run rather than risk repeating the earlier full-disk incident.
"""

import io
import zipfile
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

from pipeline.common.disk_guard import ensure_min_free_space
from pipeline.common.http import NotFoundError, RequestFailedError, get_with_retry
from pipeline.config import GDELT_RAW_MIRROR_BASE, MIN_FREE_DISK_GB
from pipeline.gdelt.flu_filter import find_matching_countries
from pipeline.gdelt.gkg_parser import GkgRecord, parse_gkg_line
from pipeline.gdelt.manifest import IngestionManifest

WriteMatch = Callable[[str, str, str], None]  # (country_iso3, stamp, url) -> None
DownloadFn = Callable[[str], bytes]

DOWNLOAD_CONCURRENCY = 8


def fifteen_min_stamps(date_str: str, hourly_only: bool = False) -> list[str]:
    """The fifteen-minute timestamps (YYYYMMDDHHMMSS) for a day, e.g.
    '20230101' -> ['20230101000000', '20230101001500', ..., '20230101234500'].
    hourly_only=True returns just the 24 on-the-hour stamps (1/4 the volume),
    the Step 2a calibration option -- only adopt it for the full run if it
    clears the >=90% recall bar against the all-96 baseline."""
    minutes = (0,) if hourly_only else (0, 15, 30, 45)
    return [f"{date_str}{h:02d}{m:02d}00" for h in range(24) for m in minutes]


def download_zip_bytes(stamp: str) -> bytes:
    url = f"{GDELT_RAW_MIRROR_BASE}/{stamp}.gkg.csv.zip"
    response = get_with_retry(url, max_retries=3, backoff_base=2.0, timeout=60)
    return response.content


def iter_records_from_zip_bytes(raw_zip: bytes) -> Iterator[GkgRecord]:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        name = zf.namelist()[0]
        with zf.open(name) as f:
            for line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
                record = parse_gkg_line(line)
                if record is not None:
                    yield record


def process_timestamp(
    stamp: str,
    target_countries: list[str],
    manifest: IngestionManifest,
    write_match: WriteMatch,
    download_fn: DownloadFn = download_zip_bytes,
) -> None:
    """Download, parse, and filter one 15-minute timestamp, unless the
    manifest already has a settled (non-retryable) result for it."""
    if manifest.is_done(stamp):
        return

    try:
        raw_zip = download_fn(stamp)
    except NotFoundError:
        manifest.mark_done(stamp, status="not_found")
        return
    except RequestFailedError:
        manifest.mark_done(stamp, status="failed_transient")
        return

    try:
        records = list(iter_records_from_zip_bytes(raw_zip))
    except zipfile.BadZipFile:
        manifest.mark_done(stamp, status="parse_failed")
        return
    finally:
        del raw_zip

    matched_count = 0
    for record in records:
        for iso3 in find_matching_countries(record, target_countries):
            write_match(iso3, stamp, record.url)
            matched_count += 1

    manifest.mark_done(stamp, status="ok", matched_count=matched_count)


def run_ingestion_for_day(
    date_str: str,
    target_countries: list[str],
    manifest: IngestionManifest,
    write_match: WriteMatch,
    download_fn: DownloadFn = download_zip_bytes,
    disk_path: str = ".",
    min_free_gb: float = MIN_FREE_DISK_GB,
    max_workers: int = DOWNLOAD_CONCURRENCY,
    hourly_only: bool = False,
) -> None:
    """Process all timestamps for one calendar day against the countries
    whose windows include this day (per window_builder.build_date_to_countries_index),
    so a day shared by multiple country-seasons is downloaded once.

    Timestamps are downloaded concurrently (matching the concurrency already
    validated in the feasibility spike) -- IngestionManifest is internally
    lock-protected, so `write_match` is the only caller-supplied piece that
    must itself be thread-safe (e.g. a single JSONL append per country file,
    each protected by its own lock). hourly_only=True uses the 24-file/day
    Step 2a subsampling option instead of all 96."""
    ensure_min_free_space(min_free_gb, disk_path)

    stamps = fifteen_min_stamps(date_str, hourly_only=hourly_only)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(
            executor.map(
                lambda stamp: process_timestamp(
                    stamp, target_countries, manifest, write_match, download_fn=download_fn
                ),
                stamps,
            )
        )
