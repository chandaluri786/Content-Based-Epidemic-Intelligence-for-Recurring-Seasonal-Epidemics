"""
Stage 3: download raw GKG 2.1 files from GDELT's public mirror.

GDELT publishes a new file every 15 minutes (96/day) at a fixed, predictable
URL pattern -- there is no search endpoint and no authentication. This is
unfiltered bulk download; all filtering happens downstream in Stage 5.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime

import requests

from config import GDELT_RAW_MIRROR_BASE, HTTP_TIMEOUT_SECONDS

# Every 15-minute mark in a day: 00:00, 00:15, 00:30, ..., 23:45 (96 total)
_FIFTEEN_MINUTE_MARKS = [(hour, minute) for hour in range(24) for minute in (0, 15, 30, 45)]


def _timestamp_for(day: date, hour: int, minute: int) -> str:
    return datetime(day.year, day.month, day.day, hour, minute).strftime("%Y%m%d%H%M%S")


def file_url_for(day: date, hour: int, minute: int) -> str:
    timestamp = _timestamp_for(day, hour, minute)
    return f"{GDELT_RAW_MIRROR_BASE}/{timestamp}.gkg.csv.zip"


def file_url_for_timestamp(timestamp: str) -> str:
    """Builds the file URL for an exact GDELT timestamp string
    (YYYYMMDDHHMMSS, e.g. "20230115121500") -- used by run_pipeline.py's
    --test-timestamp mode to download exactly one file instead of a whole
    day's 96."""
    return f"{GDELT_RAW_MIRROR_BASE}/{timestamp}.gkg.csv.zip"


def download_file(url: str) -> list[str] | None:
    """Returns the raw tab-separated lines of one GKG file, or None if the
    request failed or that 15-minute slot has no published file (happens
    occasionally -- GDELT does not guarantee every slot is populated)."""
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        inner_name = zf.namelist()[0]
        raw_bytes = zf.read(inner_name)

    return raw_bytes.decode("utf-8", errors="replace").splitlines()


def iter_day_urls(day: date):
    """Yields all 96 file URLs for one calendar day, in chronological order."""
    for hour, minute in _FIFTEEN_MINUTE_MARKS:
        yield file_url_for(day, hour, minute)
