"""Offline tests of the two change-point detectors on made-up series with a known answer.

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import unittest

import numpy as np
from scipy.integrate import quad

import bcp
import bocpd
from detection import anscombe, is_sustained

CUTOFF = 0.5
# 12 weeks: flat around 30, then a jump to about 90 at position 8 (week -2 in a real season).
STEP_UP = [31, 28, 33, 30, 29, 32, 27, 31, 88, 95, 91, 97]
STEP_DOWN = list(reversed(STEP_UP))
FLAT = [31, 28, 33, 30, 29, 32, 27, 31, 30, 29, 33, 28]
# A sparse series like KEN or AUS-2016 content: 0-1 a week, then 5-7.
SPARSE_STEP = [0, 1, 0, 0, 1, 0, 0, 1, 5, 6, 7, 6]
# One busy week at position 8, then back to normal: not a season starting.
SPIKE = [31, 28, 33, 30, 29, 32, 27, 31, 90, 30, 29, 31]
PROSPECTIVE = {"bcp": bcp.prospective, "bocpd": bocpd.prospective}


def quad_change_probability(counts) -> np.ndarray:
    """The Barry-Hartigan posterior worked out a second way: scipy quad for both integrals."""
    values = anscombe(counts)
    n = len(values)
    weights, splits = [], list(bcp._splits(n))
    for starts in splits:
        b, bounds = len(starts), list(starts) + [n]
        blocks = [values[bounds[i]:bounds[i + 1]] for i in range(b)]
        within = sum(((block - block.mean()) ** 2).sum() for block in blocks) + bcp.W_FLOOR_PER_WEEK * n
        between = sum(len(block) * (block.mean() - values.mean()) ** 2 for block in blocks)
        p_part = quad(lambda p: p ** (b - 1) * (1 - p) ** (n - b), 0, bcp.P0)[0]
        w_part = quad(lambda w: w ** ((b - 1) / 2) / (within + between * w) ** ((n - 1) / 2), 0, bcp.W0)[0]
        weights.append(p_part * w_part)
    weights = np.array(weights) / sum(weights)
    change_probability = np.zeros(n)
    for weight, starts in zip(weights, splits):
        for start in starts[1:]:
            change_probability[start] += weight
    return change_probability


class TransformTest(unittest.TestCase):
    def test_anscombe_is_monotone_and_rejects_negative_counts(self):
        values = anscombe([0, 1, 10, 100])
        self.assertTrue(np.all(np.diff(values) > 0))
        with self.assertRaises(ValueError):
            anscombe([1, -1])


class SustainedTest(unittest.TestCase):
    def test_a_rise_counts_only_when_every_week_of_it_is_above_the_earlier_level(self):
        values = anscombe(SPIKE)
        self.assertTrue(is_sustained(values, 8, 1))
        self.assertFalse(is_sustained(values, 8, 2))
        self.assertTrue(is_sustained(anscombe(STEP_UP), 8, 3))

    def test_a_rise_running_past_the_series_end_is_not_sustained(self):
        self.assertFalse(is_sustained(anscombe(STEP_UP), 10, 3))
        self.assertFalse(is_sustained(anscombe(STEP_UP), 0, 1))

    def test_only_1_2_or_3_weeks_are_allowed(self):
        with self.assertRaises(ValueError):
            is_sustained(anscombe(STEP_UP), 8, 4)


class SustainDetectorTest(unittest.TestCase):
    def test_a_one_week_spike_alarms_with_sustain_1_but_not_with_sustain_2(self):
        self.assertEqual(bcp.retrospective(SPIKE, CUTOFF, 1).alarm_index, 8)
        self.assertIsNone(bcp.retrospective(SPIKE, CUTOFF, 2).alarm_index)
        for name, detect in PROSPECTIVE.items():
            self.assertEqual(detect(SPIKE, CUTOFF, 1).alarm_index, 8, name)
            self.assertIsNone(detect(SPIKE, CUTOFF, 2).alarm_index, name)

    def test_a_lasting_step_still_alarms_with_sustain_2_one_week_later_when_prospective(self):
        self.assertEqual(bcp.retrospective(STEP_UP, CUTOFF, 2).alarm_index, 8)
        for name, detect in PROSPECTIVE.items():
            found = detect(STEP_UP, CUTOFF, 2)
            self.assertEqual((found.change_index, found.alarm_index), (8, 9), name)
            self.assertEqual(detect(STEP_UP, CUTOFF, 3).alarm_index, 10, name)

    def test_prospective_with_sustain_never_uses_later_weeks(self):
        for sustain in (2, 3):
            for name, detect in PROSPECTIVE.items():
                found = detect(STEP_UP, CUTOFF, sustain)
                changed_tail = STEP_UP[:found.alarm_index + 1] + [0] * (len(STEP_UP) - found.alarm_index - 1)
                self.assertEqual(detect(changed_tail, CUTOFF, sustain).alarm_index, found.alarm_index, name)


class BcpMathTest(unittest.TestCase):
    def test_the_exact_sum_matches_a_second_calculation_with_quad(self):
        for counts in ([3, 5, 4, 12, 14], [0, 1, 0, 6, 7, 5]):
            np.testing.assert_allclose(bcp.posterior(counts)[0], quad_change_probability(counts), atol=2e-3)


class BcpTest(unittest.TestCase):
    def test_change_probabilities_are_highest_at_the_true_step(self):
        change_probability, _ = bcp.posterior(STEP_UP)
        self.assertEqual(int(np.argmax(change_probability)), 8)
        self.assertGreater(change_probability[8], 0.9)

    def test_retrospective_finds_the_step_up(self):
        self.assertEqual(bcp.retrospective(STEP_UP, CUTOFF).alarm_index, 8)
        self.assertEqual(bcp.retrospective(SPARSE_STEP, CUTOFF).alarm_index, 8)

    def test_a_step_down_or_a_flat_series_gives_no_alarm(self):
        self.assertIsNone(bcp.retrospective(STEP_DOWN, CUTOFF).alarm_index)
        self.assertIsNone(bcp.retrospective(FLAT, CUTOFF).alarm_index)
        self.assertIsNone(bcp.retrospective([0] * 12, CUTOFF).alarm_index)

    def test_prospective_alarms_no_earlier_than_the_step_and_soon_after(self):
        found = bcp.prospective(STEP_UP, CUTOFF)
        self.assertEqual(found.change_index, 8)
        self.assertIn(found.alarm_index, (8, 9))

    def test_prospective_never_uses_later_weeks(self):
        # Changing the weeks after the alarm must not change the alarm.
        found = bcp.prospective(STEP_UP, CUTOFF)
        changed_tail = STEP_UP[:found.alarm_index + 1] + [0] * (len(STEP_UP) - found.alarm_index - 1)
        self.assertEqual(bcp.prospective(changed_tail, CUTOFF).alarm_index, found.alarm_index)


class BocpdTest(unittest.TestCase):
    def test_run_length_probabilities_sum_to_one_each_week(self):
        for probabilities in bocpd.run_length_posterior(STEP_UP):
            self.assertAlmostEqual(float(probabilities.sum()), 1.0, places=9)

    def test_it_finds_the_step_up_within_a_week(self):
        found = bocpd.prospective(STEP_UP, CUTOFF)
        self.assertIn(found.alarm_index, (8, 9))
        self.assertIn(found.change_index, (8, 9))

    def test_it_finds_a_sparse_step(self):
        self.assertIn(bocpd.prospective(SPARSE_STEP, CUTOFF).alarm_index, (8, 9))

    def test_a_step_down_or_a_flat_series_gives_no_alarm(self):
        self.assertIsNone(bocpd.prospective(STEP_DOWN, CUTOFF).alarm_index)
        self.assertIsNone(bocpd.prospective(FLAT, CUTOFF).alarm_index)
        self.assertIsNone(bocpd.prospective([0] * 12, CUTOFF).alarm_index)

    def test_it_never_uses_later_weeks(self):
        found = bocpd.prospective(STEP_UP, CUTOFF)
        changed_tail = STEP_UP[:found.alarm_index + 1] + [0] * (len(STEP_UP) - found.alarm_index - 1)
        self.assertEqual(bocpd.prospective(changed_tail, CUTOFF).alarm_index, found.alarm_index)

    def test_no_alarm_inside_the_prior_weeks(self):
        early_jump = [5, 90, 95, 92, 94, 91, 93, 95, 92, 94, 90, 93]
        found = bocpd.prospective(early_jump, CUTOFF)
        self.assertTrue(found.alarm_index is None or found.alarm_index >= bocpd.PRIOR_WEEKS)


if __name__ == "__main__":
    unittest.main()
