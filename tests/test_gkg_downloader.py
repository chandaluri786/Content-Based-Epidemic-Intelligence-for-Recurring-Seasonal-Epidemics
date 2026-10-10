"""
Unit tests for Stage 3 download failure handling (pipeline/gkg_downloader.py)
and the day-level consequence in run_pipeline.process_day: a GKG file that
fails to download must never be silently dropped from a day that then gets
checkpointed as complete. requests is monkeypatched -- no network.
Run with: pytest
"""

import io
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_pipeline
from pipeline import gkg_downloader
from pipeline.gkg_downloader import DownloadFailed, download_file


class _Resp:
    def __init__(self, status: int, content: bytes = b"") -> None:
        self.status_code = status
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def _zipped(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("x.gkg.csv", text)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(gkg_downloader.time, "sleep", lambda s: None)


def _serve(monkeypatch, responses: list):
    calls = iter(responses)

    def fake_get(url, timeout):
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(gkg_downloader.requests, "get", fake_get)


def test_missing_slot_404_returns_none(monkeypatch):
    _serve(monkeypatch, [_Resp(404)])
    assert download_file("u") is None


def test_success_returns_lines(monkeypatch):
    _serve(monkeypatch, [_Resp(200, _zipped("a\tb\nc\td"))])
    assert download_file("u") == ["a\tb", "c\td"]


def test_transient_failure_is_retried(monkeypatch):
    monkeypatch.setattr(gkg_downloader, "HTTP_MAX_RETRIES", 2)
    _serve(monkeypatch, [requests.Timeout("slow"), _Resp(503), _Resp(200, _zipped("ok"))])
    assert download_file("u") == ["ok"]


def test_persistent_failure_raises_instead_of_returning_none(monkeypatch):
    _serve(monkeypatch, [requests.Timeout("slow")] * 10)
    with pytest.raises(DownloadFailed, match="u"):
        download_file("u")


def test_corrupt_zip_raises(monkeypatch):
    _serve(monkeypatch, [_Resp(200, b"not a zip")] * 10)
    with pytest.raises(DownloadFailed):
        download_file("u")


def test_process_day_returns_none_when_a_file_fails(monkeypatch):
    def failing_download(url):
        raise DownloadFailed(url)

    monkeypatch.setattr(run_pipeline.gkg_downloader, "iter_day_urls", lambda day: iter(["u1", "u2"]))
    monkeypatch.setattr(run_pipeline.gkg_downloader, "download_file", failing_download)
    assert run_pipeline.process_day(date(2015, 5, 1), {"USA": "US"}, storage=None, seen_ids=set()) is None


def test_process_day_returns_summaries_when_all_files_download(monkeypatch):
    monkeypatch.setattr(run_pipeline.gkg_downloader, "iter_day_urls", lambda day: iter(["u1"]))
    monkeypatch.setattr(run_pipeline.gkg_downloader, "download_file", lambda url: None)
    assert run_pipeline.process_day(date(2015, 5, 1), {"USA": "US"}, storage=None, seen_ids=set()) == []
