"""Compare a run's model replies with the gold labels."""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from flu_extractor.checks import find_rule_violations, find_shape_errors
from flu_extractor.data_loading import Article, GoldLabel
from flu_extractor.metrics import (
    EXACT_KEY_FIELDS,
    RELAXED_KEY_FIELDS,
    STRICT_KEY_FIELDS,
    WEEKLY_KEY_FIELDS,
    Counts,
    ItemMatch,
    ItemTally,
    UsefulnessResult,
    bootstrap_f1_interval,
    differing_fields,
    drop_inactive_only,
    match_items,
    score_usefulness,
)
from flu_extractor.places import PlaceChecker

# Row statuses. Only "scored" rows enter the metrics.
SCORED = "scored"
API_ERROR = "api_error"        # the call failed after all retries
UNPARSEABLE = "unparseable"    # the reply was not valid JSON (or was cut off)
MALFORMED = "malformed"        # valid JSON, but it breaks the reply schema


@dataclass
class RowResult:
    """Everything we know about one scored article."""

    article_id: str
    sources: tuple[str, ...]
    status: str
    gated: bool
    gold_useful: bool
    human_useful: bool | None = None
    model_useful: bool | None = None
    model_reason: str = ""
    problems: list[str] = field(default_factory=list)    # why the row was not scored
    violations: list[str] = field(default_factory=list)  # rule violations
    gold_items: list[dict] = field(default_factory=list)
    model_items: list[dict] = field(default_factory=list)
    exact_match: ItemMatch | None = None  # gold vs model items, every field but evidence must agree
    near_match: ItemMatch | None = None   # the leftovers of exact_match, paired by kind and place


@dataclass
class Scores:
    """One set of scores over a group of scored articles."""

    articles: int
    usefulness: UsefulnessResult
    exact_items: ItemTally    # headline: every field except evidence agrees
    strict_items: ItemTally   # kind, place, strain and dates agree
    relaxed_items: ItemTally  # kind, place and strain agree
    weekly_items: ItemTally   # kind, strain, country and ISO week agree
    useful_interval: tuple[float, float] | None  # 95% interval for usefulness F1
    exact_interval: tuple[float, float] | None   # 95% interval for exact item F1


@dataclass
class Evaluation:
    """All results of evaluating one run."""

    rows: list[RowResult]
    all_articles: Scores      # every scored article
    model_articles: Scores    # only articles that reached the model
    without_inactive: Scores  # model_articles with inactive-only articles filtered on both sides
    field_agreement: dict[str, tuple[int, int]]  # field -> (equal, compared) on paired items
    by_country: dict[str, Counts]                # exact matches per country
    human_vs_model: UsefulnessResult             # model against the human useful answers
    human_vs_gold: UsefulnessResult              # gold against the human useful answers

    @property
    def usefulness(self) -> UsefulnessResult:
        return self.model_articles.usefulness

    def rows_with_status(self, status: str) -> list[RowResult]:
        return [r for r in self.rows if r.status == status]


def read_run_records(log_path: Path) -> dict[str, dict]:
    """Read a run's raw_results.jsonl into {article_id: record}. A later line replaces an earlier one."""
    records: dict[str, dict] = {}
    with log_path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                records[record["article_id"]] = record
    return records


def score_articles(pairs: list[tuple[list[dict], list[dict]]]) -> Scores:
    """Score (gold items, model items) pairs, one pair per article."""
    exact, strict, relaxed, weekly = ItemTally(), ItemTally(), ItemTally(), ItemTally()
    exact_counts = []
    for gold_items, model_items in pairs:
        exact_match = match_items(gold_items, model_items, EXACT_KEY_FIELDS)
        exact.add(exact_match)
        strict.add(match_items(gold_items, model_items, STRICT_KEY_FIELDS))
        relaxed.add(match_items(gold_items, model_items, RELAXED_KEY_FIELDS))
        weekly.add(match_items(gold_items, model_items, WEEKLY_KEY_FIELDS))
        exact_counts.append((len(exact_match.matched), len(exact_match.extra), len(exact_match.missed)))
    useful_pairs = [(bool(gold_items), bool(model_items)) for gold_items, model_items in pairs]
    useful_counts = [(int(g and m), int(m and not g), int(g and not m)) for g, m in useful_pairs]
    return Scores(
        articles=len(pairs),
        usefulness=score_usefulness(useful_pairs),
        exact_items=exact, strict_items=strict, relaxed_items=relaxed, weekly_items=weekly,
        useful_interval=bootstrap_f1_interval(useful_counts),
        exact_interval=bootstrap_f1_interval(exact_counts),
    )


