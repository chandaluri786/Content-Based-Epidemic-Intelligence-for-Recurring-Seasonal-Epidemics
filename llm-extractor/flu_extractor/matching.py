"""Pair gold items with model items inside one article.

Steps (matching_v3):
  1. Candidate pairs: the same country, and either the same kind, or two count kinds with the same
     number (a count told under the wrong kind, such as a hospitalization written as cases). A trend
     never pairs with a count, and items in different countries never pair.
  2. Similarity of a candidate pair: the share of the gold kind's applicable fields that agree,
     kind included, with equal weights (normalization.applicable_fields). This is also the pair's
     accuracy (field_scoring.PairScore.accuracy): the same fields, compared the same way.
  3. Pairs below MATCH_THRESHOLD (0.8) are not allowed: at most 2 of a count's 10 fields, or 1 of a
     trend's 8 fields, may disagree.
  4. Best partners first (one to one): repeatedly lock the allowed pair with the highest similarity
     among the items not yet paired; both of its items are then used up. A strong pair is never
     given up to make room for more, weaker pairs, so every locked pair is the closest match still
     available to both of its items.
  5. Ties at the highest similarity: lock the pair whose two items have the fewest other allowed
     partners still available (this leaves more good pairs for the rest); if that ties too, the
     first gold item, then the first model item, in article order. The result is always the same.
  6. Same-kind pairs are locked first; kind-confusion pairs only among the items left after that.
     Items with no allowed partner left stay unpaired: a gold item is a miss, a model item an extra.
"""

from dataclasses import dataclass, field

from flu_extractor.normalization import COUNT_KINDS, applicable_fields, normalize_item

MATCHING_VERSION = "matching_v3"
MATCH_THRESHOLD = 0.8


def is_candidate(gold: dict, model: dict) -> bool:
    """Rule 1 above, on normalized items."""
    if gold["country"] != model["country"]:
        return False
    if gold["kind"] == model["kind"]:
        return True
    both_counts = gold["kind"] in COUNT_KINDS and model["kind"] in COUNT_KINDS
    return both_counts and gold["number"] is not None and gold["number"] == model["number"]


def compatibility(gold: dict, model: dict) -> float:
    """Rule 2 above, on normalized items: the share of the gold kind's fields that agree (the similarity)."""
    fields = applicable_fields(gold["kind"])
    return sum(gold[name] == model[name] for name in fields) / len(fields)


def best_first_pairs(candidates: dict[tuple[int, int], float]) -> list[tuple[int, int]]:
    """Steps 4 and 5 above. `candidates` maps (gold index, model index) to the similarity of an
    allowed pair. Returns the locked pairs, in the order they were locked."""
    available = dict(candidates)
    locked = []
    while available:
        best = max(available.values())
        tied = [pair for pair, score in available.items() if abs(score - best) < 1e-9]

        def other_options(pair):
            g, m = pair
            return sum(1 for other in available if other != pair and (other[0] == g or other[1] == m))

        g, m = min(tied, key=lambda pair: (other_options(pair), pair))
        locked.append((g, m))
        available = {pair: score for pair, score in available.items() if pair[0] != g and pair[1] != m}
    return locked


@dataclass
class ArticleMatch:
    """The result of matching one article's items. Indexes refer to the original item lists."""

    pairs: list[tuple[int, int, float]]              # (gold index, model index, compatibility)
    unmatched_gold: list[int]
    unmatched_model: list[int]
    rejected: list[tuple[int, int, float]] = field(default_factory=list)  # per miss: its closest model item
    matrix: list[list[float | None]] = field(default_factory=list)       # None = not a candidate pair


def match_article(gold_items: list[dict], model_items: list[dict],
                  threshold: float = MATCH_THRESHOLD) -> ArticleMatch:
    """Steps 1-6 above for one article."""
    gold = [normalize_item(item) for item in gold_items]
    model = [normalize_item(item) for item in model_items]
    matrix = [[compatibility(g, m) if is_candidate(g, m) else None for m in model] for g in gold]
    pairs: list[tuple[int, int, float]] = []
    matched_gold: set[int] = set()
    matched_model: set[int] = set()
    for same_kind in (True, False):
        allowed = {(g, m): score for g, row in enumerate(matrix) for m, score in enumerate(row)
                   if score is not None and score >= threshold and g not in matched_gold
                   and m not in matched_model and (gold[g]["kind"] == model[m]["kind"]) == same_kind}
        for g, m in best_first_pairs(allowed):
            pairs.append((g, m, matrix[g][m]))
            matched_gold.add(g)
            matched_model.add(m)
    pairs.sort()
    rejected = []
    for g, row in enumerate(matrix):
        if g in matched_gold:
            continue
        # The closest model item of a miss: below the threshold, or locked to another gold item first.
        options = [(score, m) for m, score in enumerate(row) if score is not None]
        if options:
            score, m = max(options)
            rejected.append((g, m, score))
    return ArticleMatch(
        pairs=pairs,
        unmatched_gold=[g for g in range(len(gold)) if g not in matched_gold],
        unmatched_model=[m for m in range(len(model)) if m not in matched_model],
        rejected=rejected,
        matrix=matrix,
    )
