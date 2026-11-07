"""Read the inputs of the tables. A missing input stops the run."""

import csv
import json
from pathlib import Path

import signal_config as cfg


def _require(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"missing input: {path} (see flu_signal/README.md, Inputs)")
    return path


def _read_csv(path: Path) -> list[dict]:
    # The sampling files may start with a BOM and use CRLF; csv handles both with these options.
    with open(_require(path), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_pool_buckets(path: Path = cfg.POOL_BUCKETS_PATH) -> list[dict]:
    """One row per pool article: record_id, scan_date, country, season, phase, bucket, group_size, ..."""
    return _read_csv(path)


def load_filter_layers(path: Path = cfg.FILTER_DECISIONS_PATH) -> dict[str, str]:
    """{record_id: keyword-filter layer}."""
    return {row["record_id"]: row["layer"] for row in _read_csv(path)}


def load_season_assignments(wanted_ids: set[str], path: Path = cfg.SEASON_ASSIGNMENTS_PATH) -> dict[str, list[str]]:
    """{record_id: [season_id, ...]} for the wanted articles. The file is large, so it is streamed."""
    found: dict[str, list[str]] = {}
    with open(_require(path), encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            if record["gkg_record_id"] in wanted_ids:
                found[record["gkg_record_id"]] = list(record["country_seasons"])
    return found


def load_season_windows(path: Path = cfg.SEASON_WINDOWS_PATH) -> list[dict]:
    """The 38 country-seasons: season_id, country, season_year, onset_date, window_start, window_end."""
    return json.loads(_require(path).read_text(encoding="utf-8"))


def load_llm_answers(path: Path = cfg.LLM_REPLIES_PATH) -> dict[str, dict]:
    """{article_id: {"useful", "items", "status"}} from the combined pool run."""
    answers: dict[str, dict] = {}
    with open(_require(path), encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            parsed = record.get("parsed")
            if not parsed:
                raise ValueError(f"article {record['article_id']} has no parsed reply (status {record.get('status')})")
            answers[record["article_id"]] = {"useful": bool(parsed.get("useful")),
                                             "items": list(parsed.get("items") or []),
                                             "status": record.get("status")}
    return answers


def load_gold_answers(path: Path = cfg.GOLD_LABELS_PATH) -> dict[str, dict]:
    """{article_id: {"useful", "items", "status"}} from the gold labels."""
    records = json.loads(_require(path).read_text(encoding="utf-8"))
    return {record["article_id"]: {"useful": bool(record["useful"]),
                                   "items": list(record.get("items") or []),
                                   "status": "gold"} for record in records}
