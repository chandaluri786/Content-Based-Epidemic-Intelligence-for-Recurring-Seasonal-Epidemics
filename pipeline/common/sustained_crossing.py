"""Generic "N consecutive periods over a threshold" detector.

Shared by ground_truth/onset_detection.py (flat positivity-rate rule, Step 1)
and detection/crossing_rule.py (content/frequency signal rule, Step 6) so both
"onset" definitions are structurally identical and directly comparable.
"""

from collections.abc import Sequence


def find_sustained_crossing(
    values: Sequence[float | None],
    threshold: float,
    sustain_periods: int,
    start_index: int = 0,
) -> int | None:
    """Return the index of the first period in the first run of `sustain_periods`
    consecutive values (from start_index onward) that are each >= threshold.

    A None value never counts toward a crossing and breaks any run in progress.
    Returns None if no such run exists.
    """
    if sustain_periods < 1:
        raise ValueError(f"sustain_periods must be >= 1, got {sustain_periods}")

    run_start: int | None = None
    run_length = 0

    for i in range(start_index, len(values)):
        value = values[i]
        if value is not None and value >= threshold:
            if run_length == 0:
                run_start = i
            run_length += 1
            if run_length >= sustain_periods:
                return run_start
        else:
            run_length = 0
            run_start = None

    return None
