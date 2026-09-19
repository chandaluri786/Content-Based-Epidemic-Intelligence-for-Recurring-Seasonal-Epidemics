"""Resumable per-URL extraction results store (Step 3).

One JSONL line per processed URL: {url, stamp, status, extraction, reason, model}.
Doubles as both the resumability manifest (is_done(url) lets a run skip
already-processed URLs) and the persisted results Step 5's join reads. `stamp`
is the GDELT snapshot timestamp the URL was matched under, propagated through
so epi-week assignment downstream uses ingestion time, not article-fetch time.
status is one of "extracted", "skipped_prefilter", "not_retrievable", "failed",
"excluded_geo_mismatch". The last is a successful extraction whose
`extraction["primary_country"]` disagreed with the country this file is for
(see pipeline/extraction/geo_crosscheck.py) -- the full extraction payload is
kept (nothing is deleted), just excluded from downstream content-signal
detection, so the exclusion is auditable and reversible if the rule changes.
`model` records which pooled model actually produced the extraction (None for
statuses that never reached an LLM call), so per-model quality can be audited.
"""

import threading
from typing import Any

from pipeline.common.io_jsonl import append_jsonl, read_jsonl_tolerant


class ExtractionStore:
    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._records: list[dict[str, Any]] = read_jsonl_tolerant(path)
        self._done_urls: set[str] = {r["url"] for r in self._records}

    def is_done(self, url: str) -> bool:
        with self._lock:
            return url in self._done_urls

    def iter_records(self):
        with self._lock:
            return list(self._records)

    def record(
        self,
        url: str,
        stamp: str,
        status: str,
        extraction: dict[str, Any] | None = None,
        reason: str | None = None,
        model: str | None = None,
    ) -> None:
        entry = {
            "url": url,
            "stamp": stamp,
            "status": status,
            "extraction": extraction,
            "reason": reason,
            "model": model,
        }
        with self._lock:
            self._done_urls.add(url)
            self._records.append(entry)
            append_jsonl(self._path, entry)
