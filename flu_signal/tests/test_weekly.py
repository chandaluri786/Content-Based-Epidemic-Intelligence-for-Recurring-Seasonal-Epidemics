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


# --- Item signals (COUNT_SIGNAL_RULES.md) -----------------------------------------------------------------------

from weekly import (CLOSED_BY_HIGHER_REGION, COVERED_OR_PARTIAL, INVALID, NEW_INSIDE_SUBSET, NULL_START,
                    REGION_NOT_USED, SAME_ARTICLE_GUARD, SPANS_WEEKS, USED, build_item_weekly, count_item,
                    country_week_values, flu_word_frequency, item_series, item_vintages, screen_item, week_monday,
                    week_value)

W06 = date(2015, 2, 2)          # Monday of ISO week 2015-W06
DAY = {name: W06.replace(day=2 + i) for i, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))}
_counter = iter(range(10_000))


def count_row(record_id: str, count_type: str, first: str, last: str | None = None, number: int = 1, *,
              country: str = "India", state: str = "", city: str = "", kind: str = "deaths",
              status: str = "confirmed", scan: str = "2015-02-08", code: str = "IND", start: str | None = None) -> dict:
    """One items.csv row. `first`/`last` are day names of 2015-W06 or ISO dates."""
    def iso(day: str) -> str:
        return DAY[day].isoformat() if day in DAY else day
    return {"record_id": record_id, "item_index": str(next(_counter)), "scan_date": scan, "item_country": code,
            "season_id": "", "kind": kind, "number": str(number), "count_type": count_type, "status": status,
            "strain": "", "city": city, "state": state, "country": country,
            "start_date": iso(first) if start is None else start, "end_date": iso(last or first), "words": ""}


def evaluate(rows: list[dict]):
    """(value, {label: decision}) for rows that all sit in one week; labels are each row's record_id + number."""
    items, labels = [], {}
    for row in rows:
        item, reason = count_item(row)
        if item is not None:
            items.append(item)
            labels[item.item_id] = row.get("label", row["record_id"])
    result = week_value(items, W06)
    return result, {labels[item_id]: decision for item_id, decision in result.decisions.items()}


WORKED_EXAMPLE = [  # COUNT_SIGNAL_RULES.md Section 8
    ("a", "A", "cumulative_region", "Mon", "Wed", 20, "", ""),
    ("b", "B", "new", "Fri", None, 1, "", ""),
    ("m", "K", "cumulative_subset", "Thu", "Sun", 7, "", ""),
    ("c", "C", "new", "Tue", None, 2, "Maharashtra", ""),
    ("d", "D", "cumulative_region", "Thu", "Sun", 9, "Maharashtra", ""),
    ("e", "E", "new", "Thu", None, 1, "Rajasthan", ""),
    ("f", "E", "cumulative_subset", "Sat", "Sun", 3, "Rajasthan", ""),
    ("g", "E", "new", "Sun", None, 1, "Rajasthan", ""),
    ("h", "F", "new", "Sat", None, 1, "Rajasthan", ""),
    ("i", "G", "new", "Sat", None, 2, "Rajasthan", "Jaipur"),
    ("j", "H", "cumulative_region", "Sat", "Sun", 2, "Telangana", ""),
    ("k", "H", "cumulative_region", "Sat", "Sun", 2, "Telangana", "Karimnagar"),
    ("l", "J", "new", "Thu", None, 2, "Gujarat", "Ahmedabad"),
    ("n", "K", "new", "Sat", None, 1, "Kerala", ""),
]


class WorkedExampleTest(unittest.TestCase):
    def test_india_2015_w06_is_48_with_the_documented_items_used_and_dropped(self):
        rows = [{**count_row(article, ctype, first, last, number, state=state, city=city), "label": label}
                for label, article, ctype, first, last, number, state, city in WORKED_EXAMPLE]
        result, decisions = evaluate(rows)
        self.assertEqual(result.value, 48)
        self.assertEqual({k for k, v in decisions.items() if v == USED}, set("abmdefhijl"))
        self.assertEqual({k: v for k, v in decisions.items() if v != USED},
                         {"c": CLOSED_BY_HIGHER_REGION, "g": NEW_INSIDE_SUBSET, "k": CLOSED_BY_HIGHER_REGION,
                          "n": SAME_ARTICLE_GUARD})

    def test_overlap_risk_counts_lower_place_days_under_higher_new_or_subset_items(self):
        rows = [{**count_row(article, ctype, first, last, number, state=state, city=city), "label": label}
                for label, article, ctype, first, last, number, state, city in WORKED_EXAMPLE]
        result, _ = evaluate(rows)
        # Maharashtra Thu-Sun (4), Rajasthan Thu, Sat, Sun (3), Jaipur Sat (1), Telangana Sat-Sun (2),
        # Ahmedabad Thu (1): all under India's subset m (article K).
        self.assertEqual(result.overlap_risk_place_days, 11)


