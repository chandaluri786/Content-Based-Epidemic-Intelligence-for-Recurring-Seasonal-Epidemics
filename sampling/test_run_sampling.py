"""Tests for reading the pooled corpus and drawing the sample (run_sampling.py).

Uses a tiny made-up pool in a temporary folder. Run from the repo root with: pytest sampling/
"""
import json
import random
from datetime import date, timedelta

import pytest

from run_sampling import add_buckets, draw, parse_locations, phase_of, read_pool

ONSET = date(2020, 3, 2)


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _article(record_id, day, text="Flu cases are rising in the city."):
    return {"gkg_record_id": record_id, "url": f"https://x.com/{record_id}", "datetime": f"{day}T10:00:00",
            "themes": [], "locations": [], "article": text}


@pytest.fixture
def pool_dir(tmp_path):
    """Five articles: A1/A2/A3 are copies of one story, B is its own story, C is outside every window."""
    day = (ONSET - timedelta(days=3)).isoformat()
    (tmp_path / "season_windows.json").write_text(json.dumps([{
        "season_id": "USA-2019", "country": "USA", "season_year": 2019, "onset_date": ONSET.isoformat(),
        "window_start": (ONSET - timedelta(weeks=10)).isoformat(), "window_end": (ONSET + timedelta(weeks=2)).isoformat(),
    }]))
    ids = ["A1", "A2", "A3", "B", "C"]
    _write_jsonl(tmp_path / "pooled_articles.jsonl", [_article(i, day) for i in ids])
    _write_jsonl(tmp_path / "season_assignments.jsonl", [
        {"gkg_record_id": i, "datetime": f"{day}T10:00:00", "country_seasons": [] if i == "C" else ["USA-2019"],
         "sampling_country": None if i == "C" else "USA", "sampling_season": None if i == "C" else "USA-2019"}
        for i in ids
    ])
    _write_jsonl(tmp_path / "near_dup_groups.jsonl", [
        {"gkg_record_id": "A1", "near_dup_group": "A1", "group_size": 3},
        {"gkg_record_id": "A2", "near_dup_group": "A1", "group_size": 3},
        {"gkg_record_id": "A3", "near_dup_group": "A1", "group_size": 3},
        {"gkg_record_id": "B", "near_dup_group": "B", "group_size": 1},
        {"gkg_record_id": "C", "near_dup_group": "C", "group_size": 1},
    ])
    return tmp_path


@pytest.mark.parametrize("days_from_onset, phase", [
    (-70, "early"), (-36, "early"), (-35, "late"), (-1, "late"), (0, "post"), (14, "post"),
])
def test_phase_boundaries(days_from_onset, phase):
    assert phase_of(ONSET + timedelta(days=days_from_onset), ONSET) == phase


def test_read_pool_keeps_only_articles_with_a_sampling_season(pool_dir):
    articles = read_pool(pool_dir, random.Random(0))
    assert "C" not in {a["record_id"] for a in articles}
    assert all(a["season"] == "USA-2019" and a["country"] == "USA" for a in articles)


def test_read_pool_keeps_one_article_per_near_dup_group(pool_dir):
    articles = read_pool(pool_dir, random.Random(0))
    assert sorted(a["near_dup_group"] for a in articles) == ["A1", "B"]


def test_read_pool_adds_phase_and_group_size(pool_dir):
    story = next(a for a in read_pool(pool_dir, random.Random(0)) if a["near_dup_group"] == "A1")
    assert story["phase"] == "late"
    assert story["group_size"] == 3


def test_parse_locations_reads_the_pools_python_style_string():
    raw = "[{'name': 'Otago, Otago, New Zealand', 'country_fips': 'NZ', 'offset': 1555}]"
    assert parse_locations(raw) == [{"name": "Otago, Otago, New Zealand", "country_fips": "NZ", "offset": 1555}]
    assert parse_locations([{"name": "Belgian", "country_fips": "BE", "offset": 1361}])[0]["name"] == "Belgian"
    assert parse_locations("") == [] and parse_locations(None) == [] and parse_locations("not a list[") == []


def test_same_seed_gives_same_sample(pool_dir):
    def run(seed):
        rng = random.Random(seed)
        return [a["record_id"] for a in draw(add_buckets(read_pool(pool_dir, rng)), rng)]

    assert run(42) == run(42)


def test_sample_never_repeats_a_near_dup_group(pool_dir):
    rng = random.Random(1)
    sample = draw(add_buckets(read_pool(pool_dir, rng)), rng)
    groups = [a["near_dup_group"] for a in sample]
    assert len(groups) == len(set(groups))


def test_add_buckets_does_not_change_its_input(pool_dir):
    articles = read_pool(pool_dir, random.Random(0))
    before = [dict(a) for a in articles]
    bucketed = add_buckets(articles)
    assert articles == before
    assert all("bucket" in a and "reason" in a for a in bucketed)
