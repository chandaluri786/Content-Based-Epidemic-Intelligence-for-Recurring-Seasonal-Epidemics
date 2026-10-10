"""
Unit tests for near-duplicate grouping (dataset_prep/near_dup.py).
No network. Run with: pytest
"""

import json
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_prep.near_dup import group_near_duplicates, run_near_dup, shingles, signature

_VOCAB = [f"word{i}" for i in range(2000)]


def _story(seed: int, n_words: int = 300) -> str:
    rng = random.Random(seed)
    return " ".join(rng.choice(_VOCAB) for _ in range(n_words))


def test_shingles_are_lowercased_five_word_windows():
    assert shingles("A b, C d e F") == {b"a b c d e", b"b c d e f"}


def test_signature_is_none_for_short_texts():
    assert signature("only a few words here") is None
    assert signature(_story(1)) is not None


def test_syndicated_copy_with_changed_byline_groups_with_the_original():
    original = _story(1)
    copy = "By Staff Reporter, Wire Service. " + original + " Copyright 2023 Wire Service."
    groups = group_near_duplicates([signature(original), signature(copy), signature(_story(2))])
    assert groups == [[0, 1], [2]]


def test_unrelated_and_short_texts_stay_singletons():
    groups = group_near_duplicates([signature(_story(1)), signature("too short"), signature(_story(3))])
    assert groups == [[0], [1], [2]]


def test_run_near_dup_writes_stable_group_ids_from_the_smallest_record_id():
    original = _story(7)
    rows = [
        {"gkg_record_id": "20230102-5", "url": "https://a.com/x", "article": original},
        {"gkg_record_id": "20230101-9", "url": "https://b.com/y", "article": "Updated: " + original},
        {"gkg_record_id": "20230103-1", "url": "https://c.com/z", "article": _story(8)},
    ]
    with tempfile.TemporaryDirectory() as d:
        pool = Path(d) / "pooled_articles.jsonl"
        pool.write_text("".join(json.dumps(r) + "\n" for r in rows))
        out = Path(d) / "near_dup_groups.jsonl"

        report = run_near_dup(pool, out)

        groups = {r["gkg_record_id"]: r for r in map(json.loads, out.read_text().splitlines())}
        assert groups["20230102-5"]["near_dup_group"] == "20230101-9"
        assert groups["20230101-9"]["near_dup_group"] == "20230101-9"
        assert groups["20230101-9"]["group_size"] == 2
        assert groups["20230103-1"]["near_dup_group"] == "20230103-1"
        assert report["articles"] == 3
        assert report["groups"] == 2
        assert report["articles_in_multi_member_groups"] == 2
        assert report["largest_groups"][0]["distinct_domains"] == 2
