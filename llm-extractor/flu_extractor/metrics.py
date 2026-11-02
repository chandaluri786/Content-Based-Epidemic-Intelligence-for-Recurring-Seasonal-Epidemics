"""Scoring: usefulness classification and item matching against the gold labels."""

import random
from dataclasses import dataclass, field
from datetime import date

ITEM_KINDS = ("cases", "deaths", "hospitalized", "trend")

# Three ways to decide that a model item and a human item are "the same", from strictest to loosest.
# Evidence is never compared: the model and the labeler may quote different sentences for one fact.
#
# EXACT: every item field except evidence agrees. This is the headline score.
EXACT_KEY_FIELDS = (
    "kind", "number", "count_type", "status", "strain",
    "city", "state", "country", "start_date", "end_date", "words",
)
# STRICT: kind, place, strain and dates, ignoring the other fields.
STRICT_KEY_FIELDS = ("kind", "strain", "city", "state", "country", "start_date", "end_date")
# RELAXED: STRICT without dates. Also used to pair up near-misses for reading.
RELAXED_KEY_FIELDS = ("kind", "strain", "city", "state", "country")
# WEEKLY: what the weekly signal uses: kind, strain, country and the ISO week of the end date.
WEEKLY_KEY_FIELDS = ("kind", "strain", "country", "end_week")


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


# --- Items -------------------------------------------------------------------

def _normalise(value) -> str:
    """Make values comparable: None -> '', lower case, single spaces."""
    if value is None:
        return ""
    return " ".join(str(value).lower().split())


def _end_week(item: dict) -> str:
    """The ISO week of the end date, such as 2018-W27. Empty when there is no valid date."""
    try:
        year, week, _ = date.fromisoformat(item.get("end_date") or "").isocalendar()
    except ValueError:
        return ""
    return f"{year}-W{week:02d}"


def _item_key(item: dict, key_fields: tuple[str, ...]) -> tuple:
    values = {**item, "end_week": _end_week(item)} if "end_week" in key_fields else item
    return tuple(_normalise(values.get(name)) for name in key_fields)


def differing_fields(gold_item: dict, model_item: dict) -> list[str]:
    """Names of the fields (evidence excluded) on which two items disagree."""
    return [name for name in EXACT_KEY_FIELDS
            if _normalise(gold_item.get(name)) != _normalise(model_item.get(name))]


@dataclass
class ItemMatch:
    """Result of comparing the items of one article."""

    matched: list[tuple[dict, dict]]  # (gold item, model item)
    missed: list[dict]                # gold items the model did not produce
    extra: list[dict]                 # model items no gold item corresponds to


def match_items(gold_items: list[dict], model_items: list[dict],
                key_fields: tuple[str, ...]) -> ItemMatch:
    """Pair model items with gold items that have the same key. Each gold item is used once."""
    unused_gold = list(gold_items)
    matched, extra = [], []
    for model_item in model_items:
        model_key = _item_key(model_item, key_fields)
        partner = next(
            (g for g in unused_gold if _item_key(g, key_fields) == model_key), None
        )
        if partner is None:
            extra.append(model_item)
        else:
            unused_gold.remove(partner)
            matched.append((partner, model_item))
    return ItemMatch(matched=matched, missed=unused_gold, extra=extra)


@dataclass
class ItemTally:
    """Running totals of item matches over many articles, per kind."""

    by_kind: dict[str, Counts] = field(
        default_factory=lambda: {kind: Counts() for kind in ITEM_KINDS}
    )
    numbers_compared: int = 0  # matched cases/deaths/hospitalized items
    numbers_equal: int = 0     # ... whose `number` is also the same

    def add(self, match: ItemMatch) -> None:
        for gold_item, model_item in match.matched:
            self.by_kind[gold_item["kind"]].tp += 1
            if gold_item["kind"] != "trend":
                self.numbers_compared += 1
                self.numbers_equal += gold_item["number"] == model_item["number"]
        for gold_item in match.missed:
            self.by_kind[gold_item["kind"]].fn += 1
        for model_item in match.extra:
            self.by_kind[model_item["kind"]].fp += 1

    def overall(self) -> Counts:
        """All kinds pooled together (micro average)."""
        total = Counts()
        for counts in self.by_kind.values():
            total.tp += counts.tp
            total.fp += counts.fp
            total.fn += counts.fn
        return total


# --- Item sets per article ---------------------------------------------------

# How the model's whole item list compares with the gold list for one article. The six
# outcomes cover every case exactly once; this is also the order they appear in the report.
SET_EXACT = "exact set match"
SET_BOTH_EMPTY = "exact set match, no items on either side"
SET_EXTRAS_ONLY = "model has extra items only"
SET_MISSING_ONLY = "model is missing items only"
SET_MIXED = "some items match; others are missing or extra"
SET_NO_MATCH = "items on both sides, none match"
SET_OUTCOMES = (SET_EXACT, SET_BOTH_EMPTY, SET_EXTRAS_ONLY, SET_MISSING_ONLY, SET_MIXED, SET_NO_MATCH)


def classify_item_set(match: ItemMatch) -> str:
    """Name how one article's item sets compare, from an (exact) ItemMatch.

    The sets are identical only when nothing is missing and nothing is extra. That also
    means the two sides have the same number of items.
    """
    matched, missing, extra = len(match.matched), len(match.missed), len(match.extra)
    if not missing and not extra:
        return SET_EXACT if matched else SET_BOTH_EMPTY
    if not missing:
        return SET_EXTRAS_ONLY
    if not extra:
        return SET_MISSING_ONLY
    return SET_MIXED if matched else SET_NO_MATCH


# --- Filters and intervals ---------------------------------------------------

def drop_inactive_only(items: list[dict]) -> list[dict]:
    """The planned filter for the weekly signal: an article whose only items are `inactive`
    trends counts as having no items."""
    return [] if items and all(item.get("words") == "inactive" for item in items) else items


def bootstrap_f1_interval(article_counts: list[tuple[int, int, int]], resamples: int = 1000,
                          seed: int = 20261101) -> tuple[float, float] | None:
    """95% interval for F1, resampling whole articles, because items in one article are not
    independent. `article_counts` holds (tp, fp, fn) per article. None when there are no articles."""
    if not article_counts:
        return None
    generator = random.Random(seed)
    scores = []
    for _ in range(resamples):
        tp = fp = fn = 0
        for a_tp, a_fp, a_fn in generator.choices(article_counts, k=len(article_counts)):
            tp, fp, fn = tp + a_tp, fp + a_fp, fn + a_fn
        scores.append(Counts(tp, fp, fn).f1 or 0.0)
    scores.sort()
    return scores[int(0.025 * resamples)], scores[int(0.975 * resamples) - 1]
