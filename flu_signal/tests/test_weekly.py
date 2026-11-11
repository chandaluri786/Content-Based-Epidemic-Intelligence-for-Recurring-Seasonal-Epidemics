"""Offline tests of the weekly signals. Run from flu_signal/:

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import unittest
from datetime import date

import signal_config as cfg
from tables import parse_windows
from tables import Window
from weekly import build_weekly, is_seasonal, iso_week, item_signals, season_weeks, split_of, week_label

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


USA_2018 = WINDOWS["USA"][0]


class IsoWeekTest(unittest.TestCase):
    def test_iso_week_comes_from_the_date_alone(self):
        self.assertEqual(iso_week(date(2016, 2, 3)), "2016-W05")
        self.assertEqual(iso_week(date(2016, 1, 3)), "2015-W53")      # Sunday before 2016's first ISO week
        self.assertEqual(iso_week(date(2020, 12, 31)), "2020-W53")    # a 53-week year
        self.assertEqual(iso_week(date(2021, 1, 4)), "2021-W01")

    def test_window_weeks_are_labelled_against_the_onset_iso_week(self):
        labels = season_weeks(USA_2018)
        self.assertEqual(sorted(labels.values()), list(range(-10, 2)))
        self.assertEqual(labels[iso_week(date(2018, 10, 1))], -10)
        self.assertEqual(labels[iso_week(ONSET)], 0)
        self.assertEqual(labels[iso_week(date(2018, 12, 9))], -1)

    def test_weeks_across_new_year_and_a_53_week_year(self):
        window = Window("USA-2020", "USA", date(2021, 1, 4), date(2020, 10, 26), date(2021, 1, 18))
        labels = season_weeks(window)
        self.assertEqual(labels["2020-W53"], -1)
        self.assertEqual(labels["2021-W01"], 0)
        self.assertEqual(labels["2021-W02"], 1)

    def test_the_last_window_day_is_dropped_not_folded(self):
        labels = season_weeks(USA_2018)
        self.assertEqual(week_label(date(2018, 12, 23), USA_2018, labels), 1)
        self.assertIsNone(week_label(date(2018, 12, 24), USA_2018, labels))

    def test_a_date_outside_the_window_stops_the_run(self):
        labels = season_weeks(USA_2018)
        with self.assertRaises(ValueError):
            week_label(date(2018, 9, 30), USA_2018, labels)
        with self.assertRaises(ValueError):
            week_label(date(2018, 12, 25), USA_2018, labels)

    def test_a_window_without_12_whole_weeks_stops_the_run(self):
        short = Window("USA-2018", "USA", ONSET, date(2018, 10, 8), date(2018, 12, 24))
        with self.assertRaises(ValueError):
            season_weeks(short)


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
        rows, dropped = build_weekly([], [], WINDOWS)
        self.assertEqual(len(rows), 24)
        self.assertEqual(set(dropped.values()), {0})
        self.assertEqual([r["week"] for r in rows if r["season_id"] == "USA-2018"], list(range(-10, 2)))
        self.assertTrue(all(r["freq_articles"] == 0 for r in rows))

    def test_an_article_with_several_items_counts_once_per_signal(self):
        articles = [article("a", "2018-12-11"), article("b", "2018-12-12")]
        items = [item("a", "cases"), item("a", "deaths"), item("a", "trend", "rising"), item("a", strain="H5N1")]
        rows = {(r["season_id"], r["week"]): r for r in build_weekly(articles, items, WINDOWS)[0]}
        week0 = rows[("USA-2018", 0)]
        self.assertEqual((week0["freq_articles"], week0["content_articles"], week0["seasonal_articles"],
                          week0["activity_articles"], week0["rising_articles"], week0["avian_articles"]),
                         (2, 1, 1, 1, 1, 1))

    def test_rows_carry_split_and_headline(self):
        rows = {r["season_id"]: r for r in build_weekly([], [], WINDOWS)[0]}
        self.assertEqual((rows["USA-2018"]["split"], rows["USA-2018"]["headline"]), (cfg.SPLIT_CALIBRATION, True))
        self.assertEqual(rows["IND-2023"]["split"], cfg.SPLIT_HELD_OUT)

    def test_rows_carry_the_iso_week(self):
        rows = {(r["season_id"], r["week"]): r for r in build_weekly([], [], WINDOWS)[0]}
        self.assertEqual(rows[("USA-2018", 0)]["iso_week"], "2018-W50")
        self.assertEqual(rows[("IND-2023", -10)]["iso_week"], "2022-W46")

    def test_a_count_on_the_last_window_day_is_dropped_and_reported(self):
        articles = [article("a", "2018-12-23"), article("b", "2018-12-24")]
        rows, dropped = build_weekly(articles, [item("b")], WINDOWS)
        week1 = next(r for r in rows if (r["season_id"], r["week"]) == ("USA-2018", 1))
        self.assertEqual(week1["freq_articles"], 1)
        self.assertEqual((dropped["freq_articles"], dropped["content_articles"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
