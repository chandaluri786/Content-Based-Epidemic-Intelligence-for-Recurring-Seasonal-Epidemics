"""Resumable checkpoint of completed GDELT 15-minute-file timestamps (Step 2).

Append-only JSONL: one line per completed timestamp. A multi-hour/multi-day
batch job can be safely interrupted (killed, crashed, disk-guard abort) and
resumed without re-downloading anything already recorded here, except
`failed_transient` entries, which are deliberately retried on resume.
`not_found` (e.g. dates before the GKG 2.0 launch) and `parse_failed`
(corrupt zip) are permanently settled and never retried.
"""

import threading
from typing import Literal

from pipeline.common.io_jsonl import append_jsonl, read_jsonl_tolerant

ManifestStatus = Literal["ok", "not_found", "failed_transient", "parse_failed"]

_RETRYABLE_STATUSES = {"failed_transient"}


class IngestionManifest:
    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[ManifestStatus, int]] = {}
        for record in read_jsonl_tolerant(path):
            self._entries[record["stamp"]] = (record["status"], record.get("matched_count", 0))

    def is_done(self, stamp: str) -> bool:
        with self._lock:
            entry = self._entries.get(stamp)
        if entry is None:
            return False
        status, _ = entry
        return status not in _RETRYABLE_STATUSES

    def matched_count(self, stamp: str) -> int:
        with self._lock:
            entry = self._entries.get(stamp)
        return entry[1] if entry else 0

    def total_matched(self) -> int:
        with self._lock:
            return sum(count for _status, count in self._entries.values())

    def mark_done(self, stamp: str, status: ManifestStatus, matched_count: int = 0) -> None:
        with self._lock:
            self._entries[stamp] = (status, matched_count)
            append_jsonl(
                self._path, {"stamp": stamp, "status": status, "matched_count": matched_count}
            )
