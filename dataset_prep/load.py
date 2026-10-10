"""
Streaming reader for the pooled dataset directory: one subfolder per year
(e.g. "2018"), each holding one JSONL file per source of stored articles
(e.g. "upload.jsonl", "redownload.jsonl", "gapfill.jsonl"; same schema as
the pipeline's local storage backend writes).

Files are streamed line by line, never loaded whole -- the full dataset is
well over a gigabyte of article text.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("gkg_record_id", "url", "datetime", "article")
NON_BLANK_FIELDS = ("gkg_record_id", "url")
# The pipeline always writes datetime.isoformat() of a GKG timestamp. Exact
# dedup picks the earliest scan by string comparison, which is only valid
# if every row uses this one format.
DATETIME_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


@dataclass(frozen=True)
class SourceLine:
    """One parsed record and exactly where it came from."""
    source_file: str     # "<year>/<file name>" -- unique per file, used as identity and for reporting
    line_no: int
    record: dict


@dataclass(frozen=True)
class BadLine:
    source_file: str
    line_no: int
    reason: str


def iter_jsonl_files(dataset_dir: Path) -> list[Path]:
    """Every JSONL file one level down, in a stable order."""
    return sorted(dataset_dir.glob("*/*.jsonl"))


def _parse(line: str) -> tuple[dict | None, str]:
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg}"
    if not isinstance(record, dict):
        return None, "not a JSON object"
    missing = [f for f in REQUIRED_FIELDS if not isinstance(record.get(f), str)]
    if missing:
        return None, f"missing or non-string field(s): {', '.join(missing)}"
    blank = [f for f in NON_BLANK_FIELDS if not record[f].strip()]
    if blank:
        return None, f"blank field(s): {', '.join(blank)}"
    if not DATETIME_FORMAT.match(record["datetime"]):
        return None, f"datetime not YYYY-MM-DDTHH:MM:SS: {record['datetime']!r}"
    return record, ""


def iter_lines(dataset_dir: Path) -> Iterator[SourceLine | BadLine]:
    """Yields every record in the dataset, plus a BadLine for each line
    that can't be used. Malformed lines are reported, not raised, so one
    bad line can't abort a pass over 300k records -- same policy as the
    pipeline's own parser."""
    for path in iter_jsonl_files(dataset_dir):
        source_file = f"{path.parent.name}/{path.name}"
        with path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f):
                if not line.strip():
                    continue
                record, reason = _parse(line)
                if record is None:
                    logger.warning("Skipping %s line %d: %s", source_file, line_no, reason)
                    yield BadLine(source_file=source_file, line_no=line_no, reason=reason)
                    continue
                yield SourceLine(source_file=source_file, line_no=line_no, record=record)


def iter_records(dataset_dir: Path) -> Iterator[SourceLine]:
    """Just the usable records."""
    for item in iter_lines(dataset_dir):
        if isinstance(item, SourceLine):
            yield item
