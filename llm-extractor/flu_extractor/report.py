"""Write the evaluation as report.md, row_results.csv and item_comparison.csv."""

import csv
from collections import Counter
from pathlib import Path

from flu_extractor import config
from flu_extractor.checks import QUOTE_EMPTY, QUOTE_NOT_FOUND, QUOTE_TYPOGRAPHY_ONLY
from flu_extractor.evaluation import (
    API_ERROR, MALFORMED, SCORED, UNPARSEABLE, Evaluation, RowResult,
)
from flu_extractor.metrics import (
    ITEM_KINDS,
    SET_BOTH_EMPTY,
    SET_EXACT,
    SET_OUTCOMES,
    Counts,
    ItemTally,
    classify_item_set,
    differing_fields,
)

# In item_comparison.csv, items that are paired always agree on the first group of fields;
# the second group is shown for the human and the model side by side.
_SHARED_COLUMNS = ("kind", "strain", "city", "state", "country")
_SIDE_BY_SIDE_COLUMNS = ("number", "status", "total_or_new", "start_date", "end_date", "words")


def _fmt(value: float | None) -> str:
    """Format a rate as a percentage with one decimal, or 'n/a'."""
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _scores_row(label: str, counts: Counts) -> str:
    return (f"| {label} | {counts.tp} | {counts.fp} | {counts.fn} | "
            f"{_fmt(counts.precision)} | {_fmt(counts.recall)} | {_fmt(counts.f1)} |")


