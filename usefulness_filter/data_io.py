"""Read the pool's bucket list and the gold labels. A missing input stops the run."""

import csv
import json
from pathlib import Path

import filter_config as cfg


def _require(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"missing input: {path} (see usefulness_filter/README.md, Inputs)")
    return path


def load_pool_buckets(path: Path = cfg.POOL_BUCKETS_PATH) -> list[dict]:
    """The eligible pool: one row per article with record_id, bucket, country, year, scan_date, url."""
    # The sampling files may start with a BOM and use CRLF; csv handles both with these options.
    with open(_require(path), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_gold_useful(path: Path = cfg.GOLD_LABELS_PATH) -> dict[str, bool]:
    """{article_id: useful} for the 1,120 gold articles."""
    records = json.loads(_require(path).read_text(encoding="utf-8"))
    return {record["article_id"]: bool(record["useful"]) for record in records}
