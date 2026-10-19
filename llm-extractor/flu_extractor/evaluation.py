"""Compare a run's model replies with the human labels."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from flu_extractor.checks import find_rule_violations, find_shape_errors
from flu_extractor.data_loading import Article, HumanLabel
from flu_extractor.metrics import (
    EXACT_KEY_FIELDS,
    RELAXED_KEY_FIELDS,
    STRICT_KEY_FIELDS,
    ItemMatch,
    ItemTally,
    UsefulnessResult,
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

    row: int
    article_id: str
    status: str
    human_useful: bool
    model_useful: bool | None = None
    model_reason: str = ""
    borderline: bool | None = None
    problems: list[str] = field(default_factory=list)    # why the row was not scored
    violations: list[str] = field(default_factory=list)  # rule violations (checks a-g)
    human_items: list[dict] = field(default_factory=list)
    model_items: list[dict] = field(default_factory=list)
    model_findings: list[dict] = field(default_factory=list)
    exact_match: ItemMatch | None = None  # human vs model items, every field but evidence must agree
    near_match: ItemMatch | None = None   # the leftovers of exact_match, paired by kind and place


@dataclass
class Evaluation:
    """All results of evaluating one run."""

    rows: list[RowResult]
    usefulness: UsefulnessResult
    exact_items: ItemTally    # headline: every field except evidence agrees
    strict_items: ItemTally   # kind, place, strain and dates agree
    relaxed_items: ItemTally  # kind, place and strain agree

    def rows_with_status(self, status: str) -> list[RowResult]:
        return [r for r in self.rows if r.status == status]


def read_run_records(log_path: Path) -> dict[int, dict]:
    """Read a run's raw_results.jsonl into {row: record}. A later line for a row replaces an earlier one."""
    records: dict[int, dict] = {}
    with log_path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                records[record["row"]] = record
    return records


def evaluate_run(
    records: dict[int, dict],
    articles: dict[int, Article],
    labels: dict[int, HumanLabel],
    place_checker: PlaceChecker,
) -> Evaluation:
    """Score every record in the run against the human labels."""
    row_results = []
    for row in sorted(records):
        label = labels.get(row)
        if label is None or label.useful is None:
            continue  # nothing to compare with (rows 109 and 152)
        row_results.append(_evaluate_row(records[row], articles[row], label, place_checker))

    scored = [r for r in row_results if r.status == SCORED]
    usefulness = score_usefulness([(r.human_useful, r.model_useful) for r in scored])
    exact_items, strict_items, relaxed_items = ItemTally(), ItemTally(), ItemTally()
    for result in scored:
        exact_items.add(result.exact_match)
        strict_items.add(match_items(result.human_items, result.model_items, STRICT_KEY_FIELDS))
        relaxed_items.add(match_items(result.human_items, result.model_items, RELAXED_KEY_FIELDS))
    return Evaluation(row_results, usefulness, exact_items, strict_items, relaxed_items)


def _evaluate_row(record: dict, article: Article, label: HumanLabel,
                  place_checker: PlaceChecker) -> RowResult:
    """Classify one record (scored or failed) and, if scorable, run the checks and item matching."""
    human_items = label.items
    result = RowResult(
        row=record["row"],
        article_id=label.article_id,
        status=SCORED,
        human_useful=label.useful,
        human_items=human_items,
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
    result.borderline = parsed["borderline"]
    result.model_items = parsed["items"]
    result.model_findings = parsed["findings"]
    result.violations = find_rule_violations(parsed, article.text, place_checker)
    result.exact_match = match_items(human_items, parsed["items"], EXACT_KEY_FIELDS)
    # Items left over after the exact comparison: pair those of the same kind and place, so that
    # the report can show which fields differ instead of listing one missing and one extra item.
    result.near_match = match_items(result.exact_match.missed, result.exact_match.extra, RELAXED_KEY_FIELDS)
    return result


def default_rows_to_run(
    labels: dict[int, HumanLabel],
    example_rows: frozenset[int],
    extra_excluded_rows: frozenset[int] = frozenset(),
) -> list[int]:
    """The rows to run and score. A row is left out when it:
      - has no human label (useful is None),
      - is marked needs_relook (the labeler is unsure),
      - is one of the solved examples inside the prompt (the model has seen its answer), or
      - is in the extra exclusion set.
    """
    skipped = example_rows | extra_excluded_rows
    return sorted(
        row for row, label in labels.items()
        if label.useful is not None and not label.needs_relook and row not in skipped
    )
