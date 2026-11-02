"""Write the evaluation as report.md, row_results.csv and item_comparison.csv."""

import csv
import json
from collections import Counter
from pathlib import Path

from flu_extractor import config
from flu_extractor.checks import QUOTE_EMPTY, QUOTE_NOT_FOUND, QUOTE_TYPOGRAPHY_ONLY
from flu_extractor.evaluation import (
    API_ERROR, MALFORMED, SCORED, UNPARSEABLE, Evaluation, RowResult, Scores,
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
# the second group is shown for gold and the model side by side.
_SHARED_COLUMNS = ("kind", "strain", "city", "state", "country")
_SIDE_BY_SIDE_COLUMNS = ("number", "count_type", "status", "start_date", "end_date", "words")


def _fmt(value: float | None) -> str:
    """Format a rate as a percentage with one decimal, or 'n/a'."""
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _interval(interval: tuple[float, float] | None) -> str:
    """Format a 95% interval, or 'n/a'."""
    return "n/a" if interval is None else f"{_fmt(interval[0])} to {_fmt(interval[1])}"


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
    scores = evaluation.model_articles
    counts = scores.usefulness.counts
    return [
        "## 1. Usefulness classification",
        "",
        "Positive class = *useful*. Gold is the chain-of-thought records. Articles rejected by the keyword "
        "gate are left out here, because code decides them, not the model. Section 5 shows them included.",
        "",
        "| | Model: useful | Model: not useful |",
        "|---|---|---|",
        f"| **Gold: useful** | {counts.tp} (TP) | {counts.fn} (FN, missed) |",
        f"| **Gold: not useful** | {counts.fp} (FP, false alarm) | {scores.usefulness.true_negatives} (TN) |",
        "",
        f"- Precision: **{_fmt(counts.precision)}**  Recall: **{_fmt(counts.recall)}**  "
        f"F1: **{_fmt(counts.f1)}** (95% interval {_interval(scores.useful_interval)})  "
        f"Accuracy: **{_fmt(scores.usefulness.accuracy)}**",
        "",
    ]


def _item_set_lines(scored: list[RowResult]) -> list[str]:
    """How the model's whole item list compares with the gold list, article by article."""
    outcomes = Counter(classify_item_set(r.exact_match) for r in scored)
    total = len(scored)
    same_count = sum(len(r.gold_items) == len(r.model_items) for r in scored)
    exact_sets = outcomes[SET_EXACT] + outcomes[SET_BOTH_EMPTY]
    with_items = [r for r in scored if r.gold_items]
    exact_with_items = sum(classify_item_set(r.exact_match) == SET_EXACT for r in with_items)
    lines = [
        "| What the model's item list looks like, compared with gold | Articles |",
        "|---|---|",
        *[f"| {outcome} | {outcomes[outcome]} |" for outcome in SET_OUTCOMES],
        f"| **all scored articles** | **{total}** |",
        "",
        f"- Exact set match (same items, same number of items): **{exact_sets} of {total}** "
        f"({_fmt(exact_sets / total if total else None)}).",
        f"- Only articles where gold has items: **{exact_with_items} of {len(with_items)}** "
        f"({_fmt(exact_with_items / len(with_items) if with_items else None)}). "
        "This is the harder, more informative figure, because \"no items on either side\" is easy.",
        f"- Same number of items on both sides: **{same_count} of {total}**.",
        "",
    ]
    return lines


def _items_section(evaluation: Evaluation) -> list[str]:
    scores = evaluation.model_articles
    exact, strict = scores.exact_items, scores.strict_items
    scored = [r for r in evaluation.rows_with_status(SCORED) if not r.gated]
    gold_total = exact.overall().tp + exact.overall().fn
    model_total = exact.overall().tp + exact.overall().fp
    return [
        "## 2. Item correctness",
        "",
        "Every scored article that reached the model is included: items the model writes for a not-useful article are extras. "
        "Evidence is never compared, because two readers may quote different sentences "
        "for the same fact.",
        "",
        "### 2.1 Exact item match",
        "",
        "A model item is an **exact match** when kind, number, count_type, status, strain, city, state, "
        "country, start_date, end_date and words all agree with a gold item (case and repeated spaces "
        "are ignored). Each gold item can be matched once.",
        "",
        "In this table **TP** = exact matches, **FP** = extra items (written by the model, no exact gold "
        "counterpart), **FN** = missing items (in gold, no exact model counterpart).",
        "",
        *_item_table(exact),
        "",
        f"- Gold items: **{gold_total}**. Model items: **{model_total}**. Exact matches: "
        f"**{exact.overall().tp}**. Missing from the model: **{exact.overall().fn}**. "
        f"Extra from the model: **{exact.overall().fp}**. F1 95% interval: {_interval(scores.exact_interval)}.",
        "",
        "### 2.2 Item sets per article",
        "",
        "For each article: is the model's whole item list identical to the gold list?",
        "",
        *_item_set_lines(scored),
        "`item_comparison.csv` lists every item with its outcome, and for near-misses the fields that differ.",
        "",
        "### 2.3 Looser comparisons (to see where the misses come from)",
        "",
        "**Kind, place, strain and dates agree** (number, count_type, status and words are not compared):",
        "",
        *_item_table(strict),
        "",
        f"- Among matched cases/deaths/hospitalized items, the `number` also agrees in "
        f"**{strict.numbers_equal} of {strict.numbers_compared}**.",
        "",
        "**Kind, place and strain agree** (dates are also ignored). A big gap to the table above means most "
        "misses are date errors, not wrong places or strains:",
        "",
        *_item_table(scores.relaxed_items),
        "",
        "**Weekly signal: kind, strain, country and ISO week of the end date agree:**",
        "",
        *_item_table(scores.weekly_items),
        "",
        "### 2.4 Agreement by field",
        "",
        "On items paired with a gold item (same kind, strain and place).",
        "",
        "| Field | Equal | Compared | Share |",
        "|---|---|---|---|",
        *[f"| {name} | {equal} | {compared} | {_fmt(equal / compared if compared else None)} |"
          for name, (equal, compared) in evaluation.field_agreement.items()],
        "",
        "### 2.5 Exact matches by country",
        "",
        "| Country | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---|---|---|---|---|---|",
        *[_scores_row(country, counts) for country, counts in evaluation.by_country.items()],
        "",
    ]


def _evidence_check_lines(scored: list[RowResult]) -> list[str]:
    """Rule (a) in plain numbers: how many quoted passages are not exact copies of the article."""
    quotes_checked = sum(len(item["evidence"]) for r in scored for item in r.model_items)
    problems = [v for r in scored for v in r.violations if v.startswith("(a)")]
    invented = sum(QUOTE_NOT_FOUND in v for v in problems)
    typography = sum(QUOTE_TYPOGRAPHY_ONLY in v for v in problems)
    empty = sum(QUOTE_EMPTY in v for v in problems)
    rows_affected = sorted({r.article_id for r in scored if any(v.startswith("(a)") for v in r.violations)})
    return [
        "### Evidence is copied from the article (rule a)",
        "",
        f"Every evidence quote the model wrote ({quotes_checked} in total) is looked "
        "up in the article text. Line breaks and repeated spaces are ignored; nothing else.",
        "",
        f"- Not found in the article (reworded, shortened, joined from separate places or invented): **{invented}**",
        f"- Found only after treating curly and straight quotes or dashes as the same (words right, copy not exact): **{typography}**",
        f"- Empty: **{empty}**",
        f"- Articles affected: {', '.join(map(str, rows_affected)) if rows_affected else 'none'}",
        "",
        "The check shows that the text exists in the article. It cannot show that the quote supports the item.",
        "",
    ]


def _rule_check_section(evaluation: Evaluation) -> list[str]:
    scored = evaluation.rows_with_status(SCORED)
    rule_counts = Counter(v[:3] for r in scored for v in r.violations)  # e.g. "(a)"
    rows_with_violations = sum(1 for r in scored if r.violations)
    lines = [
        "## 3. Automatic rule checks",
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
    gated = sum(r.gated for r in evaluation.rows)
    lines = [
        "## 4. Coverage",
        "",
        f"- Rejected by the keyword gate, no API call: **{gated}**",
        f"- Articles in the run with a gold label: **{len(evaluation.rows)}**",
        f"- Scored: **{len(evaluation.rows_with_status(SCORED))}**",
    ]
    for status, meaning in (
        (API_ERROR, "API call failed after retries"),
        (UNPARSEABLE, "reply was not valid JSON or was cut off"),
        (MALFORMED, "valid JSON that breaks the reply schema"),
    ):
        failed = evaluation.rows_with_status(status)
        if failed:
            rows = ", ".join(r.article_id for r in failed)
            lines.append(f"- Not scored, {status} ({meaning}): **{len(failed)}** - articles {rows}")
    lines.append("")
    lines.append("Rows that are not scored are left out of every number above, so they do not hurt the scores. "
                 "Retry them before trusting the results.")
    lines.append("")
    return lines


def _variant_row(label: str, scores: Scores) -> str:
    useful, exact = scores.usefulness.counts, scores.exact_items.overall()
    return (f"| {label} | {scores.articles} | {_fmt(useful.f1)} | {_interval(scores.useful_interval)} "
            f"| {_fmt(exact.f1)} | {_interval(scores.exact_interval)} |")


def _variants_section(evaluation: Evaluation) -> list[str]:
    """The headline scores under each way of counting."""
    return [
        "## 5. Scores with and without gated and inactive-only articles",
        "",
        "| Articles | Count | Usefulness F1 | Interval | Exact item F1 | Interval |",
        "|---|---|---|---|---|---|",
        _variant_row("Reached the model (headline)", evaluation.model_articles),
        _variant_row("All, including keyword gate rejections", evaluation.all_articles),
        _variant_row("Reached the model, inactive-only filtered", evaluation.without_inactive),
        "",
        "The inactive-only row treats an article whose only items are `inactive` trends as having no "
        "items, on both the gold and the model side. Intervals are 95% bootstrap intervals by article.",
        "",
    ]


def _human_section(evaluation: Evaluation) -> list[str]:
    """Usefulness against the human labels, as a second truth."""
    def line(label: str, result) -> str:
        counts = result.counts
        return (f"| {label} | {result.total} | {_fmt(counts.precision)} | {_fmt(counts.recall)} "
                f"| {_fmt(counts.f1)} | {_fmt(result.accuracy)} |")
    return [
        "## 6. Against the human labels",
        "",
        "Gold was written by Claude from the rules and reviewed by Jahnavi on disagreements. These rows "
        "use the labeler's own `useful` answer as the truth instead. Only `useful` is compared.",
        "",
        "| Compared with human labels | Articles | Precision | Recall | F1 | Accuracy |",
        "|---|---|---|---|---|---|",
        line("Model", evaluation.human_vs_model),
        line("Gold records", evaluation.human_vs_gold),
        "",
    ]


def headline_scores(evaluation: Evaluation) -> dict:
    """The numbers compare_runs.py reads from each run."""
    def pack(scores: Scores) -> dict:
        return {
            "articles": scores.articles,
            "useful_f1": scores.usefulness.counts.f1,
            "exact_item_f1": scores.exact_items.overall().f1,
            "strict_item_f1": scores.strict_items.overall().f1,
            "relaxed_item_f1": scores.relaxed_items.overall().f1,
            "weekly_item_f1": scores.weekly_items.overall().f1,
        }
    return {
        "reached_model": pack(evaluation.model_articles),
        "all_articles": pack(evaluation.all_articles),
        "without_inactive": pack(evaluation.without_inactive),
    }


def write_report(evaluation: Evaluation, run_dir: Path) -> None:
    """Write all the report files into the run folder."""
    sections = [
        f"# Extraction report: {run_dir.name}",
        "",
        f"Model: `{config.MODEL_ID}`  |  Prompt: `{config.SYSTEM_PROMPT_PATH.name}` "
        f"+ `{config.EXAMPLES_PATH.name}`",
        "",
        *_usefulness_section(evaluation),
        *_items_section(evaluation),
        *_rule_check_section(evaluation),
        *_coverage_section(evaluation),
        *_variants_section(evaluation),
        *_human_section(evaluation),
    ]
    (run_dir / "report.md").write_text("\n".join(sections), encoding="utf-8")
    (run_dir / "scores.json").write_text(json.dumps(headline_scores(evaluation), indent=2), encoding="utf-8")
    _write_row_results(evaluation.rows, run_dir / "row_results.csv")
    _write_item_comparison(evaluation.rows, run_dir / "item_comparison.csv")


def _write_row_results(rows: list[RowResult], path: Path) -> None:
    """One line per article: what gold and the model said, and how the items compare."""
    columns = ["article_id", "sources", "status", "gated", "gold_useful", "human_useful", "model_useful",
               "usefulness_correct", "gold_items", "model_items", "items_exact_matched", "items_missing",
               "items_extra", "item_set_outcome", "rule_violations", "problems", "model_reason"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            scored = r.status == SCORED
            writer.writerow({
                "article_id": r.article_id, "sources": " ".join(r.sources), "status": r.status,
                "gated": r.gated, "gold_useful": r.gold_useful, "human_useful": r.human_useful,
                "model_useful": r.model_useful if scored else "",
                "usefulness_correct": (r.gold_useful == r.model_useful) if scored else "",
                "gold_items": len(r.gold_items),
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
    """Every gold and model item, one line each pair, with the evidence each of them quoted.

    outcome is one of:
      exact match               every field except evidence agrees
      same kind and place       the items are alike but some fields differ; `differing_fields`
                                lists them and the side-by-side columns show the values
      missing from model        a gold item with no model counterpart (model columns empty)
      extra from model          a model item with no gold counterpart (gold columns empty)
    Evidence is shown for learning how the two differ; it is never part of the score.
    """
    side_by_side = [f"{side}_{name}" for name in _SIDE_BY_SIDE_COLUMNS for side in ("gold", "model")]
    columns = ["article_id", "outcome", "differing_fields", *_SHARED_COLUMNS, *side_by_side,
               "gold_evidence", "model_evidence"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            if r.status != SCORED:
                continue
            pairs = (
                [("exact match", gold, model) for gold, model in r.exact_match.matched]
                + [("same kind and place", gold, model) for gold, model in r.near_match.matched]
                + [("missing from model", gold, None) for gold in r.near_match.missed]
                + [("extra from model", None, model) for model in r.near_match.extra]
            )
            for outcome, gold, model in pairs:
                shared = gold or model  # paired items agree on the shared fields, so either side will do
                line = {
                    "article_id": r.article_id, "outcome": outcome,
                    "differing_fields": ", ".join(differing_fields(gold, model)) if gold and model else "",
                    **{name: shared.get(name) for name in _SHARED_COLUMNS},
                    "gold_evidence": _evidence_text(gold),
                    "model_evidence": _evidence_text(model),
                }
                for name in _SIDE_BY_SIDE_COLUMNS:
                    line[f"gold_{name}"] = gold[name] if gold else ""
                    line[f"model_{name}"] = model[name] if model else ""
                writer.writerow(line)
