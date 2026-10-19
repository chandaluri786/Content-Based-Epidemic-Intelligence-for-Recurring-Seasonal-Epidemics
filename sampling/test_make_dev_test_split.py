"""Tests for the dev/test split (make_dev_test_split.py).

Uses a made-up 1,200-article sample with the real useful share (26%). Run from the repo root with: pytest sampling/
"""
import csv
import random
from collections import Counter

import pytest

from make_dev_test_split import (LABELERS, article_tags, item_tags, load_answers, make_split, story_groups,
                                 tag_minimums)

BUCKETS = ["P_A1_counts", "P_B_trend_response", "N_awareness", "N_animal_flu", "N_other_flu_mention"]
COUNTRIES = ["USA", "IND", "AUS"]
ITEM_FIELDS = ["article_id", "strain", "kind", "number", "status", "total_or_new", "city", "state", "country",
               "start_date", "end_date", "words", "evidence"]


def item(article_id: str, **fields) -> dict:
    base = {f: "" for f in ITEM_FIELDS}
    return {**base, "article_id": article_id, "kind": "trend", "country": "USA", "end_date": "2020-03-01",
            "words": "rising", "evidence": f"Flu is rising in story {article_id}.", **fields}


@pytest.fixture
def labeled():
    """1,200 articles: 312 useful, spread over buckets, countries and labelers, with unique texts."""
    rng = random.Random(0)
    sample, answers = [], {}
    useful_ids = set(rng.sample(range(1200), 312))
    for n in range(1200):
        a = f"a{n:04d}"
        useful = "yes" if n in useful_ids else "no"
        sample.append({"record_id": a, "bucket": BUCKETS[n % len(BUCKETS)], "country": COUNTRIES[n % 3],
                       "year": "2020", "text": " ".join(f"w{n}x{k}" for k in range(40))})
        answers[a] = {"labeler": LABELERS[n % 4], "useful": useful, "notes": "",
                      "items": [item(a)] if useful == "yes" else []}
    return sample, answers


def counts(result: dict, answers: dict) -> Counter:
    return Counter((s, answers[a]["useful"]) for a, s in result["split"].items())


def test_same_seed_gives_the_same_split(labeled):
    sample, answers = labeled
    assert make_split(sample, answers, seed=42)["split"] == make_split(sample, answers, seed=42)["split"]


def test_dev_is_a_third_and_keeps_the_natural_useful_share(labeled):
    sample, answers = labeled
    c = counts(make_split(sample, answers, seed=42), answers)
    dev, test = c["dev", "yes"] + c["dev", "no"], c["test", "yes"] + c["test", "no"]
    assert abs(dev - 400) <= 5 and dev + test == 1200
    assert abs(c["dev", "yes"] / dev - 312 / 1200) <= 0.01
    assert abs(c["test", "yes"] / test - 312 / 1200) <= 0.01


def test_every_labeler_and_bucket_is_in_both_sets(labeled):
    sample, answers = labeled
    split = make_split(sample, answers, seed=42)["split"]
    rows = {r["record_id"]: r for r in sample}
    for side in ("dev", "test"):
        ids = [a for a, s in split.items() if s == side]
        assert {answers[a]["labeler"] for a in ids} == set(LABELERS)
        assert {rows[a]["bucket"] for a in ids} == set(BUCKETS)


def test_copies_of_one_story_land_in_the_same_set(labeled):
    sample, answers = labeled
    shared = " ".join(f"same story word {k}" for k in range(60))
    for r in sample[:6]:
        r["text"] = shared
    result = make_split(sample, answers, seed=42)
    assert len({result["split"][r["record_id"]] for r in sample[:6]}) == 1


def test_one_figure_reported_twice_joins_the_articles():
    answers = {a: {"items": [item(a, kind="cases", number="142", state="Maharashtra", country="India",
                                  end_date=end, evidence=f"Story {a} says 142 cases.")]}
               for a, end in (("a", "2022-07-22"), ("b", "2022-07-23"), ("c", "2022-09-01"))}
    groups = story_groups({"a": "one text here", "b": "another text", "c": "third text"}, answers)
    assert groups["a"] == groups["b"] != groups["c"]


def test_rare_rule_gets_its_dev_minimum(labeled):
    sample, answers = labeled
    useful = [a for a in sorted(answers) if answers[a]["useful"] == "yes"]
    for a in useful[:4]:
        answers[a]["items"] = [item(a, city="Hong Kong", country="China")]
    result = make_split(sample, answers, seed=7)
    dev_with_tag = [a for a in useful[:4] if result["split"][a] == "dev"]
    assert len(dev_with_tag) >= tag_minimums(result["tags_of"])["place:territory"] == 2
    assert "place:territory" not in result["unmet"]
    c = counts(result, answers)
    assert abs(c["dev", "yes"] + c["dev", "no"] - 400) <= 5


def test_item_tags_read_counts_dates_and_places():
    items = [item("x", kind="deaths", number="1", total_or_new="new", start_date="2020-03-01",
                  evidence="A man died on Tuesday."),
             item("x", kind="deaths", number="120", total_or_new="total", start_date="",
                  evidence="The toll since January is 120, compared with 80 last year."),
             item("x", kind="trend", words="86% were H1N1", country="India",
                  evidence="86 per cent of samples were H1N1.")]
    tags = item_tags(items)
    assert {"count:new_and_total", "count:open_total", "date:weekday", "date:since",
            "count:comparison_nearby", "trend:strain_share", "trend:percentage",
            "place:several_countries"} <= tags


def test_not_useful_articles_are_tagged_by_bucket_and_note():
    answer = {"useful": "no", "notes": "useful changed to no: its only item was a forecast", "items": []}
    assert article_tags(answer, "P_B_trend_response") >= {"no:P_B_trend_response", "no:word_rules_said_useful",
                                                          "note:forecast"}


def write_rows(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def test_load_answers_uses_owner_rows_and_reports_check_disagreements(tmp_path):
    label_fields = ["row", "round", "article_id", "link", "scan_date", "useful", "causes", "labeler", "notes"]
    for n, name in enumerate(LABELERS):
        own = f"own{n}"
        partner = f"own{(n + 1) % 4}"
        write_rows(tmp_path / f"{name}_labels.csv", label_fields, [
            {"row": 1, "round": "1-own", "article_id": own, "useful": "yes", "labeler": name},
            {"row": 2, "round": f"1-check-x", "article_id": partner, "useful": "no" if n == 0 else "yes",
             "labeler": name}])
        write_rows(tmp_path / f"{name}_items.csv", ITEM_FIELDS, [item(own), item(partner)])
    answers, disagreements = load_answers(tmp_path)
    assert set(answers) == {"own0", "own1", "own2", "own3"}
    assert all(len(a["items"]) == 1 for a in answers.values())
    assert disagreements == [{"article_id": "own1", "checker": "Jahnavi", "useful": "no",
                              "owner": "Thanya", "owner_useful": "yes"}]
