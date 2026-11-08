"""Offline tests of the step 5 rules, on made-up seasons only.

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import unittest

import signal_config as cfg
from evaluate import (CONTENT, FREQUENCY, TIE, compare_season, is_timely, lead_days, lead_days_known,
                      season_row, sign_test, summarize)
from report_results import build_report, paired_rows


def detection(season_id: str, role: str, alarm_week: int | None, headline: bool = True) -> dict:
    """A row shaped like output/detections_*_frozen.csv."""
    return {"season_id": season_id, "country": season_id[:3], "headline": str(headline), "role": role,
            "alarm_week": "" if alarm_week is None else str(alarm_week)}


class LeadTest(unittest.TestCase):
    def test_lead_counts_weeks_before_onset(self):
        self.assertEqual((lead_days(-2), lead_days(0), lead_days(1)), (14, 0, -7))

    def test_known_lead_counts_from_the_end_of_the_alarm_week(self):
        self.assertEqual((lead_days_known(-2), lead_days_known(-1), lead_days_known(0)), (7, 0, -7))

    def test_no_alarm_has_no_lead(self):
        self.assertIsNone(lead_days(None))
        self.assertIsNone(lead_days_known(None))

    def test_timely_is_weeks_minus_2_to_plus_1(self):
        self.assertEqual([is_timely(w) for w in (-3, -2, 1, None, -7)], [False, True, True, False, False])


class CompareTest(unittest.TestCase):
    def test_a_hit_beats_a_miss_and_a_miss_beats_a_false_alarm(self):
        self.assertEqual(compare_season(0, None), CONTENT)
        self.assertEqual(compare_season(None, -7), CONTENT)
        self.assertEqual(compare_season(-7, None), FREQUENCY)
        self.assertEqual(compare_season(-6, 1), FREQUENCY)

    def test_when_both_hit_the_earlier_alarm_wins(self):
        self.assertEqual(compare_season(-2, 0), CONTENT)
        self.assertEqual(compare_season(1, -3), FREQUENCY)

    def test_same_week_both_miss_or_both_false_is_a_tie(self):
        self.assertEqual(compare_season(-1, -1), TIE)
        self.assertEqual(compare_season(None, None), TIE)
        self.assertEqual(compare_season(-7, -6), TIE)


class EarlyLimitTest(unittest.TestCase):
    def test_a_wider_limit_turns_a_week_minus_5_false_alarm_into_a_hit(self):
        self.assertEqual(season_row("USA-2022", "USA", -5, None)["content_outcome"], "false_alarm")
        self.assertEqual(season_row("USA-2022", "USA", -5, None, 6)["content_outcome"], "hit")

    def test_the_winner_follows_the_limit(self):
        self.assertEqual(compare_season(-5, None), FREQUENCY)     # false alarm loses to a miss at -4
        self.assertEqual(compare_season(-5, None, 6), CONTENT)    # a hit beats a miss at -6

    def test_timely_does_not_move_with_the_limit(self):
        self.assertEqual(season_row("USA-2022", "USA", -3, None, 6)["content_timely"], False)


class SignTestTest(unittest.TestCase):
    def test_exact_two_sided_values(self):
        self.assertAlmostEqual(sign_test(7, 1), 18 / 256)
        self.assertAlmostEqual(sign_test(1, 7), 18 / 256)
        self.assertEqual(sign_test(4, 4), 1.0)
        self.assertEqual(sign_test(0, 0), 1.0)
        self.assertAlmostEqual(sign_test(9, 0), 2 / 512)


class SummaryTest(unittest.TestCase):
    def test_a_hand_worked_set_of_seasons(self):
        # content: hit -2, hit 0, miss, hit 1; frequency: hit 0, false -7, hit -1, miss
        rows = [season_row("USA-2022", "USA", -2, 0), season_row("USA-2023", "USA", 0, -7),
                season_row("AUS-2022", "AUS", None, -1), season_row("IND-2022", "IND", 1, None)]
        summary = summarize(rows)
        self.assertEqual([r["winner"] for r in rows], [CONTENT, CONTENT, FREQUENCY, CONTENT])
        self.assertEqual((summary[CONTENT]["hits"], summary[CONTENT]["false_alarms"], summary[CONTENT]["score"]), (3, 0, 3))
        self.assertEqual((summary[FREQUENCY]["hits"], summary[FREQUENCY]["false_alarms"], summary[FREQUENCY]["score"]), (2, 1, 1))
        self.assertEqual((summary["content_wins"], summary["frequency_wins"], summary["ties"]), (3, 1, 0))
        self.assertEqual(summary[CONTENT]["median_lead_days"], 0)          # leads 14, 0, -7
        self.assertEqual(summary["median_lead_difference_days_when_both_hit"], 14)
        self.assertTrue(summary["content_better"])

    def test_content_is_not_better_with_a_lower_score_even_with_more_wins(self):
        rows = [season_row("A-1", "USA", -1, 0), season_row("A-2", "USA", -1, 0), season_row("A-3", "USA", -8, None)]
        summary = summarize(rows)
        self.assertEqual((summary["content_wins"], summary["frequency_wins"]), (2, 1))
        self.assertFalse(summary["content_better"])                          # score 1 vs 2


class ReportTest(unittest.TestCase):
    def test_pairs_content_and_frequency_and_flags_tuned_on_seasons(self):
        held_out = [detection("USA-2023", "content", -1), detection("USA-2023", "frequency", 1),
                    detection("KEN-2023", "content", None, False), detection("KEN-2023", "frequency", None, False)]
        calibration = [detection("USA-2018", "content", 0), detection("USA-2018", "frequency", None),
                       detection("BRA-2019", "content", None, False), detection("BRA-2019", "frequency", -6, False)]
        headline, all_rows, summary = build_report(held_out, calibration)
        self.assertEqual([r["season_id"] for r in headline], ["USA-2023"])
        self.assertEqual({r["season_id"]: r["tuned_on"] for r in all_rows},
                         {"BRA-2019": False, "KEN-2023": False, "USA-2018": True, "USA-2023": False})
        self.assertEqual(summary["headline_held_out"]["content_wins"], 1)
        self.assertEqual(summary["all_38_not_tuned_on"]["seasons"], 3)

    def test_a_season_without_both_roles_stops_the_report(self):
        with self.assertRaises(ValueError):
            paired_rows([detection("USA-2023", "content", -1)], cfg.SPLIT_HELD_OUT)


if __name__ == "__main__":
    unittest.main()
