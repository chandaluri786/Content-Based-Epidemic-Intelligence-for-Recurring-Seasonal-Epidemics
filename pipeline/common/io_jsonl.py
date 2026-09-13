"""Append-only JSONL helpers for resumable, crash-tolerant checkpoints.

Used by gdelt/manifest.py (per-timestamp ingestion checkpoint) and any other
stage that needs to survive an interrupted long-running batch job.
"""

import json
from typing import Any


def append_jsonl(path: str, record: dict[str, Any]) -> None:
    """Append one JSON record as a line, flushing and fsyncing immediately so
    an interrupted process loses at most this one in-flight write."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        import os

        os.fsync(f.fileno())


def read_jsonl_tolerant(path: str) -> list[dict[str, Any]]:
    """Read all complete JSON lines from path. Missing file returns [].
    A truncated last line (e.g. from a process killed mid-write) is dropped
    rather than raising, since manifest/checkpoint files must remain readable
    after an unclean shutdown."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []

    records: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError:
            is_last_line = i == len(lines) - 1
            if not is_last_line:
                raise
            # Truncated last line from an interrupted write: drop and stop.
            break

    return records
