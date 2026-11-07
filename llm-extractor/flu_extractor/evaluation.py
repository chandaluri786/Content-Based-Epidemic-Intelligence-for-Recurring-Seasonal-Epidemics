"""Compare a run's model replies with the gold labels, article by article.

Pipeline (see epidemiological_extraction_evaluation_methodology.md):
  1. validate the reply (checks.py) and normalize values (normalization.py);
  2. find duplicate candidates in gold and in the model items (duplicates.py), and build the
     adjudicated gold view from the review decisions;
  3. turn every city, state and country into its agreed form, its English name in OpenStreetMap
     (prompt 5.1, places.agreed_names), then match gold and model items one to one (matching.py);
  4. score the fields of matched pairs (field_scoring.py);
  5. classify unmatched items (missed, additional, duplicate extra) and run evidence checks;
  6. compute every metric per article, then summarise each over articles (every article weighing
     the same), with bootstrap intervals.

Usefulness (is the article useful?) is scored separately with a confusion table.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from flu_extractor.checks import find_rule_violations, find_format_errors
from flu_extractor.data_loading import Article, GoldLabel
from flu_extractor.duplicates import DUPLICATE, adjudicated_gold, classify_model_extras, find_groups
from flu_extractor.evidence import ItemEvidence, check_item
from flu_extractor.field_scoring import PairScore, score_pair
from flu_extractor.matching import ArticleMatch, match_article
from flu_extractor.metrics import (
    Counts, Distribution, UsefulnessResult, bootstrap_indexes, describe, drop_inactive_only, interval, safe_divide,
    score_usefulness,
)
from flu_extractor.normalization import ALL_FIELDS, ITEM_KINDS
from flu_extractor.places import PlaceChecker

# Row statuses. Only "scored" rows enter the metrics.
SCORED = "scored"
API_ERROR = "api_error"        # the call failed after all retries
UNPARSEABLE = "unparseable"    # the reply was not valid JSON (or was cut off)
MALFORMED = "malformed"        # valid JSON, but it breaks the reply schema


# --- One article -------------------------------------------------------------

@dataclass
class ArticleOutcome:
    """How one article's model items compare with its gold items."""

    gold_items: list[dict]
    model_items: list[dict]
    match: ArticleMatch
    pair_scores: list[PairScore]       # one per matched pair, in match.pairs order
    duplicate_extras: dict[int, str]   # unmatched model index -> REPEAT or POSSIBLE

    @property
    def tp(self) -> int:
        return len(self.match.pairs)

    @property
    def fp(self) -> int:
        return len(self.match.unmatched_model)

    @property
    def fn(self) -> int:
        return len(self.match.unmatched_gold)

    @property
    def empty_both(self) -> bool:
        return not self.gold_items and not self.model_items

    @property
    def precision(self) -> float | None:
        """None when the model wrote no items."""
        return safe_divide(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        """None when gold has no items."""
        return safe_divide(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float | None:
        """Event F1. 0 when items are on one side only; None (not applicable) when both are empty."""
        return safe_divide(2 * self.tp, 2 * self.tp + self.fp + self.fn)

    @property
    def attribute_accuracy(self) -> float | None:
        """Mean field accuracy of the matched pairs. None when nothing was matched."""
        return safe_divide(sum(p.accuracy for p in self.pair_scores), len(self.pair_scores))

    @property
    def exact_rate(self) -> float | None:
        """Share of matched pairs with every applicable field right. None when nothing was matched."""
        return safe_divide(sum(p.exact for p in self.pair_scores), len(self.pair_scores))

    def field_accuracy(self, name: str) -> float | None:
        """Share of this article's hits with field `name` right. None when no hit has the field."""
        results = [f.correct for p in self.pair_scores for f in p.fields if f.name == name]
        return safe_divide(sum(results), len(results))

    @property
    def exact_items(self) -> int:
        return sum(p.exact for p in self.pair_scores)

    @property
    def correct_fields(self) -> int:
        return sum(p.correct_fields for p in self.pair_scores)

    @property
    def applicable_fields(self) -> int:
        return sum(p.applicable for p in self.pair_scores)


def score_items(gold_items: list[dict], model_items: list[dict]) -> ArticleOutcome:
    match = match_article(gold_items, model_items)
    pair_scores = [score_pair(gold_items[g], model_items[m]) for g, m, _ in match.pairs]
    extras = classify_model_extras(model_items, {m for _, m, _ in match.pairs}, match.unmatched_model)
    return ArticleOutcome(gold_items, model_items, match, pair_scores, extras)


@dataclass
class RowResult:
    """Everything we know about one article in the run."""

    article_id: str
    sources: tuple[str, ...]
    status: str
    gold_useful: bool
    repaired: bool = False          # the accepted reply needed stray quotes escaped before parsing
    validation_retries: int = 0     # times the article was asked again because a reply was invalid
    model_useful: bool | None = None
    model_reason: str = ""
    problems: list[str] = field(default_factory=list)    # why the row was not scored
    violations: list[str] = field(default_factory=list)  # rule violations in the reply
    raw_gold_items: list[dict] = field(default_factory=list)  # as annotated
    gold_items: list[dict] = field(default_factory=list)      # adjudicated reference, places in agreed form
    gold_reviews: list[dict] = field(default_factory=list)    # duplicate candidate groups in gold
    raw_model_items: list[dict] = field(default_factory=list) # as the model wrote them
    model_items: list[dict] = field(default_factory=list)     # places in agreed form (5.1)
    outcome: ArticleOutcome | None = None
    evidence: list[ItemEvidence] = field(default_factory=list)  # one per model item

    @property
    def reference_uncertain(self) -> bool:
        """Gold has a duplicate candidate group that was not reviewed, or was left unresolved."""
        return any(r["decision"] not in ("distinct", DUPLICATE) for r in self.gold_reviews)


# --- Over articles -----------------------------------------------------------

# The per-article metrics that are combined over articles (README section 5): name -> how to read
# one article's value. Each is None for an article where it is not defined, and such articles are
# left out of that metric's summary (the summary says how many articles it covers).
ARTICLE_METRICS = {
    "recall": lambda o: o.recall,                 # defined when gold has items
    "precision": lambda o: o.precision,           # defined when the model wrote items
    "f1": lambda o: o.f1,                         # defined when either side has items
    "accuracy": lambda o: o.attribute_accuracy,   # defined when the article has a hit
    "exact_rate": lambda o: o.exact_rate,         # defined when the article has a hit
}


@dataclass
class Summary:
    """Task 2 over one set of articles (README section 5), plus the task 1 table.

    Every metric is computed per article first. Over the set, each metric is summarised with every
    article weighing the same: mean (with a 95% bootstrap interval), median, quartiles, share of
    articles at 1 and at 0, and the number of articles it covers. The pooled counts are context only.
    """

    articles: int
    gold_nonempty: int            # articles where gold has at least one item
    counts: Counts                # hits (tp), extras (fp), misses (fn) added up: context, not a score
    metrics: dict[str, Distribution]          # ARTICLE_METRICS name -> summary over articles
    fields: dict[str, Distribution]           # field name -> summary of per-article field accuracy
    duplicate_extras: int         # extras that repeat another model item (included in counts.fp)
    all_found: int                # gold has items: every gold item hit and no extras
    all_found_and_exact: int      # ... and every hit exact as well
    some_found: int               # gold has items: at least one hit, but some miss or extra
    none_found: int               # gold has items: no hit at all
    both_empty: int               # gold has no items and the model wrote none
    false_items_on_empty: int     # gold has no items, the model wrote some
    usefulness: UsefulnessResult
    intervals: dict[str, tuple[float, float] | None]   # 95% interval of each metric's mean

    @property
    def gold_empty(self) -> int:
        return self.articles - self.gold_nonempty


def _mean_of(values) -> float | None:
    defined = [v for v in values if v is not None]
    return sum(defined) / len(defined) if defined else None


def summarize(rows: list[RowResult], outcomes: list[ArticleOutcome]) -> Summary:
    """Aggregate one set of articles. `outcomes` and `rows` are in the same (article id) order."""
    gold_nonempty = [o for o in outcomes if o.gold_items]
    gold_empty = [o for o in outcomes if not o.gold_items]
    all_found = [o for o in gold_nonempty if o.fp == 0 and o.fn == 0]
    none_found = [o for o in gold_nonempty if o.tp == 0]
    samples = bootstrap_indexes(len(outcomes))
    values = {name: [read(o) for o in outcomes] for name, read in ARTICLE_METRICS.items()}
    intervals = {
        name: interval(lambda s, v=v: _mean_of(v[i] for i in s), len(outcomes), samples)
        for name, v in values.items()
    }
    intervals["useful_f1"] = interval(lambda s: score_usefulness(
        [(rows[i].gold_useful, rows[i].model_useful) for i in s]).counts.f1, len(rows), samples)
    return Summary(
        articles=len(outcomes),
        gold_nonempty=len(gold_nonempty),
        counts=Counts(sum(o.tp for o in outcomes), sum(o.fp for o in outcomes), sum(o.fn for o in outcomes)),
        metrics={name: describe(v) for name, v in values.items()},
        fields={name: describe([o.field_accuracy(name) for o in outcomes]) for name in ALL_FIELDS},
        duplicate_extras=sum(len(o.duplicate_extras) for o in outcomes),
        all_found=len(all_found),
        all_found_and_exact=sum(o.exact_items == o.tp for o in all_found),
        some_found=len(gold_nonempty) - len(all_found) - len(none_found),
        none_found=len(none_found),
        both_empty=sum(not o.model_items for o in gold_empty),
        false_items_on_empty=sum(bool(o.model_items) for o in gold_empty),
        usefulness=score_usefulness([(r.gold_useful, r.model_useful) for r in rows]),
        intervals=intervals,
    )


@dataclass
class Diagnostics:
    """Where the errors come from, over the headline population."""

    near_exact: Counter            # number of wrong fields per matched pair (0 = exact)
    wrong_combinations: Counter    # tuple of wrong fields -> pairs
    field_results: dict[str, Counter]  # field -> Counter of match / wrong / missing / extra
    kind_confusion: Counter        # (gold kind, model kind) -> matched pairs
    by_kind: dict[str, Counter]    # kind -> gold, model, matched, missed, additional, duplicate extras
    missed_by: dict[str, Counter]       # "strain" / "country" / "month" -> Counter
    additional_by: dict[str, Counter]
    gold_duplicates: Counter       # category and decision of gold candidate groups
    model_duplicates: Counter      # exact / near groups in model items; repeat / possible extras
    evidence: Counter


def diagnose(rows: list[RowResult]) -> Diagnostics:
    d = Diagnostics(Counter(), Counter(), {name: Counter() for name in ALL_FIELDS}, Counter(),
                    {kind: Counter() for kind in ITEM_KINDS}, {k: Counter() for k in ("strain", "country", "month")},
                    {k: Counter() for k in ("strain", "country", "month")}, Counter(), Counter(), Counter())
    for row in rows:
        o = row.outcome
        for (g, m, _), pair in zip(o.match.pairs, o.pair_scores):
            wrong = tuple(pair.wrong_fields)
            d.near_exact[min(len(wrong), 4)] += 1
            if wrong:
                d.wrong_combinations[wrong] += 1
            for result in pair.fields:
                d.field_results[result.name][result.result] += 1
            d.kind_confusion[(o.gold_items[g]["kind"], o.model_items[m]["kind"])] += 1
            d.by_kind[o.gold_items[g]["kind"]]["matched"] += 1
        for item in o.gold_items:
            d.by_kind.setdefault(item["kind"], Counter())["gold"] += 1
        for item in o.model_items:
            d.by_kind.setdefault(item.get("kind"), Counter())["model"] += 1
        for g in o.match.unmatched_gold:
            item = o.gold_items[g]
            d.by_kind[item["kind"]]["missed"] += 1
            _tally_place_time(d.missed_by, item)
        for m in o.match.unmatched_model:
            item = o.model_items[m]
            label = o.duplicate_extras.get(m)
            d.by_kind.setdefault(item.get("kind"), Counter())["additional"] += 1
            if label:
                d.by_kind[item.get("kind")]["duplicate extras"] += 1
            _tally_place_time(d.additional_by, item)
        for review in row.gold_reviews:
            d.gold_duplicates[f"{review['category']} group, {review['decision']}"] += 1
        for group in find_groups(o.model_items):
            d.model_duplicates[f"{group.category} group"] += 1
        for label in o.duplicate_extras.values():
            d.model_duplicates[f"extra: {label}"] += 1
        for ev in row.evidence:
            d.evidence["items"] += 1
            d.evidence["with evidence"] += ev.has_evidence
            d.evidence["verifiable"] += ev.verifiable
            d.evidence["quotes"] += ev.quotes
            d.evidence["quotes verbatim"] += ev.verbatim
            d.evidence["quotes typography only"] += ev.typography_only
            d.evidence["quotes not found"] += ev.not_found
            for name in ("number", "city", "strain"):
                value = getattr(ev, f"{name}_found")
                if value is not None:
                    d.evidence[f"{name} checked"] += 1
                    d.evidence[f"{name} found"] += value
    return d


def _tally_place_time(target: dict[str, Counter], item: dict) -> None:
    target["strain"][item.get("strain") or "(null)"] += 1
    target["country"][item.get("country") or "(null)"] += 1
    end = item.get("end_date")
    target["month"][end[:7] if isinstance(end, str) else "(null)"] += 1


@dataclass
class Evaluation:
    """All results of evaluating one run."""

    rows: list[RowResult]
    summaries: dict[str, Summary]   # population name -> scores; HEADLINE is the headline
    diagnostics: Diagnostics

    @property
    def headline(self) -> Summary:
        return self.summaries[HEADLINE]

    def rows_with_status(self, status: str) -> list[RowResult]:
        return [r for r in self.rows if r.status == status]


HEADLINE = "all_articles"
POPULATIONS = {
    HEADLINE: "every scored article (headline)",
    "without_inactive": "inactive-only items (1.3 food and monitoring fallbacks) removed on both sides",
}


def read_run_records(log_path: Path) -> dict[str, dict]:
    """Read a run's raw_results.jsonl into {article_id: record}. A later line replaces an earlier one."""
    records: dict[str, dict] = {}
    with log_path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                records[record["article_id"]] = record
    return records


def evaluate_run(
    records: dict[str, dict],
    articles: dict[str, Article],
    gold_labels: dict[str, GoldLabel],
    place_checker: PlaceChecker,
    adjudication: dict | None = None,
) -> Evaluation:
    """Score every record in the run against the (adjudicated) gold labels."""
    rows = [
        _evaluate_row(records[article_id], articles[article_id], gold_labels[article_id],
                      place_checker, adjudication or {})
        for article_id in sorted(records) if article_id in gold_labels
    ]
    scored = [r for r in rows if r.status == SCORED]
    no_inactive = [score_items(drop_inactive_only(r.gold_items), drop_inactive_only(r.model_items)) for r in scored]
    return Evaluation(
        rows=rows,
        summaries={
            HEADLINE: summarize(scored, [r.outcome for r in scored]),
            "without_inactive": summarize(scored, no_inactive),
        },
        diagnostics=diagnose(scored),
    )


def _evaluate_row(record: dict, article: Article, label: GoldLabel,
                  place_checker: PlaceChecker, adjudication: dict) -> RowResult:
    """Classify one record (scored or failed) and, if scorable, run the checks and the matching."""
    gold_items, reviews = adjudicated_gold(label.article_id, label.items, adjudication)
    # Prompt 5.1: compare places in their agreed form, so a different spelling of the same place
    # (USA / United States, Bangalore / Bengaluru) is never a scoring difference.
    gold_items = [place_checker.with_agreed_names(item) for item in gold_items]
    result = RowResult(
        article_id=label.article_id,
        sources=article.sources,
        status=SCORED,
        gold_useful=label.useful,
        raw_gold_items=label.items,
        gold_items=gold_items,
        gold_reviews=reviews,
        repaired=record.get("repaired", False),
        validation_retries=record.get("validation_retries", 0),
    )

    if record["api_error"]:
        result.status, result.problems = API_ERROR, [record["api_error"]]
        return result
    parsed = record["parsed"]
    if parsed is None:
        result.status, result.problems = UNPARSEABLE, [record["parse_error"] or "no parsed reply"]
        return result
    shape_errors = find_format_errors(parsed)
    if shape_errors:
        result.status, result.problems = MALFORMED, shape_errors
        return result

    result.model_useful = parsed["useful"]
    result.model_reason = parsed["reason"]
    result.raw_model_items = parsed["items"]
    result.model_items = [place_checker.with_agreed_names(item) for item in parsed["items"]]
    result.violations = find_rule_violations(parsed, article.text, article.scan_date, place_checker)
    result.outcome = score_items(gold_items, result.model_items)
    result.evidence = [check_item(item, article.text) for item in parsed["items"]]
    return result


def default_articles_to_run(
    articles: dict[str, Article],
    gold_labels: dict[str, GoldLabel] | None,
    example_ids: frozenset[str],
    extra_excluded_ids: frozenset[str] = frozenset(),
) -> list[str]:
    """Every article with a gold label, except the few-shot examples (the model sees their answers
    in the prompt) and any article in the extra exclusion set. Sorted by article id.

    With no gold labels (gold_labels is None, a run on unlabelled articles such as the pool), every
    article counts as selected, with the same exclusions."""
    skipped = example_ids | extra_excluded_ids
    return sorted(article_id for article_id in articles
                  if (gold_labels is None or article_id in gold_labels) and article_id not in skipped)
