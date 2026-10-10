"""
Unit tests for cross-file exact dedup (dataset_prep/exact_dedup.py) --
pure logic plus a small end-to-end run over a temporary dataset dir, no
network needed. Run with: pytest
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_prep.exact_dedup import RecordRef, choose_canonical, cluster_duplicates, dedup_dataset, normalize_url


def _ref(record_id: str, url: str, dt: str = "2023-01-01T00:00:00", text_length: int = 100,
         source_file: str = "2023/upload.jsonl", line_no: int = 0) -> RecordRef:
    return RecordRef(
        source_file=source_file, line_no=line_no,
        record_id=record_id, normalized_url=normalize_url(url), datetime=dt, text_length=text_length,
    )


def test_normalize_url_ignores_scheme_www_case_and_trailing_slash():
    assert normalize_url("http://www.Example.com/news/story/") == normalize_url("https://example.com/news/story")


def test_normalize_url_drops_tracking_params_but_keeps_real_ones():
    assert normalize_url("https://x.com/a?id=5&utm_source=tw&fbclid=abc") == "x.com/a?id=5"
    assert normalize_url("https://x.com/a?id=5") != normalize_url("https://x.com/a?id=6")


def test_normalize_url_sorts_query_params_and_drops_default_ports():
    assert normalize_url("https://x.com:443/a?b=2&a=1") == normalize_url("http://x.com:80/a?a=1&b=2")
    assert normalize_url("https://x.com:8443/a") != normalize_url("https://x.com/a")


def test_normalize_url_keeps_path_case():
    assert normalize_url("https://x.com/Story") != normalize_url("https://x.com/story")


def test_cluster_links_same_record_id_across_files():
    refs = [_ref("A", "https://x.com/1", source_file="2018/upload.jsonl"),
            _ref("A", "https://x.com/1", source_file="2018/redownload.jsonl")]
    assert cluster_duplicates(refs) == [[0, 1]]


def test_cluster_links_same_url_with_different_record_ids():
    refs = [_ref("A", "http://www.x.com/1/"), _ref("B", "https://x.com/1")]
    assert cluster_duplicates(refs) == [[0, 1]]


def test_cluster_is_transitive_across_id_and_url():
    """A~B share an ID, B~C share a URL -> one cluster, even though A and C share nothing directly."""
    refs = [_ref("A", "https://x.com/1"), _ref("A", "https://x.com/2"), _ref("C", "https://x.com/2")]
    assert cluster_duplicates(refs) == [[0, 1, 2]]


def test_cluster_keeps_unrelated_records_apart():
    refs = [_ref("A", "https://x.com/1"), _ref("B", "https://x.com/2")]
    assert cluster_duplicates(refs) == [[0], [1]]


def test_canonical_is_earliest_scan():
    late = _ref("A", "https://x.com/1", dt="2023-01-02T00:00:00", text_length=999)
    early = _ref("B", "https://x.com/1", dt="2023-01-01T00:00:00", text_length=1)
    assert choose_canonical([late, early]) == early


def test_canonical_tie_breaks_on_longer_text_then_file():
    short = _ref("A", "https://x.com/1", text_length=10, source_file="2018/redownload.jsonl")
    long_ = _ref("A", "https://x.com/1", text_length=20, source_file="2018/upload.jsonl")
    assert choose_canonical([short, long_]) == long_

    a = _ref("A", "https://x.com/1", source_file="2018/upload.jsonl")
    b = _ref("A", "https://x.com/1", source_file="2018/redownload.jsonl")
    assert choose_canonical([a, b]) == b


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def _record(record_id: str, url: str, dt: str, article: str) -> dict:
    return {"gkg_record_id": record_id, "url": url, "datetime": dt, "themes": [], "locations": [], "article": article}


def test_dedup_dataset_end_to_end_writes_one_row_per_cluster_and_skips_bad_lines():
    with tempfile.TemporaryDirectory() as d:
        dataset = Path(d) / "dataset"
        _write_jsonl(dataset / "2018" / "upload.jsonl", [
            _record("A", "https://x.com/1", "2018-01-02T00:00:00", "first"),
            _record("B", "https://x.com/2", "2018-01-03T00:00:00", "other"),
        ])
        _write_jsonl(dataset / "2018" / "redownload.jsonl", [
            _record("A", "https://x.com/1", "2018-01-02T00:00:00", "first"),
            _record("Z", "http://www.x.com/1/", "2018-01-01T00:00:00", "earlier rescan"),
        ])
        with open(dataset / "2018" / "upload.jsonl", "a") as f:
            f.write("{not json\n")
        out = Path(d) / "pool" / "pooled_articles.jsonl"

        report = dedup_dataset(dataset, out)

        rows = [json.loads(line) for line in out.read_text().splitlines()]
        by_id = {r["gkg_record_id"]: r for r in rows}
        assert set(by_id) == {"Z", "B"}
        assert by_id["Z"]["merged_record_ids"] == ["A", "Z"]
        assert by_id["Z"]["source_files"] == ["2018/redownload.jsonl", "2018/upload.jsonl"]
        assert by_id["B"]["merged_record_ids"] == ["B"]
        assert report["rows_in"] == 4
        assert report["rows_out"] == 2
        assert report["bad_lines"] == 1
        assert report["file_pair_overlaps"] == {"2018/redownload.jsonl | 2018/upload.jsonl": 1}
        assert report["per_file"]["2018/upload.jsonl"] == {"rows_in": 2, "rows_kept": 1}


def test_dedup_dataset_rejects_blank_keys_and_non_iso_datetimes():
    """Blank URLs would all share one dedup key; mixed datetime formats
    would break the earliest-scan string comparison."""
    with tempfile.TemporaryDirectory() as d:
        dataset = Path(d) / "dataset"
        _write_jsonl(dataset / "2018" / "matched_articles.jsonl", [
            _record("A", "", "2018-01-02T00:00:00", "blank url"),
            _record("B", "", "2018-01-02T00:00:00", "blank url too"),
            _record(" ", "https://x.com/1", "2018-01-02T00:00:00", "blank id"),
            _record("C", "https://x.com/2", "2018-01-02", "date only"),
            _record("D", "https://x.com/3", "2018-01-02T00:00:00", "ok"),
        ])
        out = Path(d) / "pooled_articles.jsonl"

        report = dedup_dataset(dataset, out)

        assert [json.loads(l)["gkg_record_id"] for l in out.read_text().splitlines()] == ["D"]
        assert report["bad_lines"] == 4
