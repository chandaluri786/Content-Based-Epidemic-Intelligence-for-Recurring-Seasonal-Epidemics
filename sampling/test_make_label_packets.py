"""Tests for splitting the sample into labeler packets (make_label_packets.py).

Uses a made-up 1,200-article sample with the real bucket quotas. Run from the repo root with: pytest sampling/
"""
import csv
from collections import Counter

import pytest

from make_label_packets import (LABELERS, PILOT_PER_SIDE, assignment_key, checker_of, likely_useful,
                                make_packets, packet_rows, partner_of, write_packet)
from run_sampling import QUOTAS

BUCKETS = {**{b: n for b, n in QUOTAS.items() if b != "JUNK"},
           "X_too_short": 17, "X_spam_stub": 4, "X_listing_garbled": 4}


@pytest.fixture
def sample():
    return [{"record_id": f"{bucket}-{i}", "url": f"https://x.com/{bucket}/{i}", "scan_date": "2020-03-01",
             "bucket": bucket, "text": f"article {i} in {bucket}"}
            for bucket, n in BUCKETS.items() for i in range(n)]


def test_every_article_goes_to_exactly_one_labeler(sample):
    packets, _ = make_packets(sample, seed=42)
    ids = [r["record_id"] for name in LABELERS for r in packets[name]]
    assert sorted(ids) == sorted(r["record_id"] for r in sample)


def test_packets_are_even_in_size_and_mix(sample):
    packets, _ = make_packets(sample, seed=42)
    for name in LABELERS:
        assert len(packets[name]) == 300
        assert abs(sum(likely_useful(r["bucket"]) for r in packets[name]) - 150) <= 2
        for bucket, n in Counter(r["bucket"] for r in packets[name]).items():
            assert abs(n - BUCKETS[bucket] / len(LABELERS)) <= 1


def test_round_one_is_half_likely_useful_and_spread_over_buckets(sample):
    packets, pilots = make_packets(sample, seed=42)
    for name in LABELERS:
        pilot = pilots[name]
        assert len(pilot) == 2 * PILOT_PER_SIDE
        assert sum(likely_useful(r["bucket"]) for r in pilot) == PILOT_PER_SIDE
        assert len({r["bucket"] for r in pilot}) >= 12
        assert {r["record_id"] for r in pilot} <= {r["record_id"] for r in packets[name]}


def test_check_rotation_covers_everyone_once():
    assert [partner_of(n) for n in LABELERS] == LABELERS[1:] + LABELERS[:1]
    assert all(checker_of(partner_of(n)) == n for n in LABELERS)


def test_sheet_order_is_own_pilot_then_partner_pilot_then_rest(sample):
    packets, pilots = make_packets(sample, seed=42)
    rows = packet_rows("Jahnavi", packets, pilots)
    rounds = [rnd for rnd, _ in rows]
    assert rounds == ["1-own"] * 20 + ["1-check-Thanya"] * 20 + ["2"] * 280
    assert [r for _, r in rows[20:40]] == pilots["Thanya"]


def test_key_marks_pilots_and_their_checker(sample):
    packets, pilots = make_packets(sample, seed=42)
    key = assignment_key(packets, pilots)
    pilot_rows = [k for k in key if k["pilot"]]
    assert len(key) == 1200 and len(pilot_rows) == 80
    assert all(k["checked_by"] == checker_of(k["owner"]) for k in pilot_rows)
    assert all(k["checked_by"] == "" for k in key if not k["pilot"])


def test_same_seed_gives_same_packets(sample):
    assert make_packets(sample, seed=42) == make_packets(sample, seed=42)
    assert make_packets(sample, seed=42) != make_packets(sample, seed=7)


def test_written_label_sheet_has_no_bucket_and_blank_labels(sample, tmp_path):
    packets, pilots = make_packets(sample, seed=42)
    write_packet(tmp_path, "Manoj", packet_rows("Manoj", packets, pilots))
    with open(tmp_path / "Manoj_labels.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 320 and "bucket" not in rows[0]  # 20 own + 20 partner's + 280 round 2
    assert all(r["labeler"] == "Manoj" and r["useful"] == "" for r in rows)
    assert (tmp_path / "Manoj_items.csv").read_text(encoding="utf-8-sig").startswith("article_id,kind,")
    assert "#1  [1-own]" in (tmp_path / "Manoj_texts.txt").read_text(encoding="utf-8")
