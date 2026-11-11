"""Offline tests of the transform check's diagnostics, on made-up seasons only.

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import unittest

from scoring import Setting
from transform_check import near_best
from tune import score_weeks

SEASONS = ["USA-2018", "USA-2019", "USA-2023"]


def setting(cutoff: float, method: str = "bcp_prospective") -> Setting:
    return Setting("rising_articles", method, cutoff, 1, 0.0)


class NearBestTest(unittest.TestCase):
    def test_counts_selectable_settings_within_one_point_of_the_best(self):
        weeks = {setting(0.3): {"USA-2018": -1, "USA-2019": 0, "USA-2023": 1},      # score 3
                 setting(0.4): {"USA-2018": -1, "USA-2019": 0, "USA-2023": None},    # score 2
                 setting(0.5): {"USA-2018": -1, "USA-2019": None, "USA-2023": None},  # score 1
                 setting(0.6, "bcp_retrospective"): {"USA-2018": -1, "USA-2019": 0, "USA-2023": 1}}  # not selectable
        best, score, crowd = near_best(score_weeks(weeks, SEASONS), ("rising_articles",))
        self.assertEqual((best, score.value, crowd), (setting(0.3), 3, 2))


if __name__ == "__main__":
    unittest.main()
