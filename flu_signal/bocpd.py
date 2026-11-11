"""Bayesian online change point detection (Adams & MacKay 2007).

Each week it updates the probability of every "run length" (weeks since the last change). An alarm is
raised at week t when the run is probably at most RECENT_WEEKS - 1 weeks old (a change at t or t - 1)
and the new run's level is above what came before.

Model: Normal with unknown mean and variance (Normal-Gamma prior, Student-t predictive) on
Anscombe-transformed counts. A Poisson model was planned, but weekly news counts vary far more than
Poisson allows (USA frequency moves between 250 and 360 with no real change), so it would alarm almost
every week. This model learns the noise level of each run from the data, so it does not need the transform
to make the noise 1. The transform still helps: small counts (0-3 a week) are skewed and stop at 0, and the
square root makes them closer to Normal; and both detectors then read the same values.

The prior is set from the first PRIOR_WEEKS weeks, and no alarm is raised before that, so the run
uses only weeks already seen. A new run's first week is scored under the prior predictive.
"""

import numpy as np
from scipy.special import gammaln, logsumexp

from detection import DEFAULT_TRANSFORM, NO_DETECTION, TRANSFORMS, Detection, is_sustained, transformed

HAZARD = 1.0 / 10.0       # prior chance of a change in any week (expected run of 10 weeks)
PRIOR_WEEKS = 3           # weeks used to set the prior; no alarm before the week after them
RECENT_WEEKS = 2          # an alarm needs the run to have started in the last 2 weeks
KAPPA0 = 1.0              # prior weight of the mean, in weeks
ALPHA0 = 1.0              # prior shape of the precision
MIN_VARIANCE = TRANSFORMS[DEFAULT_TRANSFORM].bocpd_min_variance   # 1.0: Anscombe variance of Poisson counts


def _student_t_logpdf(x: float, mu: np.ndarray, kappa: np.ndarray, alpha: np.ndarray, beta: np.ndarray) -> np.ndarray:
    df = 2.0 * alpha
    scale2 = beta * (kappa + 1.0) / (alpha * kappa)
    return (gammaln((df + 1.0) / 2.0) - gammaln(df / 2.0) - 0.5 * np.log(np.pi * df * scale2)
            - (df + 1.0) / 2.0 * np.log1p((x - mu) ** 2 / (df * scale2)))


def _prior(values: np.ndarray, min_variance: float = MIN_VARIANCE) -> tuple[float, float, float, float]:
    head = values[:PRIOR_WEEKS]
    variance = max(float(head.var()), min_variance)
    return float(head.mean()), KAPPA0, ALPHA0, ALPHA0 * variance


def run_length_posterior(counts, transform: str = DEFAULT_TRANSFORM) -> list[np.ndarray]:
    """P(run length = r | weeks so far) after each week; entry t has t + 1 values (r = 0 .. t)."""
    values = transformed(counts, transform)
    if len(values) < PRIOR_WEEKS:
        raise ValueError(f"need at least {PRIOR_WEEKS} weeks, got {len(values)}")
    mu0, kappa0, alpha0, beta0 = _prior(values, TRANSFORMS[transform].bocpd_min_variance)
    mu, kappa = np.array([mu0]), np.array([kappa0])
    alpha, beta = np.array([alpha0]), np.array([beta0])
    log_joint = np.array([0.0])          # before week 0 nothing has been seen
    posteriors = []
    prior_args = (np.array([mu0]), np.array([kappa0]), np.array([alpha0]), np.array([beta0]))
    for t, x in enumerate(values):
        if t == 0:
            log_joint = _student_t_logpdf(x, *prior_args)
        else:
            log_pred = _student_t_logpdf(x, mu, kappa, alpha, beta)
            log_growth = log_joint + np.log1p(-HAZARD) + log_pred
            log_change = logsumexp(log_joint) + np.log(HAZARD) + _student_t_logpdf(x, *prior_args)[0]
            log_joint = np.concatenate(([log_change], log_growth))
        posteriors.append(np.exp(log_joint - logsumexp(log_joint)))
        # Update every run with x; a new run (r = 0) starts from the prior.
        if t == 0:
            mu, kappa, alpha, beta = np.array([mu0]), np.array([kappa0]), np.array([alpha0]), np.array([beta0])
        else:
            mu = np.concatenate(([mu0], mu))
            kappa = np.concatenate(([kappa0], kappa))
            alpha = np.concatenate(([alpha0], alpha))
            beta = np.concatenate(([beta0], beta))
        beta = beta + kappa * (x - mu) ** 2 / (2.0 * (kappa + 1.0))
        mu = (kappa * mu + x) / (kappa + 1.0)
        kappa = kappa + 1.0
        alpha = alpha + 0.5
    return posteriors


def prospective(counts, cutoff: float, sustain_weeks: int = 1, margin: float = 0.0,
                transform: str = DEFAULT_TRANSFORM) -> Detection:
    """The earliest confirmed alarm. A candidate is a week t whose run probably began in the last
    RECENT_WEEKS weeks (at `start`), with the level going up. It is confirmed at week
    max(t, start + sustain_weeks - 1) if the rise has lasted `sustain_weeks` weeks by then; the check
    reads no week after the confirmation week. Candidates that fail are skipped."""
    values = transformed(counts, transform)
    confirmed = []
    for t, run_probability in enumerate(run_length_posterior(counts, transform)):
        if t < PRIOR_WEEKS:
            continue
        recent = float(run_probability[:RECENT_WEEKS].sum())
        if recent < cutoff:
            continue
        start = t - int(np.argmax(run_probability[:RECENT_WEEKS]))
        alarm = max(t, start + sustain_weeks - 1)
        if (alarm < len(values) and values[start:t + 1].mean() > values[:start].mean()
                and is_sustained(values, start, sustain_weeks, margin)):
            confirmed.append(Detection(alarm, start, recent))
    # A later candidate can be confirmed sooner than an earlier one when sustain_weeks is 3.
    return min(confirmed, key=lambda d: d.alarm_index, default=NO_DETECTION)
