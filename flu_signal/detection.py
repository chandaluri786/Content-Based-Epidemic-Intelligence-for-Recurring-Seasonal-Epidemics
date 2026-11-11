"""What the two change-point detectors share: the count transform and the result type.

Both detectors work on Anscombe-transformed counts, 2 * sqrt(x + 3/8). For Poisson counts the noise on this
scale has variance close to 1 at any level, and the Normal models inside the detectors fit better than on raw
counts (small counts are skewed and stop at 0).

Real weekly news counts are noisier than Poisson: in weeks -10 .. -5 the variance is about 2.7 times the mean
for freq_articles (Poisson: 1 times). So on the Anscombe scale the noise is close to 1 only for small series;
big USA series have about 2 to 4. That does not break the detectors: BCP needs only the same noise before and
after a change (it estimates the level itself), and BOCPD learns the noise of each run. Only the fixed constants
assume a noise of about 1: MARGIN_CHOICES (margin 1 = "one Poisson noise unit"), the BCP floor and the BOCPD
variance floor. No chosen setting uses margin 1.

Other transforms (log, raw) exist only for the post-hoc check in transform_check.py; anscombe is the method.
"""

from collections.abc import Callable
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
MARGIN_CHOICES = (0.0, 1.0)   # how far above the earlier level, on the transformed scale
                              # (on the Anscombe scale 1 = one Poisson noise unit)


def is_sustained(values: np.ndarray, change_index: int, sustain_weeks: int, margin: float = 0.0) -> bool:
    """True when each of the `sustain_weeks` weeks from `change_index` is above the mean of the weeks
    before it plus `margin`.

    `values` are transformed counts. Only values[:change_index + sustain_weeks] are read, so a caller that
    has seen that many weeks uses no later data. With sustain 1 only the change week itself is checked.
    """
    if sustain_weeks not in SUSTAIN_CHOICES:
        raise ValueError(f"sustain_weeks must be one of {SUSTAIN_CHOICES}, got {sustain_weeks}")
    if margin < 0:
        raise ValueError(f"margin must be 0 or more, got {margin}")
    after = values[change_index:change_index + sustain_weeks]
    if change_index < 1 or len(after) < sustain_weeks:
        return False
    return bool((after > values[:change_index].mean() + margin).all())


@dataclass(frozen=True)
class Transform:
    """A count transform and the noise floors the detectors use on its scale."""

    apply: Callable[[np.ndarray], np.ndarray]
    bcp_within_floor_per_week: float   # bcp.py: keeps splits with no within-block spread from winning
    bocpd_min_variance: float          # bocpd.py: floor of the prior variance


def _anscombe(values: np.ndarray) -> np.ndarray:
    return 2.0 * np.sqrt(values + 3.0 / 8.0)


def _raw(values: np.ndarray) -> np.ndarray:
    return values.copy()


DEFAULT_TRANSFORM = "anscombe"
# log: Poisson noise of log(x + 1) is about 1 / x, so the floors are set for about 10 a week: variance 0.1, and
# the BCP floor one tenth of that, as for anscombe (0.1 against a noise of 1). raw keeps the anscombe floors.
TRANSFORMS = {
    "anscombe": Transform(_anscombe, bcp_within_floor_per_week=0.1, bocpd_min_variance=1.0),
    "log": Transform(np.log1p, bcp_within_floor_per_week=0.01, bocpd_min_variance=0.1),
    "raw": Transform(_raw, bcp_within_floor_per_week=0.1, bocpd_min_variance=1.0),
}


def transformed(counts, transform: str = DEFAULT_TRANSFORM) -> np.ndarray:
    if transform not in TRANSFORMS:
        raise ValueError(f"transform must be one of {tuple(TRANSFORMS)}, got {transform!r}")
    values = np.asarray(counts, dtype=float)
    if values.ndim != 1 or (values < 0).any():
        raise ValueError("counts must be a 1-D series of non-negative numbers")
    return TRANSFORMS[transform].apply(values)


def anscombe(counts) -> np.ndarray:
    return transformed(counts, "anscombe")