class CountStageOneTest(unittest.TestCase):
    def test_a_period_across_two_iso_weeks_or_with_no_start_is_not_used(self):
        self.assertEqual(count_item(count_row("A", "cumulative_region", "2015-02-01", "Mon")), (None, SPANS_WEEKS))
        self.assertEqual(count_item(count_row("A", "cumulative_region", "Mon", "Sun", start="")), (None, NULL_START))

    def test_trend_items_are_not_counts(self):
        self.assertEqual(count_item({**count_row("A", "new", "Mon"), "kind": "trend"}), (None, None))

    def test_values_the_prompt_cannot_produce_stop_the_run(self):
        with self.assertRaises(ValueError):
            count_item(count_row("A", "running_total", "Mon"))
        with self.assertRaises(ValueError):
            count_item({**count_row("A", "new", "Mon"), "number": "2.5"})
        with self.assertRaises(ValueError):
            count_item(count_row("A", "new", "Mon", "Tue"))          # a new count is one day
        with self.assertRaises(ValueError):
            count_item(count_row("A", "new", "2015-02-31"))

    def test_a_bad_row_is_left_out_and_listed_without_stopping_the_run(self):
        item, reason, problem = screen_item({**count_row("A", "new", "Mon"), "number": ""})
        self.assertEqual((item, reason), (None, INVALID))
        self.assertIn("number", problem)
        rows = [count_row("1", "new", "2018-12-10", number=3, kind="cases", code="USA", scan="2018-12-10"),
                {**count_row("2", "new", "2018-12-10", kind="cases", code="USA", scan="2018-12-10"), "count_type": ""}]
        out = build_item_weekly([{**article("1", "2018-12-10"), "source": "llm"}], rows, WINDOWS)
        self.assertEqual([(i["record_id"], i["kind"]) for i in out["invalid_items"]], [("2", "cases")])
        self.assertEqual(out["report"]["cases_confirmed"]["decisions"], {INVALID: 1, USED: 1})


class CountRulesTest(unittest.TestCase):
    def test_region_totals_on_separate_days_are_added(self):
        result, _ = evaluate([count_row("A", "cumulative_region", "Mon", "Wed", 6),
                              count_row("B", "cumulative_region", "Thu", "Sun", 4)])
        self.assertEqual(result.value, 10)

    def test_a_copy_of_a_complete_total_counts_once(self):
        result, decisions = evaluate([count_row("A", "cumulative_region", "Mon", "Sun", 9),
                                      count_row("B", "cumulative_region", "Mon", "Sun", 9)])
        self.assertEqual(result.value, 9)
        self.assertEqual(sorted(decisions.values()), [REGION_NOT_USED, USED])

    def test_copies_of_new_counts_in_different_articles_are_both_added(self):
        result, _ = evaluate([count_row("A", "new", "Mon", number=2, state="Kerala"),
                              count_row("B", "new", "Mon", number=2, state="Kerala")])
        self.assertEqual(result.value, 4)

    def test_a_subset_partly_on_region_days_is_dropped(self):
        result, decisions = evaluate([count_row("A", "cumulative_region", "Mon", "Wed", 6, state="Kerala"),
                                      count_row("B", "cumulative_subset", "Wed", "Fri", 4, state="Kerala"),
                                      count_row("C", "cumulative_subset", "Thu", "Fri", 3, state="Kerala")])
        self.assertEqual(result.value, 9)
        self.assertEqual(decisions["B"], COVERED_OR_PARTIAL)

    def test_a_country_region_for_the_whole_week_is_final(self):
        result, decisions = evaluate([count_row("A", "cumulative_region", "Mon", "Sun", 30),
                                      count_row("B", "new", "Tue", number=5, state="Kerala"),
                                      count_row("C", "cumulative_region", "Mon", "Sun", 12, state="Kerala")])
        self.assertEqual(result.value, 30)
        self.assertEqual((decisions["B"], decisions["C"]), (CLOSED_BY_HIGHER_REGION, CLOSED_BY_HIGHER_REGION))

    def test_new_and_subset_do_not_close_days_but_guard_their_own_article(self):
        result, decisions = evaluate([{**count_row("A", "new", "Tue", number=3), "label": "india"},
                                      {**count_row("A", "new", "Tue", number=2, state="Kerala"), "label": "same"},
                                      {**count_row("B", "new", "Tue", number=4, state="Kerala"), "label": "other"}])
        self.assertEqual(result.value, 7)
        self.assertEqual(decisions, {"india": USED, "same": SAME_ARTICLE_GUARD, "other": USED})

    def test_a_city_with_no_state_is_a_child_of_its_country(self):
        result, _ = evaluate([count_row("A", "new", "Mon", number=1),
                              count_row("B", "new", "Mon", number=2, city="Delhi")])
        self.assertEqual(result.value, 3)
        result, decisions = evaluate([count_row("A", "cumulative_region", "Mon", "Sun", 10),
                                      count_row("B", "new", "Mon", number=2, city="Delhi")])
        self.assertEqual((result.value, decisions["B"]), (10, CLOSED_BY_HIGHER_REGION))

    def test_confirmed_and_suspected_never_affect_each_other(self):
        items = [count_item(row)[0] for row in (count_row("A", "cumulative_region", "Mon", "Sun", 10),
                                                count_row("B", "new", "Mon", number=2, status="suspected"))]
        values = country_week_values(items)
        self.assertEqual(values[("IND", "deaths", "confirmed", W06)].value, 10)
        self.assertEqual(values[("IND", "deaths", "suspected", W06)].value, 2)


