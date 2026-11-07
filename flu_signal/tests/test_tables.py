"""Offline tests of the article and item tables. Run from flu_signal/:

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import unittest
from datetime import date

import signal_config as cfg
from tables import article_answer, build_tables, item_rows, parse_windows, season_for

RAW_WINDOWS = [
    {"season_id": "USA-2018", "country": "USA", "season_year": 2018, "onset_date": "2018-12-10",
     "window_start": "2018-10-01", "window_end": "2018-12-24"},
    {"season_id": "IND-2018", "country": "IND", "season_year": 2018, "onset_date": "2018-08-27",
     "window_start": "2018-06-18", "window_end": "2018-09-10"},
]
WINDOWS = parse_windows(RAW_WINDOWS)


def item(country: str | None, kind: str = "cases") -> dict:
    return {"kind": kind, "number": 5, "country": country, "state": None, "evidence": ["..."]}


def bucket(record_id: str, scan_date: str = "2018-12-01", country: str = "USA") -> dict:
    return {"record_id": record_id, "scan_date": scan_date, "country": country, "season": f"{country}-2018",
            "phase": "late", "bucket": "N_x", "group_size": "1"}


class WindowTest(unittest.TestCase):
    def test_both_window_ends_are_included(self):
        self.assertEqual(season_for("USA", date(2018, 10, 1), WINDOWS), "USA-2018")
        self.assertEqual(season_for("USA", date(2018, 12, 24), WINDOWS), "USA-2018")
        self.assertIsNone(season_for("USA", date(2018, 12, 25), WINDOWS))

    def test_a_country_without_windows_has_no_season(self):
        self.assertIsNone(season_for("KEN", date(2018, 12, 1), WINDOWS))

    def test_overlapping_windows_of_one_country_are_refused(self):
        overlap = RAW_WINDOWS + [{**RAW_WINDOWS[0], "season_id": "USA-2019", "window_start": "2018-12-20",
                                  "window_end": "2019-02-01"}]
        with self.assertRaises(ValueError):
            parse_windows(overlap)


class AnswerTest(unittest.TestCase):
    def test_gold_wins_over_an_llm_reply(self):
        gold = {"a": {"useful": True, "items": [], "status": "gold"}}
        llm = {"a": {"useful": False, "items": [], "status": "valid"}}
        self.assertEqual(article_answer("a", gold, llm, None)[0], cfg.SOURCE_GOLD)

    def test_a_dropped_article_is_not_useful(self):
        source, answer = article_answer("a", {}, {}, cfg.DROPPED_LAYER)
        self.assertEqual((source, answer["useful"], answer["items"]), (cfg.SOURCE_NOT_SENT, False, []))

    def test_an_article_with_no_answer_that_was_not_dropped_stops_the_run(self):
        with self.assertRaises(ValueError):
            article_answer("a", {}, {}, "has_flu_word")


class ItemRowsTest(unittest.TestCase):
    def test_each_item_counts_toward_its_own_country(self):
        # An Indian article dated inside both windows, with one Indian and one US item.
        skipped: dict[str, int] = {}
        rows = item_rows("a", date(2018, 9, 5), [item("India"), item("United States")], {
            **WINDOWS, "USA": parse_windows([{**RAW_WINDOWS[0], "window_start": "2018-09-01"}])["USA"]}, skipped)
        self.assertEqual([(r["item_country"], r["season_id"]) for r in rows], [("IND", "IND-2018"), ("USA", "USA-2018")])
        self.assertEqual(skipped, {})

    def test_items_about_other_countries_or_outside_the_window_are_skipped(self):
        skipped: dict[str, int] = {}
        rows = item_rows("a", date(2018, 12, 1), [item("Mexico"), item(None), item("India"), item("United States")],
                         WINDOWS, skipped)
        self.assertEqual([r["item_index"] for r in rows], [3])
        self.assertEqual(skipped, {"not_cohort_country": 2, "outside_country_window": 1})


class BuildTablesTest(unittest.TestCase):
    def test_frequency_uses_every_mentioned_season_and_content_uses_item_countries(self):
        buckets = [bucket("a"), bucket("b"), bucket("c")]
        assignments = {"a": ["USA-2018", "IND-2018"], "b": ["USA-2018"], "c": ["USA-2018"]}
        gold = {"a": {"useful": True, "items": [item("United States")], "status": "gold"}}
        llm = {"b": {"useful": False, "items": [], "status": "valid"}}
        articles, items, report = build_tables(buckets, {"c": cfg.DROPPED_LAYER}, assignments, gold, llm, WINDOWS)
        self.assertEqual([(r["source"], r["frequency_seasons"], r["content_seasons"]) for r in articles],
                         [("gold", "USA-2018;IND-2018", "USA-2018"), ("llm", "USA-2018", ""), ("not_sent", "USA-2018", "")])
        self.assertEqual(len(items), 1)
        self.assertEqual(report["by_source"], {"gold": 1, "llm": 1, "not_sent": 1})

    def test_an_article_missing_from_the_assignments_stops_the_run(self):
        with self.assertRaises(ValueError):
            build_tables([bucket("a")], {}, {}, {"a": {"useful": False, "items": [], "status": "gold"}}, {}, WINDOWS)

    def test_an_llm_reply_for_an_article_outside_the_pool_stops_the_run(self):
        llm = {"a": {"useful": False, "items": [], "status": "valid"},
               "zz": {"useful": False, "items": [], "status": "valid"}}
        with self.assertRaises(ValueError):
            build_tables([bucket("a")], {}, {"a": ["USA-2018"]}, {}, llm, WINDOWS)


if __name__ == "__main__":
    unittest.main()
