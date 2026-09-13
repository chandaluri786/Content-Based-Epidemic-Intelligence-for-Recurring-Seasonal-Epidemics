import io
import zipfile
from unittest.mock import patch

import pytest

from pipeline.common.disk_guard import DiskSpaceError
from pipeline.common.http import NotFoundError, RequestFailedError
from pipeline.gdelt.manifest import IngestionManifest
from pipeline.gdelt.raw_downloader import (
    fifteen_min_stamps,
    iter_records_from_zip_bytes,
    process_timestamp,
    run_ingestion_for_day,
)

GOOD_LINE = (
    "id\tdate\t1\tsrc\thttp://example.com/flu-outbreak-story\t\t\tthemes\tcounts\t\t"
    "4#Nairobi, Kenya#KE#adm1#0#0#0#0\tp\to\tt\n"
)


def make_zip_bytes(inner_content: str, filename: str = "20230101000000.gkg.csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(filename, inner_content)
    return buf.getvalue()


@pytest.mark.unit
class TestFifteenMinStamps:
    def test_returns_96_stamps_for_a_day(self):
        stamps = fifteen_min_stamps("20230101")
        assert len(stamps) == 96

    def test_stamps_are_sorted_and_well_formed(self):
        stamps = fifteen_min_stamps("20230101")
        assert stamps[0] == "20230101000000"
        assert stamps[1] == "20230101001500"
        assert stamps[-1] == "20230101234500"
        assert stamps == sorted(stamps)

    def test_hourly_only_returns_24_stamps_at_minute_zero(self):
        stamps = fifteen_min_stamps("20230101", hourly_only=True)
        assert len(stamps) == 24
        assert all(stamp.endswith("0000") for stamp in stamps)
        assert stamps[1] == "20230101010000"


@pytest.mark.unit
class TestIterRecordsFromZipBytes:
    def test_yields_parsed_records_from_the_inner_csv(self):
        raw = make_zip_bytes(GOOD_LINE)
        records = list(iter_records_from_zip_bytes(raw))
        assert len(records) == 1
        assert records[0].url == "http://example.com/flu-outbreak-story"

    def test_skips_unparseable_lines(self):
        raw = make_zip_bytes("too\tfew\n" + GOOD_LINE)
        records = list(iter_records_from_zip_bytes(raw))
        assert len(records) == 1

    def test_bad_zip_bytes_raises_bad_zip_file(self):
        with pytest.raises(zipfile.BadZipFile):
            list(iter_records_from_zip_bytes(b"not a zip file"))


@pytest.mark.unit
class TestProcessTimestamp:
    def test_already_done_stamp_is_skipped(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        manifest.mark_done("20230101000000", status="ok", matched_count=1)
        calls = []
        process_timestamp(
            "20230101000000",
            ["KEN"],
            manifest,
            write_match=lambda *a: calls.append(a),
            download_fn=lambda stamp: (_ for _ in ()).throw(AssertionError("should not download")),
        )
        assert calls == []

    def test_successful_download_writes_matches_and_marks_ok(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        calls = []
        process_timestamp(
            "20230101000000",
            ["KEN"],
            manifest,
            write_match=lambda iso3, stamp, url: calls.append((iso3, stamp, url)),
            download_fn=lambda stamp: make_zip_bytes(GOOD_LINE),
        )
        assert calls == [("KEN", "20230101000000", "http://example.com/flu-outbreak-story")]
        assert manifest.is_done("20230101000000") is True
        assert manifest.matched_count("20230101000000") == 1

    def test_no_matching_country_still_marks_ok_with_zero_matches(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        process_timestamp(
            "20230101000000",
            ["USA"],  # GOOD_LINE mentions Kenya, not USA
            manifest,
            write_match=lambda *a: None,
            download_fn=lambda stamp: make_zip_bytes(GOOD_LINE),
        )
        assert manifest.is_done("20230101000000") is True
        assert manifest.matched_count("20230101000000") == 0

    def test_not_found_error_marks_not_found(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))

        def raise_not_found(stamp):
            raise NotFoundError("404")

        process_timestamp(
            "20140101000000",
            ["KEN"],
            manifest,
            write_match=lambda *a: None,
            download_fn=raise_not_found,
        )
        assert manifest.is_done("20140101000000") is True
        assert manifest.matched_count("20140101000000") == 0

    def test_transient_failure_marks_failed_transient_and_is_not_done(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))

        def raise_transient(stamp):
            raise RequestFailedError("500")

        process_timestamp(
            "20230101000000",
            ["KEN"],
            manifest,
            write_match=lambda *a: None,
            download_fn=raise_transient,
        )
        assert manifest.is_done("20230101000000") is False

    def test_bad_zip_marks_parse_failed(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        process_timestamp(
            "20230101000000",
            ["KEN"],
            manifest,
            write_match=lambda *a: None,
            download_fn=lambda stamp: b"not a zip",
        )
        assert manifest.is_done("20230101000000") is True
        assert manifest.matched_count("20230101000000") == 0


@pytest.mark.unit
class TestRunIngestionForDay:
    def test_processes_all_96_stamps_for_the_day(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        processed_stamps = []

        with patch("pipeline.gdelt.raw_downloader.ensure_min_free_space"):
            run_ingestion_for_day(
                "20230101",
                ["KEN"],
                manifest,
                write_match=lambda *a: None,
                download_fn=lambda stamp: processed_stamps.append(stamp)
                or make_zip_bytes(GOOD_LINE),
                disk_path=str(tmp_path),
            )
        assert len(processed_stamps) == 96

    def test_raises_disk_space_error_before_downloading_anything(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        called = []

        with (
            patch(
                "pipeline.gdelt.raw_downloader.ensure_min_free_space",
                side_effect=DiskSpaceError("out of space"),
            ),
            pytest.raises(DiskSpaceError),
        ):
            run_ingestion_for_day(
                "20230101",
                ["KEN"],
                manifest,
                write_match=lambda *a: None,
                download_fn=lambda stamp: called.append(stamp),
                disk_path=str(tmp_path),
            )
        assert called == []

    def test_skips_already_done_stamps_on_resume(self, tmp_path):
        manifest = IngestionManifest(str(tmp_path / "manifest.jsonl"))
        for stamp in fifteen_min_stamps("20230101")[:10]:
            manifest.mark_done(stamp, status="ok", matched_count=0)

        processed_stamps = []
        with patch("pipeline.gdelt.raw_downloader.ensure_min_free_space"):
            run_ingestion_for_day(
                "20230101",
                ["KEN"],
                manifest,
                write_match=lambda *a: None,
                download_fn=lambda stamp: processed_stamps.append(stamp)
                or make_zip_bytes(GOOD_LINE),
                disk_path=str(tmp_path),
            )
        assert len(processed_stamps) == 86
