"""
Unit tests for gap-day detection and the seeded checkpoint
(dataset_prep/gap_days.py). No network. Run with: pytest
"""

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_prep.gap_days import covered_days, find_gap_days, seeded_checkpoint
from models import CountrySeasonWindow
from run_pipeline import _day_needs_processing


def _window(country: str, start: date, end: date) -> CountrySeasonWindow:
    return CountrySeasonWindow(country_iso3=country, season_year=start.year, onset_date=start,
                               window_start=start, window_end=end)


def test_covered_days_reads_dates_from_pool():
    with tempfile.TemporaryDirectory() as d:
        pool = Path(d) / "pooled_articles.jsonl"
        pool.write_text(
            json.dumps({"datetime": "2023-01-01T10:00:00"}) + "\n"
            + json.dumps({"datetime": "2023-01-01T23:45:00"}) + "\n"
            + json.dumps({"datetime": "2023-01-03T00:00:00"}) + "\n"
        )
        assert covered_days(pool) == {date(2023, 1, 1), date(2023, 1, 3)}


def test_find_gap_days_is_window_days_minus_covered_days():
    windows = [_window("USA", date(2023, 1, 1), date(2023, 1, 3)), _window("AUS", date(2023, 1, 3), date(2023, 1, 4))]
    covered = {date(2023, 1, 1), date(2023, 1, 3), date(2022, 6, 1)}
    assert find_gap_days(windows, covered) == [date(2023, 1, 2), date(2023, 1, 4)]


def test_seeded_checkpoint_makes_the_pipeline_process_only_gap_days():
    windows = [_window("USA", date(2023, 1, 1), date(2023, 1, 3))]
    gaps = [date(2023, 1, 2)]
    countries = {"USA", "AUS"}

    checkpoint = seeded_checkpoint(windows, gaps, countries)

    to_process = [day for day in (date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3))
                  if _day_needs_processing(day, countries, checkpoint)]
    assert to_process == gaps


def test_shard_days_splits_gaps_disjointly_and_interleaves_years():
    from dataset_prep.gap_days import shard_days

    gaps = [date(2015, 5, d) for d in range(1, 8)] + [date(2024, 9, d) for d in range(1, 4)]
    shards = shard_days(gaps, 3)

    assert sorted(d for shard in shards for d in shard) == gaps
    assert len({d for shard in shards for d in shard}) == len(gaps)
    assert [len(s) for s in shards] == [4, 3, 3]
    assert all(any(d.year == 2015 for d in s) for s in shards)


def test_each_shard_checkpoint_leaves_only_that_shards_days():
    from dataset_prep.gap_days import shard_days

    windows = [_window("USA", date(2023, 1, 1), date(2023, 1, 6))]
    gaps = [date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 5)]
    countries = {"USA"}
    all_days = [date(2023, 1, d) for d in range(1, 7)]

    for shard in shard_days(gaps, 2):
        checkpoint = seeded_checkpoint(windows, shard, countries)
        assert [d for d in all_days if _day_needs_processing(d, countries, checkpoint)] == shard