IND_2015 = parse_windows([{"season_id": "IND-2015", "country": "IND", "season_year": 2015, "onset_date": "2015-03-02",
                           "window_start": "2014-12-22", "window_end": "2015-03-16"}])["IND"][0]


class ItemSeriesTest(unittest.TestCase):
    def test_season_weeks_are_iso_weeks_from_the_monday_onset(self):
        self.assertEqual(week_monday(IND_2015, 0), date(2015, 3, 2))
        self.assertEqual(week_monday(IND_2015, -4), W06)
        with self.assertRaises(ValueError):
            week_monday(parse_windows([{**{"season_id": "X-2015", "country": "X", "onset_date": "2015-03-03",
                                           "window_start": "2014-12-23", "window_end": "2015-03-17"}}])["X"][0], 0)

    def test_an_item_counts_in_its_event_week_and_only_in_its_country(self):
        items = [count_item(count_row("A", "new", "Tue", number=4, kind="cases"))[0],
                 count_item(count_row("B", "new", "Tue", number=9, kind="cases", code="USA"))[0]]
        series = item_series(items, IND_2015)
        self.assertEqual(series["cases_confirmed"][-4 - cfg.FIRST_WEEK], 4)
        self.assertEqual(sum(series["cases_confirmed"]), 4)
        self.assertEqual(set(series), set(cfg.ITEM_SERIES))

    def test_the_replay_never_shows_an_item_before_its_scan_date(self):
        # An event in week -4 (2015-W06) reported in an article scanned in week -2.
        items = [count_item(count_row("A", "new", "Tue", number=5, kind="cases", scan="2015-02-18"))[0]]
        vintages = item_vintages(items, IND_2015)["cases_confirmed"]
        as_of = {week: vintages[week - cfg.FIRST_WEEK] for week in range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1)}
        self.assertEqual(as_of[-3][-4 - cfg.FIRST_WEEK], 0)       # week -3 ends 2015-02-15: not yet published
        self.assertEqual(as_of[-2][-4 - cfg.FIRST_WEEK], 5)       # week -2 ends 2015-02-22: now known
        self.assertEqual(as_of[cfg.LAST_WEEK], item_series(items, IND_2015)["cases_confirmed"])

    def test_the_flu_word_baseline_leaves_out_articles_the_keyword_filter_dropped(self):
        articles = [{**article("1", "2018-12-10"), "source": "llm"},
                    {**article("2", "2018-12-11"), "source": cfg.SOURCE_NOT_SENT}]
        self.assertEqual(flu_word_frequency(articles, WINDOWS)[("USA-2018", 0)], 1)

    def test_the_flu_word_baseline_uses_the_same_strict_iso_weeks_as_freq_articles(self):
        articles = [{**article("1", "2018-12-23"), "source": "llm"},      # Sunday: week +1
                    {**article("2", "2018-12-24"), "source": "llm"}]      # lone last Monday: dropped
        counts = flu_word_frequency(articles, WINDOWS)
        self.assertEqual(counts[("USA-2018", 1)], 1)
        self.assertEqual(sum(counts.values()), 1)
        rows, _ = build_weekly(articles, [], WINDOWS)
        self.assertEqual(sum(row["freq_articles"] for row in rows), 1)

    def test_build_item_weekly_writes_every_season_week_and_vintage(self):
        articles = [{**article("1", "2018-12-10"), "source": "llm"}]
        rows = [count_row("1", "new", "2018-12-10", number=3, kind="cases", country="United States",
                          code="USA", scan="2018-12-10")]
        out = build_item_weekly(articles, rows, WINDOWS)
        weeks = cfg.LAST_WEEK - cfg.FIRST_WEEK + 1
        self.assertEqual(len(out["weekly_rows"]), 2 * weeks)
        self.assertEqual(len(out["vintage_rows"]), 2 * weeks * weeks * len(cfg.ITEM_SERIES))
        week0 = next(r for r in out["weekly_rows"] if r["season_id"] == "USA-2018" and r["week"] == 0)
        self.assertEqual((week0["cases_confirmed"], week0[cfg.FLU_WORD_FREQUENCY_SIGNAL]), (3, 1))
        self.assertEqual(out["count_rows"][0]["iso_week"], "2018-W50")
        self.assertEqual(out["report"]["cases_confirmed"]["decisions"], {USED: 1})


if __name__ == "__main__":
    unittest.main()
