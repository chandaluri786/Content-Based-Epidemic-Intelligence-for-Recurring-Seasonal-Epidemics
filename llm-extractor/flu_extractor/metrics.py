"""Counting helpers shared by the evaluation: confusion tables, rates, distributions, bootstrap."""

import random
from dataclasses import dataclass, field

BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 20261101  # the same seed in every run, so runs on the same articles are paired


def safe_divide(numerator: float, denominator: float) -> float | None:
    """Divide, returning None (shown as 'n/a') instead of crashing when the denominator is 0."""
    return numerator / denominator if denominator else None


@dataclass
class Counts:
    """True positives, false positives and false negatives, with the scores derived from them."""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float | None:
        """Of everything the model produced, the share that was right."""
        return safe_divide(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        """Of everything in the gold labels, the share the model found."""
        return safe_divide(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float | None:
        """Harmonic mean of precision and recall, written in counts so that 0 hits gives 0, not n/a."""
        return safe_divide(2 * self.tp, 2 * self.tp + self.fp + self.fn)


# --- Usefulness --------------------------------------------------------------

@dataclass
class UsefulnessResult:
    """Confusion table for 'is this article useful?'. Positive = useful."""

    counts: Counts = field(default_factory=Counts)
    true_negatives: int = 0

    @property
    def total(self) -> int:
        return self.counts.tp + self.counts.fp + self.counts.fn + self.true_negatives

    @property
    def accuracy(self) -> float | None:
        return safe_divide(self.counts.tp + self.true_negatives, self.total)


def score_usefulness(pairs: list[tuple[bool, bool]]) -> UsefulnessResult:
    """Score a list of (gold says useful, model says useful) pairs."""
    result = UsefulnessResult()
    for gold_useful, model_useful in pairs:
        if gold_useful and model_useful:
            result.counts.tp += 1
        elif model_useful:
            result.counts.fp += 1  # model said useful, gold said not
        elif gold_useful:
            result.counts.fn += 1  # model missed a useful article
        else:
            result.true_negatives += 1
    return result


def drop_inactive_only(items: list[dict]) -> list[dict]:
    """The planned filter for the weekly signal: an article whose only items are `inactive`
    trends counts as having no items."""
    return [] if items and all(item.get("words") == "inactive" for item in items) else items


# --- Distributions and intervals ---------------------------------------------

@dataclass
class Distribution:
    """Summary of one per-article score over the articles where it is defined."""

    articles: int          # articles with a value
    not_applicable: int    # articles in the population with no value (N/A)
    mean: float | None
    median: float | None
    q1: float | None
    q3: float | None
    share_zero: float | None
    share_one: float | None


def _quantile(sorted_values: list[float], q: float) -> float:
    position = (len(sorted_values) - 1) * q
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def describe(values: list[float | None]) -> Distribution:
    defined = sorted(v for v in values if v is not None)
    if not defined:
        return Distribution(0, len(values), None, None, None, None, None, None)
    n = len(defined)
    return Distribution(
        articles=n, not_applicable=len(values) - n, mean=sum(defined) / n,
        median=_quantile(defined, 0.5), q1=_quantile(defined, 0.25), q3=_quantile(defined, 0.75),
        share_zero=sum(v == 0 for v in defined) / n, share_one=sum(v == 1 for v in defined) / n,
    )


def bootstrap_indexes(size: int, resamples: int = BOOTSTRAP_RESAMPLES,
                      seed: int = BOOTSTRAP_SEED) -> list[list[int]]:
    """Resampled article positions. The same seed and size give the same samples, so two runs
    scored on the same sorted article list share their bootstrap samples (a paired comparison)."""
    generator = random.Random(seed)
    return [[generator.randrange(size) for _ in range(size)] for _ in range(resamples)] if size else []


def interval(statistic, size: int, samples: list[list[int]] | None = None) -> tuple[float, float] | None:
    """95% interval of `statistic(indexes)` over bootstrap samples of `size` articles."""
    samples = samples if samples is not None else bootstrap_indexes(size)
    values = sorted(v for v in (statistic(s) for s in samples) if v is not None)
    if not values:
        return None
    return values[int(0.025 * len(values))], values[max(int(0.975 * len(values)) - 1, 0)]
