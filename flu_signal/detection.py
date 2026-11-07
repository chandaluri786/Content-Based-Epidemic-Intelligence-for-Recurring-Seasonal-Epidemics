"""What the two change-point detectors share: the count transform and the result type.

Both detectors work on Anscombe-transformed counts, 2 * sqrt(x + 3/8). For Poisson counts this has
variance close to 1 at any level, so a USA week of 300 articles and a KEN week of 3 are on comparable
footing, and the Normal models inside the detectors fit better than on raw counts.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Detection:
    """The first alarm of one detector on one series.

    alarm_index: position in the series (0 = first week) at which the alarm is raised, or None.
    change_index: position where the detected rise starts (<= alarm_index), or None.
    For a retrospective run both are the change point; for a prospective run the alarm is raised
    at the week the data first show the change.
    """

    alarm_index: int | None
    change_index: int | None
    probability: float | None


NO_DETECTION = Detection(None, None, None)


SUSTAIN_CHOICES = (1, 2, 3)   # weeks a rise must stay up; tuned on calibration seasons (step 4)


def is_sustained(values: np.ndarray, change_index: int, sustain_weeks: int) -> bool:
    """True when each of the `sustain_weeks` weeks from `change_index` is above the mean of the weeks before it.

    `values` are Anscombe-transformed. Only values[:change_index + sustain_weeks] are read, so a caller that
    has seen that many weeks uses no later data. With sustain 1 only the change week itself is checked.
    """
    if sustain_weeks not in SUSTAIN_CHOICES:
        raise ValueError(f"sustain_weeks must be one of {SUSTAIN_CHOICES}, got {sustain_weeks}")
    after = values[change_index:change_index + sustain_weeks]
    if change_index < 1 or len(after) < sustain_weeks:
        return False
    return bool((after > values[:change_index].mean()).all())


def anscombe(counts) -> np.ndarray:
    values = np.asarray(counts, dtype=float)
    if values.ndim != 1 or (values < 0).any():
        raise ValueError("counts must be a 1-D series of non-negative numbers")
    return 2.0 * np.sqrt(values + 3.0 / 8.0)
