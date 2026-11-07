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


if __name__ == "__main__":
    unittest.main()
