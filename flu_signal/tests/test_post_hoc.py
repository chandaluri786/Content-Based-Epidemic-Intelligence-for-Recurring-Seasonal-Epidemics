"""Offline tests of the post-hoc checks, on made-up seasons only.

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import unittest

from post_hoc import bird_flu_share, by_year, uniform
from scoring import Setting

GOOD = Setting("rising_articles", "bcp_prospective", 0.4, 1, 0.0)
BAD = Setting("rising_articles", "bocpd_prospective", 0.4, 1, 0.0)
FREQ = Setting("freq_articles", "bocpd_prospective", 0.4, 1, 0.0)
SEASONS = {season_id: {"country": season_id[:3], "headline": True}
           for season_id in ("USA-2018", "USA-2019", "USA-2022", "USA-2023")}


class ByYearTest(unittest.TestCase):
    def test_the_choice_uses_only_calibration_seasons(self):
        # GOOD hits both calibration seasons and misses held-out; BAD is the reverse. GOOD must be chosen.
        weeks = {GOOD: {"USA-2018": -1, "USA-2019": 0, "USA-2022": None, "USA-2023": None},
                 BAD: {"USA-2018": None, "USA-2019": None, "USA-2022": -2, "USA-2023": -1},
                 FREQ: {"USA-2018": 0, "USA-2019": 0, "USA-2022": 0, "USA-2023": 0}}
        content, frequency, rows = by_year(weeks, SEASONS, 4, ("rising_articles",), FREQ)
        self.assertEqual((content, frequency), (GOOD, FREQ))
        self.assertEqual([row["season_id"] for row in rows], ["USA-2022", "USA-2023"])
        self.assertEqual([row["content_outcome"] for row in rows], ["miss", "miss"])

    def test_the_limit_changes_the_choice_and_the_outcome(self):
        # At -4, GOOD's -5 alarms are false and BAD's misses score higher; at -6 GOOD's are hits.
        weeks = {GOOD: {"USA-2018": -5, "USA-2019": -5, "USA-2022": -5, "USA-2023": -5},
                 BAD: {"USA-2018": None, "USA-2019": None, "USA-2022": None, "USA-2023": None},
                 FREQ: {"USA-2018": 0, "USA-2019": 0, "USA-2022": 0, "USA-2023": 0}}
        self.assertEqual(by_year(weeks, SEASONS, 4, ("rising_articles",), FREQ)[0], BAD)
        content, _, rows = by_year(weeks, SEASONS, 6, ("rising_articles",), FREQ)
        self.assertEqual(content, GOOD)
        self.assertEqual([row["winner"] for row in rows], ["content", "content"])


class HelpersTest(unittest.TestCase):
    def test_only_content_articles_mixes_in_bird_flu(self):
        seasons = {"USA-2024": {"content_articles": [8, 2], "avian_articles": [5, 0]},
                   "USA-2019": {"content_articles": [9, 9], "avian_articles": [9, 9]}}   # calibration: ignored
        self.assertEqual(bird_flu_share("content_articles", seasons), 0.5)
        self.assertEqual((bird_flu_share("rising_articles", seasons), bird_flu_share("avian_articles", seasons)),
                         (0.0, 1.0))

    def test_uniform_gives_every_row_the_same_columns(self):
        self.assertEqual(uniform([{"a": 1}, {"b": 2}]), [{"a": 1, "b": ""}, {"a": "", "b": 2}])


if __name__ == "__main__":
    unittest.main()
