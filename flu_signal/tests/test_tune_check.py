"""Offline tests of tune.py --check (the frozen result still holds), on made-up seasons only.

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import unittest

from scoring import Setting
from tune import alarm_problems, choice_problems, score_weeks

GOOD = Setting("rising_articles", "bcp_prospective", 0.4, 1, 0.0)
BAD = Setting("rising_articles", "bocpd_prospective", 0.4, 1, 0.0)
FREQ = Setting("freq_articles", "bocpd_prospective", 0.4, 1, 0.0)
WEEKS = {GOOD: {"USA-2018": -1, "USA-2019": 0}, BAD: {"USA-2018": None, "USA-2019": -8},
         FREQ: {"USA-2018": 0, "USA-2019": 1}}


def entry(setting: Setting) -> dict:
    return {"signal": setting.signal, "method": setting.method, "cutoff": setting.cutoff,
            "sustain_weeks": setting.sustain_weeks, "margin": setting.margin}


class ChoiceTest(unittest.TestCase):
    def test_no_problem_when_tuning_gives_the_frozen_settings(self):
        scored = score_weeks(WEEKS, ["USA-2018", "USA-2019"])
        self.assertEqual(choice_problems(scored, {"content": entry(GOOD), "frequency": entry(FREQ)}), [])

    def test_a_different_choice_is_reported(self):
        scored = score_weeks(WEEKS, ["USA-2018", "USA-2019"])
        problems = choice_problems(scored, {"content": entry(BAD), "frequency": entry(FREQ)})
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("content"))


class AlarmTest(unittest.TestCase):
    RECORDED = [{"season_id": "USA-2018", "role": "content", "alarm_week": "-1"},
                {"season_id": "USA-2018", "role": "frequency", "alarm_week": ""}]

    def test_same_alarm_weeks_give_no_problem(self):
        now = [{"season_id": "USA-2018", "role": "content", "alarm_week": -1},
               {"season_id": "USA-2018", "role": "frequency", "alarm_week": None}]
        self.assertEqual(alarm_problems(now, self.RECORDED), [])

    def test_a_moved_alarm_is_reported(self):
        now = [{"season_id": "USA-2018", "role": "content", "alarm_week": -1},
               {"season_id": "USA-2018", "role": "frequency", "alarm_week": 1}]
        self.assertEqual(alarm_problems(now, self.RECORDED),
                         ["('USA-2018', 'frequency'): alarm week now 1, recorded none"])


if __name__ == "__main__":
    unittest.main()