def _item_table(tally: ItemTally) -> list[str]:
    """Markdown table of precision/recall/F1 per kind, plus the pooled row."""
    lines = [
        "| Kind | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [_scores_row(kind, tally.by_kind[kind]) for kind in ITEM_KINDS]
    lines.append(_scores_row("**all kinds**", tally.overall()))
    return lines


def _usefulness_section(evaluation: Evaluation) -> list[str]:
    result = evaluation.usefulness
    counts = result.counts
    return [
        "## 1. Usefulness classification",
        "",
        "Positive class = *useful*. Human label is the truth.",
        "",
        "| | Model: useful | Model: not useful |",
        "|---|---|---|",
        f"| **Human: useful** | {counts.tp} (TP) | {counts.fn} (FN, missed) |",
        f"| **Human: not useful** | {counts.fp} (FP, false alarm) | {result.true_negatives} (TN) |",
        "",
        f"- Precision: **{_fmt(counts.precision)}**  Recall: **{_fmt(counts.recall)}**  "
        f"F1: **{_fmt(counts.f1)}**  Accuracy: **{_fmt(result.accuracy)}**",
        "",
    ]


def _item_set_lines(scored: list[RowResult]) -> list[str]:
    """How the model's whole item list compares with the human's, article by article."""
    outcomes = Counter(classify_item_set(r.exact_match) for r in scored)
    total = len(scored)
    same_count = sum(len(r.human_items) == len(r.model_items) for r in scored)
    exact_sets = outcomes[SET_EXACT] + outcomes[SET_BOTH_EMPTY]
    with_items = [r for r in scored if r.human_items]
    exact_with_items = sum(classify_item_set(r.exact_match) == SET_EXACT for r in with_items)
    lines = [
        "| What the model's item list looks like, compared with the human's | Articles |",
        "|---|---|",
        *[f"| {outcome} | {outcomes[outcome]} |" for outcome in SET_OUTCOMES],
        f"| **all scored articles** | **{total}** |",
        "",
        f"- Exact set match (same items, same number of items): **{exact_sets} of {total}** "
        f"({_fmt(exact_sets / total if total else None)}).",
        f"- Only articles where the human found items: **{exact_with_items} of {len(with_items)}** "
        f"({_fmt(exact_with_items / len(with_items) if with_items else None)}). "
        "This is the harder, more informative figure, because \"no items on either side\" is easy.",
        f"- Same number of items on both sides: **{same_count} of {total}**.",
        "",
    ]
    return lines


def _items_section(evaluation: Evaluation) -> list[str]:
    exact, strict = evaluation.exact_items, evaluation.strict_items
    scored = evaluation.rows_with_status(SCORED)
    human_total = exact.overall().tp + exact.overall().fn
    model_total = exact.overall().tp + exact.overall().fp
    return [
        "## 2. Item correctness",
        "",
        "Every scored article is included: items the model writes for a not-useful article are extras. "
        "Evidence is never compared, because the model and the labeler may quote different sentences "
        "for the same fact.",
        "",
        "### 2.1 Exact item match",
        "",
        "A model item is an **exact match** when kind, strain, number, status, total_or_new, city, state, "
        "country, start_date, end_date and words all agree with a human item (case and repeated spaces "
        "are ignored). Each human item can be matched once.",
        "",
        "In this table **TP** = exact matches, **FP** = extra items (written by the model, no exact human "
        "counterpart), **FN** = missing items (written by the human, no exact model counterpart).",
        "",
        *_item_table(exact),
        "",
        f"- Human items: **{human_total}**. Model items: **{model_total}**. Exact matches: "
        f"**{exact.overall().tp}**. Missing from the model: **{exact.overall().fn}**. "
        f"Extra from the model: **{exact.overall().fp}**.",
        "",
        "### 2.2 Item sets per article",
        "",
        "For each article: is the model's whole item list identical to the human's?",
        "",
        *_item_set_lines(scored),
        "`item_comparison.csv` lists every item with its outcome, and for near-misses the fields that differ.",
        "",
        "### 2.3 Looser comparisons (to see where the misses come from)",
        "",
        "**Kind, place, strain and dates agree** (number, status, total_or_new and words are not compared):",
        "",
        *_item_table(strict),
        "",
        f"- Among matched cases/deaths/hospitalized items, the `number` also agrees in "
        f"**{strict.numbers_equal} of {strict.numbers_compared}**.",
        "",
        "**Kind, place and strain agree** (dates are also ignored). A big gap to the table above means most "
        "misses are date errors, not wrong places or strains:",
        "",
        *_item_table(evaluation.relaxed_items),
        "",
    ]


def _evidence_check_lines(scored: list[RowResult]) -> list[str]:
    """Rule (a) in plain numbers: how many quoted passages are not exact copies of the article."""
    quotes_checked = sum(len(item["evidence"]) for r in scored for item in r.model_items)
    problems = [v for r in scored for v in r.violations if v.startswith("(a)")]
    invented = sum(QUOTE_NOT_FOUND in v for v in problems)
    typography = sum(QUOTE_TYPOGRAPHY_ONLY in v for v in problems)
    empty = sum(QUOTE_EMPTY in v for v in problems)
    articles_affected = sorted({r.article_id for r in scored if any(v.startswith("(a)") for v in r.violations)})
    return [
        "### Evidence is copied from the article (rule a)",
        "",
        f"Every evidence quote the model wrote ({quotes_checked} in total) is looked "
        "up in the article text. Line breaks and repeated spaces are ignored; nothing else.",
        "",
        f"- Not found in the article (reworded, shortened, joined from separate places or invented): **{invented}**",
        f"- Found only after treating curly and straight quotes or dashes as the same (words right, copy not exact): **{typography}**",
        f"- Empty: **{empty}**",
        f"- Articles affected: {', '.join(articles_affected) if articles_affected else 'none'}",
        "",
        "The check shows that the text exists in the article. It cannot show that the quote supports the item.",
        "",
    ]


def _rule_check_section(evaluation: Evaluation) -> list[str]:
    scored = evaluation.rows_with_status(SCORED)
    rule_counts = Counter(v[:3] for r in scored for v in r.violations)  # e.g. "(a)"
    rows_with_violations = sum(1 for r in scored if r.violations)
    lines = [
        "## 3. Automatic rule checks (prompt section 5, step 3)",
        "",
        f"{rows_with_violations} of {len(scored)} scored articles have at least one violation.",
        "",
        *_evidence_check_lines(scored),
    ]
    if rule_counts:
        lines += ["| Rule | Violations |", "|---|---|"]
        lines += [f"| {rule} | {count} |" for rule, count in sorted(rule_counts.items())]
        lines.append("")
    return lines


def _coverage_section(evaluation: Evaluation) -> list[str]:
    """How many articles could not be scored, and why."""
    lines = [
        "## 4. Coverage",
        "",
        f"- Articles in the run with a human label: **{len(evaluation.rows)}**",
        f"- Scored: **{len(evaluation.rows_with_status(SCORED))}**",
    ]
    for status, meaning in (
        (API_ERROR, "API call failed after retries"),
        (UNPARSEABLE, "reply was not valid JSON or was cut off"),
        (MALFORMED, "valid JSON that breaks the reply schema"),
    ):
        failed = evaluation.rows_with_status(status)
        if failed:
            ids = ", ".join(r.article_id for r in failed)
            lines.append(f"- Not scored, {status} ({meaning}): **{len(failed)}** - articles {ids}")
    lines.append("")
    lines.append("Articles that are not scored are left out of every number above, so they do not hurt the scores. "
                 "Retry them before trusting the results.")
    lines.append("")
    return lines


def _split_text(evaluation: Evaluation) -> str:
    """Which split(s) the run's articles come from, e.g. '**dev** (380 articles)'."""
    counts = Counter(r.split for r in evaluation.rows)
    return ", ".join(f"**{split}** ({count} articles)" for split, count in sorted(counts.items())) or "none"


def write_report(evaluation: Evaluation, run_dir: Path, run_info: dict[str, str] | None = None) -> None:
    """Write all three report files into the run folder.

    run_info: the run's prompt, examples and labels file names (default: what config uses now)."""
    info = run_info or {"system_prompt": config.SYSTEM_PROMPT_PATH.name, "examples": config.EXAMPLES_PATH.name,
                        "labels": config.HUMAN_LABELS_PATH.name}
    sections = [
        f"# Extraction report: {run_dir.name}",
        "",
        f"Model: `{config.MODEL_ID}`  |  Prompt: `{info['system_prompt']}` "
        f"+ `{info['examples']}`  |  Labels: `{info['labels']}`  |  Split: {_split_text(evaluation)}",
        "",
        *_usefulness_section(evaluation),
        *_items_section(evaluation),
        *_rule_check_section(evaluation),
        *_coverage_section(evaluation),
    ]
    (run_dir / "report.md").write_text("\n".join(sections), encoding="utf-8")
    _write_row_results(evaluation.rows, run_dir / "row_results.csv")
    _write_item_comparison(evaluation.rows, run_dir / "item_comparison.csv")


def _write_row_results(rows: list[RowResult], path: Path) -> None:
    """One line per article: what the human and the model said, and how the items compare."""
    columns = ["article_id", "labeler", "split", "status", "human_useful", "model_useful", "usefulness_correct",
               "borderline", "human_items", "model_items", "items_exact_matched", "items_missing",
               "items_extra", "item_set_outcome", "rule_violations", "problems", "model_reason"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            scored = r.status == SCORED
            writer.writerow({
                "article_id": r.article_id, "labeler": r.labeler, "split": r.split, "status": r.status,
                "human_useful": r.human_useful,
                "model_useful": r.model_useful if scored else "",
                "usefulness_correct": (r.human_useful == r.model_useful) if scored else "",
                "borderline": r.borderline if scored else "",
                "human_items": len(r.human_items),
                "model_items": len(r.model_items) if scored else "",
                "items_exact_matched": len(r.exact_match.matched) if scored else "",
                "items_missing": len(r.exact_match.missed) if scored else "",
                "items_extra": len(r.exact_match.extra) if scored else "",
                "item_set_outcome": classify_item_set(r.exact_match) if scored else "",
                "rule_violations": " | ".join(r.violations),
                "problems": " | ".join(r.problems),
                "model_reason": r.model_reason,
            })


def _evidence_text(item: dict | None) -> str:
    """The quotes of an item in one cell, separated by ' || '. Empty when there is no item."""
    return " || ".join(item["evidence"]) if item else ""


def _write_item_comparison(rows: list[RowResult], path: Path) -> None:
    """Every human and model item, one line each pair, with the evidence each of them quoted.

    outcome is one of:
      exact match               every field except evidence agrees
      same kind and place       the items are alike but some fields differ; `differing_fields`
                                lists them and the side-by-side columns show the values
      missing from model        a human item with no model counterpart (model columns empty)
      extra from model          a model item with no human counterpart (human columns empty)
    Evidence is shown for learning how the two differ; it is never part of the score.
    """
    side_by_side = [f"{side}_{name}" for name in _SIDE_BY_SIDE_COLUMNS for side in ("human", "model")]
    columns = ["article_id", "labeler", "split", "outcome", "differing_fields", *_SHARED_COLUMNS, *side_by_side,
               "human_evidence", "model_evidence"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            if r.status != SCORED:
                continue
            pairs = (
                [("exact match", human, model) for human, model in r.exact_match.matched]
                + [("same kind and place", human, model) for human, model in r.near_match.matched]
                + [("missing from model", human, None) for human in r.near_match.missed]
                + [("extra from model", None, model) for model in r.near_match.extra]
            )
            for outcome, human, model in pairs:
                shared = human or model  # paired items agree on the shared fields, so either side will do
                line = {
                    "article_id": r.article_id, "labeler": r.labeler, "split": r.split, "outcome": outcome,
                    "differing_fields": ", ".join(differing_fields(human, model)) if human and model else "",
                    **{name: shared.get(name) for name in _SHARED_COLUMNS},
                    "human_evidence": _evidence_text(human),
                    "model_evidence": _evidence_text(model),
                }
                for name in _SIDE_BY_SIDE_COLUMNS:
                    line[f"human_{name}"] = human[name] if human else ""
                    line[f"model_{name}"] = model[name] if model else ""
                writer.writerow(line)
