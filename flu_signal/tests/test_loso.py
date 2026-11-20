"""Offline tests of the leave-one-season-out check, on made-up seasons only.

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import unittest

from scoring import Setting
from loso import fold

GOOD = Setting("rising_articles", "bcp_prospective", 0.4, 1, 0.0)
BAD = Setting("rising_articles", "bocpd_prospective", 0.4, 1, 0.0)
FREQ = Setting("freq_articles", "bocpd_prospective", 0.4, 1, 0.0)
SEASONS = {season_id: {"country": season_id[:3], "headline": True} for season_id in ("USA-2018", "USA-2019", "USA-2023")}


class FoldTest(unittest.TestCase):
    def test_the_left_out_season_never_takes_part_in_the_tuning(self):
        # GOOD hits both training seasons and misses USA-2023; BAD misses the training seasons and hits USA-2023.
        # GOOD is chosen and scored on USA-2023 as a miss: the left-out season's own result played no part.
        weeks = {GOOD: {"USA-2018": -1, "USA-2019": 0, "USA-2023": None},
                 BAD: {"USA-2018": None, "USA-2019": None, "USA-2023": -3},
                 FREQ: {"USA-2018": 0, "USA-2019": 1, "USA-2023": 0}}
        row = fold("USA-2023", weeks, SEASONS)
        self.assertTrue(row["content_setting"].startswith("rising_articles bcp_prospective"))
        self.assertEqual(row["trained_on"], 2)
        self.assertEqual((row["content_alarm_week"], row["frequency_alarm_week"], row["winner"]), (None, 0, "frequency"))

    def test_leaving_out_a_different_season_can_change_the_choice(self):
        weeks = {GOOD: {"USA-2018": -1, "USA-2019": None, "USA-2023": None},
                 BAD: {"USA-2018": None, "USA-2019": -2, "USA-2023": -3},
                 FREQ: {"USA-2018": 0, "USA-2019": 1, "USA-2023": 0}}
        # Trained on USA-2019 and USA-2023, BAD has 2 hits to GOOD's 0, so BAD is chosen, then scored on
        # USA-2018, where it misses.
        row = fold("USA-2018", weeks, SEASONS)
        self.assertTrue(row["content_setting"].startswith("rising_articles bocpd_prospective"))
        self.assertIsNone(row["content_alarm_week"])


# --- Item signals (COMBINED_SIGNAL_RULES.md) --------------------------------------------------------------------

import random
from datetime import date, timedelta

import signal_config as cfg
from loso import (BASELINES, CANDIDATES, ITEM_ONSET, ITEM_ONSET_NO_SUSPICION, calendar_alarm_weeks, calendar_reference,
                  decision, grade_rows, item_alarm_weeks, item_folds, item_grid, item_seasons, items_summary, realtime_alarm)
from run_detectors import METHODS, SELECTABLE_METHODS, to_week
from tables import parse_windows
from weekly import build_item_weekly, build_weekly

WEEKS = cfg.LAST_WEEK - cfg.FIRST_WEEK + 1


class RealtimeAlarmTest(unittest.TestCase):
    def test_on_a_series_that_is_never_revised_it_is_the_detectors_own_prospective_alarm(self):
        rng = random.Random(7)
        for _ in range(12):
            rise = rng.randrange(3, 11)
            series = [rng.randrange(0, 4) + (rng.randrange(4, 12) if i >= rise else 0) for i in range(WEEKS)]
            for method in SELECTABLE_METHODS:
                for cutoff in (0.3, 0.5, 0.7):
                    for sustain in (1, 2, 3):
                        expected = to_week(METHODS[method](series, cutoff, sustain, 0.0).alarm_index)
                        self.assertEqual(realtime_alarm(method, [series] * WEEKS, cutoff, sustain), expected,
                                         f"{method} {cutoff} {sustain} {series}")

    def test_a_rise_reported_late_cannot_raise_an_alarm_before_it_is_published(self):
        quiet = [1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0]
        revised = [1, 0, 1, 1, 9, 12, 14, 15, 15, 16, 15, 14]      # the rise from position 4 is only published at 9
        vintages = [quiet] * 9 + [revised] * 3
        for method in SELECTABLE_METHODS:
            week = realtime_alarm(method, vintages, 0.3, 1)
            self.assertIsNotNone(week)
            self.assertGreaterEqual(week, to_week(9))


def onset_monday(year: int) -> date:
    first = date(year, 12, 1)
    return first + timedelta(days=(7 - first.weekday()) % 7)


def made_up_tables(years=(2016, 2017, 2018)):
    """Small step 1 tables for some USA seasons: flat flu articles, and confirmed cases that rise from week -3."""
    raw_windows, articles, items = [], [], []
    for year in years:
        onset = onset_monday(year)
        raw_windows.append({"season_id": f"USA-{year}", "country": "USA", "season_year": year,
                            "onset_date": onset.isoformat(), "window_start": (onset - timedelta(days=70)).isoformat(),
                            "window_end": (onset + timedelta(days=14)).isoformat()})
        for week in range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1):
            day = onset + timedelta(days=7 * week + 2)
            for n in range(5 + (3 if week >= -2 else 0)):
                record_id = f"{year}-{week}-{n}"
                articles.append({"record_id": record_id, "scan_date": day.isoformat(), "source": "llm",
                                 "frequency_seasons": f"USA-{year}"})
            number = 1 if week < -3 else 10 + 3 * (week + 3)
            items.append({"record_id": f"{year}-{week}-0", "item_index": "0", "scan_date": day.isoformat(),
                          "item_country": "USA", "season_id": f"USA-{year}", "kind": "cases", "number": str(number),
                          "count_type": "new", "status": "confirmed", "strain": "", "city": "", "state": "Texas",
                          "country": "United States", "start_date": day.isoformat(), "end_date": day.isoformat(),
                          "words": ""})
    return parse_windows(raw_windows), articles, items


def as_csv_rows(rows: list[dict]) -> list[dict]:
    return [{key: str(value) for key, value in row.items()} for row in rows]


class ItemExperimentTest(unittest.TestCase):
    def test_item_onset_is_the_earliest_series_alarm_and_the_chain_runs_end_to_end(self):
        windows, articles, items = made_up_tables()
        weekly_rows = as_csv_rows(build_weekly(articles, items, windows)[0])
        out = build_item_weekly(items, windows)
        seasons = item_seasons(weekly_rows, as_csv_rows(out["weekly_rows"]), as_csv_rows(out["vintage_rows"]))
        weeks = item_alarm_weeks(seasons)
        for setting in item_grid((ITEM_ONSET,)):
            for season_id in seasons:
                series = [weeks[Setting(s, setting.method, setting.cutoff, setting.sustain_weeks, setting.margin)][season_id]
                          for s in cfg.ITEM_SERIES]
                self.assertEqual(weeks[setting][season_id], min((w for w in series if w is not None), default=None))
        # No suspicion series has data here, so leaving them out changes nothing.
        for setting in item_grid((ITEM_ONSET,)):
            same = Setting(ITEM_ONSET_NO_SUSPICION, setting.method, setting.cutoff, setting.sustain_weeks, setting.margin)
            self.assertEqual(weeks[same], weeks[setting])
        rows = item_folds(weeks, seasons, cfg.EARLY_LIMIT)
        self.assertEqual(len(rows), len(seasons) * len(BASELINES) * len(CANDIDATES))
        summary = items_summary(rows)
        self.assertTrue(summary["post_hoc"])
        main = next(c for c in summary["comparisons"]
                    if (c["candidate"], c["baseline"]) == (ITEM_ONSET, "freq_articles"))
        self.assertEqual(main["content"]["hits"], len(seasons))         # cases rise from week -3 in every season
        triggers = grade_rows(weeks, rows)
        self.assertEqual({t["triggered_by"] for t in triggers}, {"cases_confirmed"})
        self.assertEqual({t["grade_at_alarm"] for t in triggers}, {cfg.ITEM_GRADES["cases_confirmed"]})


class StaleItemFilesTest(unittest.TestCase):
    def test_item_files_older_than_the_weekly_signals_are_reported_clearly(self):
        windows, articles, items = made_up_tables()
        weekly_rows = as_csv_rows(build_weekly(articles, items, windows)[0])
        older = dict(windows, USA=windows["USA"][:2])                  # item files built before one more season
        out = build_item_weekly(items, older)
        with self.assertRaisesRegex(ValueError, "run build_weekly.py again"):
            item_seasons(weekly_rows, as_csv_rows(out["weekly_rows"]), as_csv_rows(out["vintage_rows"]))


class ItemFoldTest(unittest.TestCase):
    def test_the_left_out_season_never_takes_part_in_choosing_the_item_onset_setting(self):
        good = Setting(ITEM_ONSET, "bcp_prospective", 0.4, 1, 0.0)
        bad = Setting(ITEM_ONSET, "bocpd_prospective", 0.4, 1, 0.0)
        weeks = {good: {"USA-2018": -1, "USA-2019": 0, "USA-2023": None},
                 bad: {"USA-2018": None, "USA-2019": None, "USA-2023": -3}}
        for signal in (*BASELINES, *CANDIDATES):
            if signal != ITEM_ONSET:
                weeks[Setting(signal, "bocpd_prospective", 0.4, 1, 0.0)] = {"USA-2018": 0, "USA-2019": 1, "USA-2023": 0}
        rows = [r for r in item_folds(weeks, SEASONS, cfg.EARLY_LIMIT)
                if r["season_id"] == "USA-2023" and r["candidate"] == ITEM_ONSET and r["baseline"] == "freq_articles"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["candidate_setting"].startswith(f"{ITEM_ONSET} bcp_prospective"))
        self.assertIsNone(rows[0]["content_alarm_week"])

    def test_decision_needs_both_conditions_for_better_and_neither_for_not_better(self):
        def summary(score, base, wins, losses):
            return {"content": {"score": score}, "frequency": {"score": base}, "content_wins": wins,
                    "frequency_wins": losses}
        self.assertEqual(decision(summary(5, 3, 8, 4)), "better")
        self.assertEqual(decision(summary(2, 3, 4, 8)), "not better")
        self.assertEqual(decision(summary(5, 3, 4, 8)), "mixed")

    def test_the_grade_is_the_most_serious_series_alarmed_so_far(self):
        setting = ("bcp_prospective", 0.5, 1, 0.0)
        alarms = {"cases_suspected": -6, "hospitalized_suspected": None, "cases_confirmed": -4,
                  "hospitalized_confirmed": -3, "deaths_confirmed": -2}
        weeks = {Setting(s, *setting): {"IND-2015": w} for s, w in alarms.items()}
        row = {"season_id": "IND-2015", "country": "IND", "early_limit_week": -4, "candidate": ITEM_ONSET,
               "baseline": "freq_articles", "candidate_setting": f"{ITEM_ONSET} bcp_prospective cutoff 0.5 sustain 1 margin 0.0",
               "content_alarm_week": -6, "content_outcome": "false_alarm"}
        [out] = grade_rows(weeks, [row])
        self.assertEqual((out["triggered_by"], out["grade_at_alarm"]), ("cases_suspected", 1))
        self.assertEqual([out[f"grade_week_{w}"] for w in range(-7, 0)], [None, 1, 1, 2, 3, 4, 4])


if __name__ == "__main__":
    unittest.main()


class CalendarReferenceTest(unittest.TestCase):
    """The no-news reference: alarm in the ISO week of the usual onset date from the other seasons."""

    ROWS = [{"season_id": s, "country": "USA", "season_year": y, "headline": "True", "onset_date": o}
            for s, y, o in (("USA-2016", "2016", "2016-12-19"),     # 353 days after 1 January
                            ("USA-2017", "2017", "2017-12-04"),     # 337
                            ("USA-2018", "2018", "2019-01-07"))]    # 371

    def test_weeks_come_from_the_other_seasons_median_date(self):
        # USA-2016: other offsets 337, 371 -> 337 -> Sat 2016-12-03, ISO week of Mon 11-28 -> week -3.
        # USA-2017: 353, 371 -> 353 -> Wed 2017-12-20, week of 12-18 -> +2, after the window -> miss.
        # USA-2018: 353, 337 -> 337 -> Tue 2018-12-04, week of 12-03 -> -5.
        self.assertEqual(calendar_alarm_weeks(self.ROWS), {"USA-2016": -3, "USA-2017": None, "USA-2018": -5})

    def test_reference_is_scored_at_each_early_limit(self):
        ref = calendar_reference(self.ROWS)["by_early_limit"]
        self.assertEqual({k: (v["hits"], v["false_alarms"], v["misses"], v["score"]) for k, v in ref.items()},
                         {"-4": (1, 1, 1, 0), "-5": (2, 0, 1, 2)})
        self.assertEqual(ref["-4"]["seasons"]["USA-2018"]["outcome"], "false_alarm")
