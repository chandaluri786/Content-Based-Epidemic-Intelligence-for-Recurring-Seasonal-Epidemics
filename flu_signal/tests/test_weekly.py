"""Offline tests of the weekly signals. Run from flu_signal/:

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import unittest
from datetime import date

import signal_config as cfg
from tables import parse_windows
from weekly import build_weekly, is_seasonal, item_signals, split_of, week_index

ONSET = date(2018, 12, 10)
WINDOWS = parse_windows([
    {"season_id": "USA-2018", "country": "USA", "season_year": 2018, "onset_date": "2018-12-10",
     "window_start": "2018-10-01", "window_end": "2018-12-24"},
    {"season_id": "IND-2023", "country": "IND", "season_year": 2023, "onset_date": "2023-01-23",
     "window_start": "2022-11-14", "window_end": "2023-02-06"},
])


def article(record_id: str, scan_date: str, frequency_seasons: str = "USA-2018") -> dict:
    return {"record_id": record_id, "scan_date": scan_date, "frequency_seasons": frequency_seasons}


def item(record_id: str, kind: str = "cases", words: str = "", strain: str = "", season_id: str = "USA-2018") -> dict:
    return {"record_id": record_id, "season_id": season_id, "kind": kind, "words": words, "strain": strain}


class WeekIndexTest(unittest.TestCase):
    def test_window_start_is_week_minus_10_and_onset_is_week_0(self):
        self.assertEqual(week_index(date(2018, 10, 1), ONSET), -10)
        self.assertEqual(week_index(ONSET, ONSET), 0)
        self.assertEqual(week_index(date(2018, 12, 9), ONSET), -1)

    def test_the_last_window_day_is_folded_into_week_plus_1(self):
        self.assertEqual(week_index(date(2018, 12, 23), ONSET), 1)
        self.assertEqual(week_index(date(2018, 12, 24), ONSET), 1)

    def test_a_date_outside_the_window_stops_the_run(self):
        with self.assertRaises(ValueError):
            week_index(date(2018, 9, 30), ONSET)
        with self.assertRaises(ValueError):
            week_index(date(2018, 12, 25), ONSET)


class ItemSignalTest(unittest.TestCase):
    def test_bird_flu_and_variant_strains_are_not_seasonal(self):
        for strain in ("H5N1", "avian influenza", "H7N9", "H9N2", "H3N2v", "H1N2v"):
            self.assertFalse(is_seasonal(strain), strain)
        for strain in ("", None, "H1N1", "H3N2", "influenza A", "influenza B"):
            self.assertTrue(is_seasonal(strain), strain)

    def test_a_bird_flu_item_counts_only_as_content_and_avian(self):
        self.assertEqual(item_signals(item("a", strain="H5N1")), {"content_articles", "avian_articles"})

    def test_counts_and_active_trends_are_activity_and_rising_trends_are_rising(self):
        self.assertIn("activity_articles", item_signals(item("a", "deaths")))
        self.assertIn("activity_articles", item_signals(item("a", "trend", "present")))
        self.assertEqual(item_signals(item("a", "trend", "rising")),
                         {"content_articles", "seasonal_articles", "activity_articles", "rising_articles"})

    def test_inactive_low_and_falling_trends_are_not_activity(self):
        for words in ("inactive", "low", "falling"):
            self.assertEqual(item_signals(item("a", "trend", words)), {"content_articles", "seasonal_articles"})


class SplitTest(unittest.TestCase):
    def test_seasons_from_2022_are_held_out(self):
        self.assertEqual(split_of(2021), cfg.SPLIT_CALIBRATION)
        self.assertEqual(split_of(2022), cfg.SPLIT_HELD_OUT)


class BuildWeeklyTest(unittest.TestCase):
    def test_every_season_gets_12_weeks_with_zeros_where_nothing_happened(self):
        rows = build_weekly([], [], WINDOWS)
        self.assertEqual(len(rows), 24)
        self.assertEqual([r["week"] for r in rows if r["season_id"] == "USA-2018"], list(range(-10, 2)))
        self.assertTrue(all(r["freq_articles"] == 0 for r in rows))

    def test_an_article_with_several_items_counts_once_per_signal(self):
        articles = [article("a", "2018-12-11"), article("b", "2018-12-12")]
        items = [item("a", "cases"), item("a", "deaths"), item("a", "trend", "rising"), item("a", strain="H5N1")]
        rows = {(r["season_id"], r["week"]): r for r in build_weekly(articles, items, WINDOWS)}
        week0 = rows[("USA-2018", 0)]
        self.assertEqual((week0["freq_articles"], week0["content_articles"], week0["seasonal_articles"],
                          week0["activity_articles"], week0["rising_articles"], week0["avian_articles"]),
                         (2, 1, 1, 1, 1, 1))

    def test_rows_carry_split_and_headline(self):
        rows = {r["season_id"]: r for r in build_weekly([], [], WINDOWS)}
        self.assertEqual((rows["USA-2018"]["split"], rows["USA-2018"]["headline"]), (cfg.SPLIT_CALIBRATION, True))
        self.assertEqual(rows["IND-2023"]["split"], cfg.SPLIT_HELD_OUT)


if __name__ == "__main__":
    unittest.main()
