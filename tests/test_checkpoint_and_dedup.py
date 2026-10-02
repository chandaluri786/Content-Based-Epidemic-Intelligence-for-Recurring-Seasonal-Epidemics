"""
Unit tests for cross-run checkpointing (run_pipeline._day_needs_processing,
_load_completed_days/_save_completed_days) and the local storage backend's
already_stored_ids(), both pure/local-filesystem logic -- no network
needed. Run with: pytest
"""

import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.storage import LocalStorageBackend
from run_pipeline import _day_needs_processing, _load_completed_days, _save_completed_days


def test_day_needs_processing_false_when_same_countries_already_checked():
    completed = {date(2023, 1, 15): {"USA", "IND"}}
    assert not _day_needs_processing(date(2023, 1, 15), {"USA"}, completed)
    assert not _day_needs_processing(date(2023, 1, 15), {"USA", "IND"}, completed)


def test_day_needs_processing_true_for_a_country_not_checked_before():
    """A later run asking for a country not covered by the earlier check
    (e.g. earlier run was --countries USA, this one adds IND) must not be
    skipped -- the checkpoint is a lower bound on what's been checked, not
    an upper bound on what could be found there."""
    completed = {date(2023, 1, 15): {"USA"}}
    assert _day_needs_processing(date(2023, 1, 15), {"USA", "IND"}, completed)


def test_day_needs_processing_true_for_a_day_never_seen_before():
    assert _day_needs_processing(date(2023, 1, 15), {"USA"}, completed={})


def test_completed_days_round_trip_through_disk():
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "completed_days.json")
        completed = {date(2023, 1, 15): {"USA", "IND"}, date(2023, 1, 16): {"USA"}}
        _save_completed_days(completed, path)
        reloaded = _load_completed_days(path)
        assert reloaded == completed


def test_load_completed_days_empty_when_file_absent():
    assert _load_completed_days("/nonexistent/path/completed_days.json") == {}


def test_local_backend_already_stored_ids_reads_across_years():
    from models import ExtractedArticle

    with tempfile.TemporaryDirectory() as d:
        backend = LocalStorageBackend(base_dir=d)
        backend.write(ExtractedArticle(
            gkg_record_id="20220601000000-1", url="https://example.com/a", gkg_datetime="2022-06-01T00:00:00",
            themes=[], locations=[], article_text="x",
        ))
        backend.write(ExtractedArticle(
            gkg_record_id="20230601000000-2", url="https://example.com/b", gkg_datetime="2023-06-01T00:00:00",
            themes=[], locations=[], article_text="y",
        ))

        ids = backend.already_stored_ids()
        assert ids == {"20220601000000-1", "20230601000000-2"}


def test_local_backend_already_stored_ids_empty_when_nothing_stored():
    with tempfile.TemporaryDirectory() as d:
        backend = LocalStorageBackend(base_dir=str(Path(d) / "does_not_exist_yet"))
        assert backend.already_stored_ids() == set()