def evaluate_run(
    records: dict[str, dict],
    articles: dict[str, Article],
    gold_labels: dict[str, GoldLabel],
    human_useful: dict[str, bool | None],
    place_checker: PlaceChecker,
) -> Evaluation:
    """Score every record in the run against the gold labels."""
    rows = [
        _evaluate_row(records[article_id], articles[article_id], gold_labels[article_id],
                      human_useful.get(article_id), place_checker)
        for article_id in sorted(records) if article_id in gold_labels
    ]
    scored = [r for r in rows if r.status == SCORED]
    reached_model = [r for r in scored if not r.gated]
    with_human = [r for r in reached_model if r.human_useful is not None]
    return Evaluation(
        rows=rows,
        all_articles=score_articles([(r.gold_items, r.model_items) for r in scored]),
        model_articles=score_articles([(r.gold_items, r.model_items) for r in reached_model]),
        without_inactive=score_articles([(drop_inactive_only(r.gold_items), drop_inactive_only(r.model_items))
                                         for r in reached_model]),
        field_agreement=_field_agreement(reached_model),
        by_country=_exact_by_country(reached_model),
        human_vs_model=score_usefulness([(r.human_useful, r.model_useful) for r in with_human]),
        human_vs_gold=score_usefulness([(r.human_useful, r.gold_useful) for r in with_human]),
    )


def _field_agreement(rows: list[RowResult]) -> dict[str, tuple[int, int]]:
    """On items paired with a gold item, how often each field agrees."""
    equal, compared = Counter(), Counter()
    for result in rows:
        for gold_item, model_item in [*result.exact_match.matched, *result.near_match.matched]:
            different = differing_fields(gold_item, model_item)
            for name in EXACT_KEY_FIELDS:
                compared[name] += 1
                equal[name] += name not in different
    return {name: (equal[name], compared[name]) for name in EXACT_KEY_FIELDS}


def _exact_by_country(rows: list[RowResult]) -> dict[str, Counts]:
    """Exact matches, missing items and extra items for each country."""
    counts: dict[str, Counts] = {}
    def tally(item: dict) -> Counts:
        return counts.setdefault(item.get("country") or "(none)", Counts())
    for result in rows:
        for gold_item, _ in result.exact_match.matched:
            tally(gold_item).tp += 1
        for model_item in result.exact_match.extra:
            tally(model_item).fp += 1
        for gold_item in result.exact_match.missed:
            tally(gold_item).fn += 1
    return dict(sorted(counts.items(), key=lambda pair: -(pair[1].tp + pair[1].fn)))


def _evaluate_row(record: dict, article: Article, label: GoldLabel, human_useful: bool | None,
                  place_checker: PlaceChecker) -> RowResult:
    """Classify one record (scored or failed) and, if scorable, run the checks and item matching."""
    result = RowResult(
        article_id=label.article_id,
        sources=article.sources,
        status=SCORED,
        gated=record.get("gated", False),
        gold_useful=label.useful,
        human_useful=human_useful,
        gold_items=label.items,
    )

    if record["api_error"]:
        result.status, result.problems = API_ERROR, [record["api_error"]]
        return result
    parsed = record["parsed"]
    if parsed is None:
        result.status, result.problems = UNPARSEABLE, [record["parse_error"] or "no parsed reply"]
        return result
    shape_errors = find_shape_errors(parsed)
    if shape_errors:
        result.status, result.problems = MALFORMED, shape_errors
        return result

    result.model_useful = parsed["useful"]
    result.model_reason = parsed["reason"]
    result.model_items = parsed["items"]
    result.violations = find_rule_violations(parsed, article.text, article.scan_date, place_checker)
    result.exact_match = match_items(label.items, parsed["items"], EXACT_KEY_FIELDS)
    # Items left over after the exact comparison: pair those of the same kind and place, so that
    # the report can show which fields differ instead of listing one missing and one extra item.
    result.near_match = match_items(result.exact_match.missed, result.exact_match.extra, RELAXED_KEY_FIELDS)
    return result


def default_articles_to_run(
    articles: dict[str, Article],
    gold_labels: dict[str, GoldLabel],
    split: str,
    example_ids: frozenset[str],
    extra_excluded_ids: frozenset[str] = frozenset(),
) -> list[str]:
    """The articles to run and score. An article is left out when it:
      - belongs to the other split,
      - has no gold label yet,
      - is one of the solved examples in the examples file (the model would see its answer), or
      - is in the extra exclusion set.
    """
    skipped = example_ids | extra_excluded_ids
    return sorted(
        article_id for article_id, article in articles.items()
        if article.split == split and article_id in gold_labels and article_id not in skipped
    )
