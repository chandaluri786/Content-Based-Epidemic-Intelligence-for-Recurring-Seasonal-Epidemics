"""Bayesian change point analysis (Barry & Hartigan 1993), as used by Ganser et al. 2022 through R `bcp`.

The series is split into blocks with a constant mean. The posterior of a split rho with b blocks is
(Erdman & Emerson 2007, R bcp):

    f(rho | x)  ∝  ∫_0^p0 p^(b-1) (1-p)^(n-b) dp  *  ∫_0^w0 w^((b-1)/2) / (W + B w)^((n-1)/2) dw

with W the within-block and B the between-block sum of squares. R bcp samples splits by MCMC;
a season has only 12 weeks, so here every one of the 2^11 = 2,048 splits is summed exactly.

Changes from Ganser: the counts are Anscombe-transformed (detection.py), and W gets a small floor.
Only the shape of the noise matters here, not its size: scaling every value by c scales W and B by c^2, and
that factor is the same for every split, so it cancels. The floor is the one constant tied to the scale.
Without the floor, integer series with repeated values (0, 0, 0, 1, 1) have splits with W = 0, whose
weight is infinite, and those splits win however unlikely they are.
"""

import functools
import itertools

import numpy as np
from scipy.special import betainc, betaln, logsumexp

from detection import DEFAULT_TRANSFORM, NO_DETECTION, TRANSFORMS, Detection, is_sustained, transformed

P0 = 0.2                  # prior bound on the change probability (R bcp default, kept by Ganser)
W0 = 0.2                  # prior bound on the signal-to-noise ratio (R bcp default, kept by Ganser)
W_FLOOR_PER_WEEK = TRANSFORMS[DEFAULT_TRANSFORM].bcp_within_floor_per_week   # 0.1 on the Anscombe scale
W_GRID_POINTS = 200       # points for the w integral
MIN_WEEKS = 4             # the prospective run starts once this many weeks are seen


def _splits(n: int):
    """Every split of n points, as a tuple of block start positions (always starting with 0)."""
    for mask in itertools.product((False, True), repeat=n - 1):
        yield (0,) + tuple(i + 1 for i, cut in enumerate(mask) if cut)


def _log_weight(values: np.ndarray, starts: tuple[int, ...], w_grid: np.ndarray, log_dw: float,
                floor_per_week: float = W_FLOOR_PER_WEEK) -> float:
    n, b = len(values), len(starts)
    bounds = list(starts) + [n]
    blocks = [values[bounds[i]:bounds[i + 1]] for i in range(b)]
    grand_mean = values.mean()
    within = sum(float(((block - block.mean()) ** 2).sum()) for block in blocks) + floor_per_week * n
    between = sum(len(block) * (block.mean() - grand_mean) ** 2 for block in blocks)
    log_p_part = betaln(b, n - b + 1) + np.log(betainc(b, n - b + 1, P0))
    log_integrand = 0.5 * (b - 1) * np.log(w_grid) - 0.5 * (n - 1) * np.log(within + between * w_grid)
    return float(log_p_part + logsumexp(log_integrand) + log_dw)


def posterior(counts, transform: str = DEFAULT_TRANSFORM) -> tuple[np.ndarray, np.ndarray]:
    """(change_probability, posterior_mean) for a series of counts.

    change_probability[i] is the posterior probability that a new block starts at position i
    (index 0 is always 0). posterior_mean is on the transformed scale.
    Cached on the series: the cut-off, sustain and margin do not change it, so the step 4 grid reuses it.
    Copies are returned so a caller cannot change the cached arrays.
    """
    change_probability, posterior_mean = _posterior_cached(tuple(float(c) for c in counts), transform)
    return change_probability.copy(), posterior_mean.copy()


@functools.lru_cache(maxsize=None)
def _posterior_cached(counts: tuple[float, ...], transform: str) -> tuple[np.ndarray, np.ndarray]:
    values = transformed(counts, transform)
    floor = TRANSFORMS[transform].bcp_within_floor_per_week
    n = len(values)
    if n < 2:
        return np.zeros(n), values.copy()
    w_grid = np.linspace(W0 / W_GRID_POINTS, W0, W_GRID_POINTS)
    log_dw = np.log(W0 / W_GRID_POINTS)
    splits = list(_splits(n))
    log_weights = np.array([_log_weight(values, starts, w_grid, log_dw, floor) for starts in splits])
    weights = np.exp(log_weights - logsumexp(log_weights))

    change_probability = np.zeros(n)
    posterior_mean = np.zeros(n)
    for weight, starts in zip(weights, splits):
        bounds = list(starts) + [n]
        for i in range(len(starts)):
            block = values[bounds[i]:bounds[i + 1]]
            posterior_mean[bounds[i]:bounds[i + 1]] += weight * block.mean()
        for start in starts[1:]:
            change_probability[start] += weight
    return change_probability, posterior_mean


def first_rising_change(counts, cutoff: float, sustain_weeks: int = 1, margin: float = 0.0,
                        transform: str = DEFAULT_TRANSFORM) -> Detection:
    """The first position whose change probability reaches `cutoff`, with the mean going up there and
    the rise lasting `sustain_weeks` weeks (at least `margin` above the earlier level) within the series.
    Positions that fail are skipped."""
    change_probability, posterior_mean = posterior(counts, transform)
    values = transformed(counts, transform)
    for i in range(1, len(change_probability)):
        if (change_probability[i] >= cutoff and posterior_mean[i] > posterior_mean[i - 1]
                and is_sustained(values, i, sustain_weeks, margin)):
            return Detection(i, i, float(change_probability[i]))
    return NO_DETECTION


def retrospective(counts, cutoff: float, sustain_weeks: int = 1, margin: float = 0.0,
                  transform: str = DEFAULT_TRANSFORM) -> Detection:
    """Run on the whole window at once, as Ganser did. It uses weeks after the change."""
    return first_rising_change(counts, cutoff, sustain_weeks, margin, transform)


def prospective(counts, cutoff: float, sustain_weeks: int = 1, margin: float = 0.0,
                transform: str = DEFAULT_TRANSFORM) -> Detection:
    """Rerun on the weeks seen so far, week by week. The alarm is raised at the first week whose
    data so far show a rising change point that has lasted `sustain_weeks` weeks; the change itself
    lies at least sustain_weeks - 1 weeks earlier."""
    for seen in range(MIN_WEEKS, len(counts) + 1):
        found = first_rising_change(counts[:seen], cutoff, sustain_weeks, margin, transform)
        if found.change_index is not None:
            return Detection(seen - 1, found.change_index, found.probability)
    return NO_DETECTION
