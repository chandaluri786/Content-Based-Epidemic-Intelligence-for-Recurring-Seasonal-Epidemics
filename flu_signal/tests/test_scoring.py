"""Offline tests of step 4: scoring, ranking and the tuner's season filter.

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import json
import tempfile
import unittest
from pathlib import Path

import signal_config as cfg
from run_detectors import DETECTED_SIGNALS, load_frozen_settings, setting_problems
from scoring import FALSE_ALARM, HIT, MISS, Score, Setting, classify, rank, score_setting
from tune import best, calibration_headline_seasons, grid, plateau, plateau_middle, score_grid

STEP = [31, 28, 33, 30, 29, 32, 27, 31, 88, 95, 91, 97]   # rise at week -2
FLAT = [31, 28, 33, 30, 29, 32, 27, 31, 30, 29, 33, 28]


def setting(cutoff: float = 0.5, sustain: int = 1, margin: float = 0.0, method: str = "bcp_prospective") -> Setting:
    return Setting("rising_articles", method, cutoff, sustain, margin)


def weekly_rows(season_id: str, split: str, series: list[int], headline: bool = True) -> list[dict]:
    """Rows shaped like output/weekly_signals.csv, the same series in every signal column."""
    return [{"season_id": season_id, "country": season_id[:3], "headline": str(headline), "split": split,
             "week": str(cfg.FIRST_WEEK + i), **{signal: str(count) for signal in DETECTED_SIGNALS}}
            for i, count in enumerate(series)]


class ClassifyTest(unittest.TestCase):
    def test_the_early_limit_week_is_a_hit_and_one_week_earlier_is_a_false_alarm(self):
        self.assertEqual(classify(-cfg.EARLY_LIMIT), HIT)
        self.assertEqual(classify(-cfg.EARLY_LIMIT - 1), FALSE_ALARM)

    def test_the_last_window_week_is_a_hit_and_no_alarm_is_a_miss(self):
        self.assertEqual(classify(cfg.LAST_WEEK), HIT)
        self.assertEqual(classify(None), MISS)

    def test_a_week_outside_the_window_stops_the_run(self):
        with self.assertRaises(ValueError):
            classify(cfg.LAST_WEEK + 1)


class ScoreTest(unittest.TestCase):
    def test_score_is_hits_minus_false_alarms(self):
        score = score_setting([-2, 0, 1, -7, None, None])
        self.assertEqual((score.hits, score.false_alarms, score.misses, score.value), (3, 1, 2, 2))
        self.assertEqual(score.median_hit_week, 0.0)

    def test_no_hits_has_no_median(self):
        self.assertIsNone(score_setting([None, -8]).median_hit_week)


class RankTest(unittest.TestCase):
    def test_higher_score_wins_then_more_hits_then_fewer_false_alarms(self):
        a = (setting(0.3), Score(hits=5, false_alarms=2, misses=6, median_hit_week=0.0))   # score 3
        b = (setting(0.4), Score(hits=4, false_alarms=0, misses=9, median_hit_week=0.0))   # score 4
        c = (setting(0.6), Score(hits=6, false_alarms=2, misses=5, median_hit_week=0.0))   # score 4, more hits
        self.assertEqual([pair[0].cutoff for pair in rank([a, b, c])], [0.6, 0.4, 0.3])

    def test_an_earlier_median_wins_a_tie_then_the_plainer_setting(self):
        late = (setting(0.5), Score(4, 0, 9, 1.0))
        early = (setting(0.8), Score(4, 0, 9, -1.0))
        self.assertEqual(rank([late, early])[0][0].cutoff, 0.8)
        plain = (setting(0.5, 1, 0.0), Score(4, 0, 9, 0.0))
        fussy = (setting(0.5, 2, 1.0), Score(4, 0, 9, 0.0))
        self.assertEqual(rank([fussy, plain])[0][0], plain[0])


class TuneTest(unittest.TestCase):
    def test_the_tuner_reads_only_calibration_headline_seasons(self):
        rows = (weekly_rows("USA-2018", cfg.SPLIT_CALIBRATION, STEP)
                + weekly_rows("USA-2023", cfg.SPLIT_HELD_OUT, FLAT)
                + weekly_rows("KEN-2019", cfg.SPLIT_CALIBRATION, FLAT, headline=False))
        self.assertEqual(sorted(calibration_headline_seasons(rows)), ["USA-2018"])

    def test_held_out_seasons_cannot_change_the_winner(self):
        calibration = weekly_rows("USA-2018", cfg.SPLIT_CALIBRATION, STEP) + weekly_rows("AUS-2017", cfg.SPLIT_CALIBRATION, FLAT)
        held_out = weekly_rows("USA-2023", cfg.SPLIT_HELD_OUT, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        settings = [s for s in grid(("rising_articles",)) if s.method == "bocpd_prospective"][:12]
        with_held_out = best(score_grid(settings, calibration_headline_seasons(calibration + held_out)), ("rising_articles",))
        without = best(score_grid(settings, calibration_headline_seasons(calibration)), ("rising_articles",))
        self.assertEqual(with_held_out[0], without[0])
        self.assertEqual(sorted(with_held_out[2]), ["AUS-2017", "USA-2018"])

    def test_retrospective_bcp_is_never_chosen(self):
        seasons = calibration_headline_seasons(weekly_rows("USA-2018", cfg.SPLIT_CALIBRATION, STEP))
        winner = best(score_grid(grid(("rising_articles",)), seasons), ("rising_articles",))
        self.assertNotEqual(winner[0].method, "bcp_retrospective")


def scored_run(values_by_cutoff: dict[float, int]) -> list[tuple]:
    """A fake scored grid for one signal/method/sustain/margin: {cut-off: score} (score = hits, no false alarms)."""
    return [(setting(cutoff), Score(hits=value, false_alarms=0, misses=13 - value, median_hit_week=0.0), {})
            for cutoff, value in values_by_cutoff.items()]


class PlateauTest(unittest.TestCase):
    def test_a_plateau_of_three_freezes_the_middle_cutoff(self):
        scored = scored_run({0.3: 8, 0.4: 8, 0.5: 8, 0.6: 7, 0.7: 7})
        winner = scored[0]
        self.assertEqual([row[0].cutoff for row in plateau(winner, scored)], [0.3, 0.4, 0.5])
        self.assertEqual(plateau_middle(winner, scored)[0].cutoff, 0.4)

    def test_a_plateau_of_two_freezes_the_lower_cutoff(self):
        scored = scored_run({0.3: 6, 0.4: 8, 0.5: 8, 0.6: 7})
        self.assertEqual(plateau_middle(scored[1], scored)[0].cutoff, 0.4)

    def test_a_lone_peak_stays_and_a_gap_ends_the_plateau(self):
        scored = scored_run({0.3: 8, 0.4: 7, 0.5: 8, 0.6: 8})
        self.assertEqual(plateau_middle(scored[0], scored)[0].cutoff, 0.3)
        self.assertEqual([row[0].cutoff for row in plateau(scored[2], scored)], [0.5, 0.6])

    def test_other_settings_are_not_part_of_the_plateau(self):
        other = (Setting("rising_articles", "bocpd_prospective", 0.4, 1, 0.0), Score(8, 0, 5, 0.0), {})
        scored = scored_run({0.3: 8, 0.4: 6}) + [other]
        self.assertEqual([row[0].cutoff for row in plateau(scored[0], scored)], [0.3])


class FrozenSettingsTest(unittest.TestCase):
    GOOD = {"signal": "rising_articles", "method": "bcp_prospective", "cutoff": 0.4, "sustain_weeks": 1, "margin": 0.0}

    def write(self, content: dict, frequency: dict) -> Path:
        path = Path(tempfile.mkdtemp()) / "frozen_settings.json"
        path.write_text(json.dumps({"content": content, "frequency": frequency}), encoding="utf-8")
        return path

    def test_a_setting_tune_could_choose_has_no_problems(self):
        self.assertEqual(setting_problems(self.GOOD), [])
        frozen = load_frozen_settings(self.write(self.GOOD, {**self.GOOD, "signal": "freq_articles"}))
        self.assertEqual(frozen["content"]["cutoff"], 0.4)

    def test_retrospective_unknown_signal_or_off_grid_values_are_refused(self):
        for bad in ({"method": "bcp_retrospective"}, {"signal": "avian_articles"}, {"cutoff": 0.35},
                    {"sustain_weeks": 4}, {"margin": 0.5}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                load_frozen_settings(self.write({**self.GOOD, **bad}, self.GOOD))

    def test_a_missing_file_or_role_stops_the_held_out_run(self):
        with self.assertRaises(FileNotFoundError):
            load_frozen_settings(Path(tempfile.mkdtemp()) / "none.json")
        path = Path(tempfile.mkdtemp()) / "frozen_settings.json"
        path.write_text(json.dumps({"content": self.GOOD}), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_frozen_settings(path)


if __name__ == "__main__":
    unittest.main()
