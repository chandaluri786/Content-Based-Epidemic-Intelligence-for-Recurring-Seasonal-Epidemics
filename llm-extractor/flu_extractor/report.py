"""Write an evaluation into the run folder.

Files (one evaluation = one set):
  report.md                 the readable summary
  evaluation_summary.json   dataset-level metrics, settings and versions (compare_runs.py reads it)
  article_metrics.csv       one row per article: counts and article-level scores
  matched_items.csv         one row per matched gold/model pair, field by field
  missed_items.csv          unmatched gold items
  additional_items.csv      unmatched model items, with their duplicate label
  duplicate_candidates.csv  duplicate candidate groups in gold and in the model items
  field_error_summary.csv   results by field over matched pairs
  kind_error_summary.csv    gold, model, matched, missed, additional and duplicate items by kind
  error_examples.md         a few examples of each error type, for review
  plot_*.png                charts of the per-article values (flu_extractor/plots.py)
"""

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from flu_extractor import config
from flu_extractor.duplicates import DUPLICATES_VERSION, find_groups
from flu_extractor.evaluation import (
    API_ERROR, MALFORMED, SCORED, UNPARSEABLE, Evaluation, RowResult, Summary,
)
from flu_extractor.field_scoring import EXTRA_VALUE, MATCH, MISSING_VALUE, WRONG
from flu_extractor.matching import MATCH_THRESHOLD, MATCHING_VERSION
from flu_extractor.metrics import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, Distribution, safe_divide
from flu_extractor.plots import write_plots
from flu_extractor.normalization import ALL_FIELDS, ITEM_KINDS, NORMALIZATION_VERSION, applicable_fields, show

EVALUATION_VERSION = "evaluation_v5"
_ITEM_COLUMNS = ("kind", "number", "count_type", "status", "words", "strain", "city", "state", "country",
                 "start_date", "end_date")


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _interval(value: tuple[float, float] | None) -> str:
    return "n/a" if value is None else f"{_fmt(value[0])} to {_fmt(value[1])}"


def _item_text(item: dict) -> str:
    fields = applicable_fields(item.get("kind"))
    return ", ".join(f"{name}={show(item.get(name))}" for name in fields)


# --- report.md ---------------------------------------------------------------

def _usefulness_section(evaluation: Evaluation) -> list[str]:
    s = evaluation.headline
    u = s.usefulness
    c = u.counts
    return [
        "## 1. Task 1: useful or not",
        "",
        "One answer per article, compared with the gold `useful`.",
        "",
        "| | Model: useful | Model: not useful |",
        "|---|---|---|",
        f"| **Gold: useful** | {c.tp} | {c.fn} (missed article) |",
        f"| **Gold: not useful** | {c.fp} (false alarm) | {u.true_negatives} |",
        "",
        f"Precision **{_fmt(c.precision)}**, recall **{_fmt(c.recall)}**, F1 **{_fmt(c.f1)}** "
        f"(95% interval {_interval(s.intervals['useful_f1'])}), accuracy **{_fmt(u.accuracy)}**.",
        "",
    ]


_SUMMARY_HEADER = ["| Metric | Per article | Articles covered | **Mean** | 95% interval of the mean | Median | "
                   "25th-75th | At 1 | At 0 |", "|---|---|---|---|---|---|---|---|---|"]


def _metric_row(label: str, calculation: str, d: Distribution, ci=None) -> str:
    return (f"| {label} | {calculation} | {d.articles} | **{_fmt(d.mean)}** | {_interval(ci) if ci is not None else ''} | "
            f"{_fmt(d.median)} | {_fmt(d.q1)} to {_fmt(d.q3)} | {_fmt(d.share_one)} | {_fmt(d.share_zero)} |")


def _finding_section(evaluation: Evaluation) -> list[str]:
    s = evaluation.headline
    m, c = s.metrics, s.counts
    lines = [
        "## 2. Task 2: finding the events",
        "",
        "Places are compared in their agreed form (5.1): every city, state and country, in gold and in the "
        f"model's reply, is replaced by its {config.PLACE_NAME_LANGUAGE} name in OpenStreetMap, so two spellings of one "
        "place are never a difference. "
        f"Inside each article, each gold item is paired with at most one model item ({MATCHING_VERSION}): same "
        f"country and kind, similarity (share of fields that agree) at least {MATCH_THRESHOLD}. The highest-similarity "
        "pair still available is locked first, and its two items are used up (ties: the pair with fewer other "
        "options, then article order). A pair is a **hit**; a gold item left alone is a **miss**; a model item left "
        "alone is an **extra**.",
        "",
        "Every metric is computed **per article**, then summarised over the articles it covers, each article "
        "weighing the same. **Mean** is the headline; the interval comes from resampling articles.",
        "",
        *_SUMMARY_HEADER,
        _metric_row("**Recall**", "hits / gold items", m["recall"], s.intervals["recall"]),
        _metric_row("**Precision**", "hits / model items", m["precision"], s.intervals["precision"]),
        _metric_row("**F1**", "2 x hits / (2 x hits + misses + extras)", m["f1"], s.intervals["f1"]),
        "",
        f"Context only (added over all articles, not a score): {c.tp} hits, {c.fn} misses, {c.fp} extras. "
        "Per-article values: `article_metrics.csv`, `plot_article_counts.png` and `plot_article_metrics.png`.",
        "",
    ]
    other = evaluation.summaries.get("without_inactive")
    if other:
        o = other.metrics
        lines += [f"With inactive-only items (1.3 food and monitoring fallbacks) removed on both sides: mean recall "
                  f"{_fmt(o['recall'].mean)}, precision {_fmt(o['precision'].mean)}, F1 {_fmt(o['f1'].mean)}.", ""]
    return lines


def _details_section(evaluation: Evaluation) -> list[str]:
    s = evaluation.headline
    m = s.metrics
    lines = [
        "## 3. Task 2: details of the found events",
        "",
        "Only hits are scored here; misses and extras are already in section 2. A hit's accuracy is the share "
        f"of its fields that agree with gold, which is its similarity, so it is never below {MATCH_THRESHOLD}.",
        "",
        *_SUMMARY_HEADER,
        _metric_row("**Accuracy**", "mean similarity of the article's hits", m["accuracy"], s.intervals["accuracy"]),
        _metric_row("**Exact rate**", "hits with every field right / hits", m["exact_rate"], s.intervals["exact_rate"]),
        "",
        "**Field accuracy**, per article: the article's hits with that field right / its hits with that field. "
        "It shows which detail goes wrong (`plot_field_accuracy.png`).",
        "",
        "| Field | Articles covered | **Mean** | Median | 25th-75th | At 1 | At 0 |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in ALL_FIELDS:
        d = s.fields[name]
        if d.articles:
            lines.append(f"| {name} | {d.articles} | **{_fmt(d.mean)}** | {_fmt(d.median)} | {_fmt(d.q1)} to "
                         f"{_fmt(d.q3)} | {_fmt(d.share_one)} | {_fmt(d.share_zero)} |")
    return [*lines, ""]


def _articles_section(evaluation: Evaluation) -> list[str]:
    s = evaluation.headline
    share = lambda n, total: f"{n} ({_fmt(safe_divide(n, total))})"  # noqa: E731
    return [
        "## 4. Task 2: article outcomes",
        "",
        "Each article is in exactly one bucket (`plot_article_buckets.png`).",
        "",
        "| Articles | Outcome | Count (share) |",
        "|---|---|---|",
        f"| Gold has items ({s.gold_nonempty}) | every item found, no extras | **{share(s.all_found, s.gold_nonempty)}** |",
        f"| | ... of which every detail right as well | {share(s.all_found_and_exact, s.gold_nonempty)} |",
        f"| | some found, with misses or extras | {share(s.some_found, s.gold_nonempty)} |",
        f"| | nothing found | {share(s.none_found, s.gold_nonempty)} |",
        f"| Gold has no items ({s.gold_empty}) | model wrote none (correct) | **{share(s.both_empty, s.gold_empty)}** |",
        f"| | model wrote items (false items) | {share(s.false_items_on_empty, s.gold_empty)} |",
        "",
    ]


def _errors_section(evaluation: Evaluation) -> list[str]:
    s = evaluation.headline
    d = evaluation.diagnostics
    lines = [
        "## 5. Where the misses and extras come from",
        "",
        "| Kind | Gold | Model | Hits | Misses | Extras |",
        "|---|---|---|---|---|---|",
    ]
    for kind in sorted(d.by_kind, key=lambda k: (k not in ITEM_KINDS, str(k))):
        c = d.by_kind[kind]
        lines.append(f"| {kind} | {c['gold']} | {c['model']} | {c['matched']} | {c['missed']} | {c['additional']} |")
    confusion = [(pair, n) for pair, n in d.kind_confusion.items() if pair[0] != pair[1]]
    lines += [
        "",
        f"- Extras that repeat another model item ({DUPLICATES_VERSION}): **{s.duplicate_extras}** of {s.counts.fp}.",
        "- Hits whose kinds differ (gold -> model): "
        + (", ".join(f"{g} -> {m}: {n}" for (g, m), n in sorted(confusion)) or "none") + ".",
    ]
    for title, source in (("Misses", d.missed_by), ("Extras", d.additional_by)):
        lines.append(f"- {title} by country (top 10): "
                     + (", ".join(f"{k} {v}" for k, v in source["country"].most_common(10)) or "none") + ".")
    return [*lines, ""]


def _checks_section(evaluation: Evaluation) -> list[str]:
    scored = evaluation.rows_with_status(SCORED)
    e = evaluation.diagnostics.evidence
    rule_counts = Counter(v[:3] for r in scored for v in r.violations)
    lines = [
        "## 6. Checks and coverage",
        "",
        f"- Articles in the run with a gold label: **{len(evaluation.rows)}**; scored: **{len(scored)}**.",
    ]
    for status, meaning in ((API_ERROR, "API call failed after retries"),
                            (UNPARSEABLE, "reply was not valid JSON or was cut off"),
                            (MALFORMED, "valid JSON that breaks the reply format")):
        failed = evaluation.rows_with_status(status)
        if failed:
            lines.append(f"- Not scored, {status} ({meaning}): **{len(failed)}**. These are left out of every "
                         "number above; rerun them with --run-dir.")
    lines += [
        f"- Evidence quotes copied exactly from the article: {_fmt(safe_divide(e['quotes verbatim'], e['quotes']))} "
        f"of {e['quotes']}.",
        f"- Articles breaking at least one rule check: {sum(bool(r.violations) for r in scored)} of {len(scored)} "
        "(" + (", ".join(f"{k}: {v}" for k, v in sorted(rule_counts.items())) or "none") + ").",
        "",
    ]
    return lines


# --- Settings and versions ---------------------------------------------------

def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _code_version() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=config.PROJECT_DIR,
                                capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain", "flu_extractor"], cwd=config.PROJECT_DIR,
                               capture_output=True, text=True, timeout=10).stdout.strip()
        return result.stdout.strip() + (" (uncommitted changes in flu_extractor)" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return None


def _summary_json(s: Summary) -> dict:
    return {
        "articles": s.articles, "gold_nonempty": s.gold_nonempty, "gold_empty": s.gold_empty,
        "metrics": {name: d.__dict__ for name, d in s.metrics.items()},
        "field_accuracy": {name: d.__dict__ for name, d in s.fields.items() if d.articles},
        "intervals_of_the_mean": s.intervals,
        "buckets": {"all_found": s.all_found, "all_found_and_exact": s.all_found_and_exact,
                    "some_found": s.some_found, "none_found": s.none_found,
                    "empty_correct": s.both_empty, "empty_false_items": s.false_items_on_empty},
        "counts": {"hits": s.counts.tp, "misses": s.counts.fn, "extras": s.counts.fp,
                   "repeated_extras": s.duplicate_extras},
        "useful": {"precision": s.usefulness.counts.precision, "recall": s.usefulness.counts.recall,
                   "f1": s.usefulness.counts.f1, "accuracy": s.usefulness.accuracy},
    }


def _settings(run_dir: Path) -> dict:
    run_config_path = run_dir / "run_config.json"
    run_config = json.loads(run_config_path.read_text(encoding="utf-8")) if run_config_path.exists() else {}
    return {
        "run_id": run_dir.name,
        "model": run_config.get("model"),
        "prompt": run_config.get("system_prompt"), "prompt_sha256": run_config.get("system_prompt_sha256"),
        "examples": run_config.get("examples"), "examples_sha256": run_config.get("examples_sha256"),
        "example_count": run_config.get("example_count"),
        "decoding": {k: run_config.get(k) for k in ("temperature", "top_p", "seed", "extra_body", "max_tokens")},
        "annotation_rules": "prompt_rules.md, as in the prompt above",
        "gold_labels_sha256": _sha256(config.GOLD_LABELS_PATH),
        "duplicate_adjudication_sha256": _sha256(config.ADJUDICATION_PATH),
        "normalization_version": NORMALIZATION_VERSION,
        "place_names": {"source": config.PLACE_NAME_SOURCE, "language": config.PLACE_NAME_LANGUAGE,
                        "rule": "every city, state and country in its agreed form, its name in OpenStreetMap (5.1)"},
        "matching_version": MATCHING_VERSION, "match_threshold": MATCH_THRESHOLD,
        "duplicates_version": DUPLICATES_VERSION,
        "evaluation_version": EVALUATION_VERSION, "code_version": _code_version(),
        "bootstrap": {"resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED, "unit": "article"},
    }


# --- Detailed files ----------------------------------------------------------

def _write_csv(path: Path, columns: list[str], rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _scored(evaluation: Evaluation) -> list[RowResult]:
    return [r for r in evaluation.rows if r.status == SCORED]


def _article_outcome(o) -> str:
    """The article's bucket in report section 4."""
    if not o.gold_items:
        return "empty, correct" if not o.model_items else "empty, false items"
    if o.tp == 0:
        return "nothing found"
    if o.fp == 0 and o.fn == 0:
        return "all found, every detail right" if o.exact_items == o.tp else "all found"
    return "some found"


def _article_rows(evaluation: Evaluation):
    for r in evaluation.rows:
        o = r.outcome
        yield {
            "article_id": r.article_id, "sources": " ".join(r.sources), "status": r.status,
            "gold_useful": r.gold_useful, "model_useful": r.model_useful,
            "gold_items": len(r.gold_items), "model_items": len(r.model_items) if o else "",
            "hits": o.tp if o else "", "misses": o.fn if o else "", "extras": o.fp if o else "",
            "repeated_extras": len(o.duplicate_extras) if o else "",
            "recall": o.recall if o else "", "precision": o.precision if o else "", "f1": o.f1 if o else "",
            "accuracy": o.attribute_accuracy if o else "", "exact_hits": o.exact_items if o else "",
            "outcome": _article_outcome(o) if o else "",
            "rule_violations": " | ".join(r.violations), "problems": " | ".join(r.problems),
        }


def _item_columns(prefix: str, item: dict | None) -> dict:
    return {f"{prefix}_{name}": (show(item.get(name)) if item else "") for name in _ITEM_COLUMNS}


def _evidence(item: dict | None) -> str:
    return " || ".join(item.get("evidence") or []) if item else ""


def _matched_rows(rows: list[RowResult]):
    for r in rows:
        o = r.outcome
        for (g, m, compat), pair in zip(o.match.pairs, o.pair_scores):
            line = {"article_id": r.article_id, "sources": " ".join(r.sources), "gold_index": g, "model_index": m,
                    "similarity": round(compat, 3), "exact": pair.exact, "wrong_fields": ", ".join(pair.wrong_fields)}
            results = {f.name: f.result for f in pair.fields}
            line.update({f"result_{name}": results.get(name, "not applicable") for name in ALL_FIELDS})
            line.update(_item_columns("gold", o.gold_items[g]))
            line.update(_item_columns("model", o.model_items[m]))
            line["gold_evidence"], line["model_evidence"] = _evidence(o.gold_items[g]), _evidence(o.model_items[m])
            yield line


def _missed_rows(rows: list[RowResult]):
    for r in rows:
        o = r.outcome
        rejected = {g: (m, s) for g, m, s in o.match.rejected}
        for g in o.match.unmatched_gold:
            m, score = rejected.get(g, (None, None))
            yield {"article_id": r.article_id, "sources": " ".join(r.sources), "gold_index": g,
                   "model_wrote_items": bool(o.model_items),
                   "closest_model_index": "" if m is None else m,
                   "closest_model_similarity": "" if score is None else round(score, 3),
                   **_item_columns("gold", o.gold_items[g]), "gold_evidence": _evidence(o.gold_items[g])}


def _additional_rows(rows: list[RowResult]):
    for r in rows:
        o = r.outcome
        for m in o.match.unmatched_model:
            yield {"article_id": r.article_id, "sources": " ".join(r.sources), "model_index": m,
                   "gold_has_items": bool(o.gold_items), "duplicate_label": o.duplicate_extras.get(m, ""),
                   **_item_columns("model", o.model_items[m]), "model_evidence": _evidence(o.model_items[m])}


def _duplicate_rows(rows: list[RowResult]):
    for r in rows:
        for review in r.gold_reviews:
            for i in review["item_indexes"]:
                yield {"side": "gold", "article_id": r.article_id, "sources": " ".join(r.sources),
                       "group": "-".join(map(str, review["item_indexes"])), "category": review["category"],
                       "decision": review["decision"], "reason": review["reason"], "item_index": i,
                       "duplicate_label": "", "item": _item_text(r.raw_gold_items[i]),
                       "evidence": _evidence(r.raw_gold_items[i])}
        if r.outcome:
            for group in find_groups(r.model_items):
                for i in group.indexes:
                    yield {"side": "model", "article_id": r.article_id, "sources": " ".join(r.sources),
                           "group": "-".join(map(str, group.indexes)), "category": group.category,
                           "decision": "", "reason": "", "item_index": i,
                           "duplicate_label": r.outcome.duplicate_extras.get(i, "kept"),
                           "item": _item_text(r.model_items[i]), "evidence": _evidence(r.model_items[i])}


def _error_examples(evaluation: Evaluation, per_type: int = 3) -> list[str]:
    rows = _scored(evaluation)
    lines = ["# Error examples", "", f"Run: up to {per_type} examples of each error type, in article id order.", ""]

    def block(title, examples):
        lines.extend([f"## {title}", ""])
        if not examples:
            lines.extend(["None.", ""])
        for article, gold, model, note in examples[:per_type]:
            lines.append(f"- **{article.article_id}** ({' '.join(article.sources)}) {note}")
            if gold:
                lines.append(f"  - gold: {_item_text(gold)}  \n    evidence: {_evidence(gold)[:300]}")
            if model:
                lines.append(f"  - model: {_item_text(model)}  \n    evidence: {_evidence(model)[:300]}")
        lines.append("")

    for kind in ITEM_KINDS:
        block(f"Missed {kind} items", [(r, r.outcome.gold_items[g], None, "") for r in rows for g in r.outcome.match.unmatched_gold
                                       if r.outcome.gold_items[g]["kind"] == kind])
        block(f"Additional {kind} items (not duplicates)",
              [(r, None, r.outcome.model_items[m], "gold has no items" if not r.gold_items else "")
               for r in rows for m in r.outcome.match.unmatched_model
               if r.outcome.model_items[m].get("kind") == kind and m not in r.outcome.duplicate_extras])
    block("Duplicate extras", [(r, None, r.outcome.model_items[m], f"({label})") for r in rows
                               for m, label in r.outcome.duplicate_extras.items()])
    block("Kind confusion", [(r, r.outcome.gold_items[g], r.outcome.model_items[m], "") for r in rows
                             for g, m, _ in r.outcome.match.pairs
                             if r.outcome.gold_items[g]["kind"] != r.outcome.model_items[m]["kind"]])
    for combo, _ in evaluation.diagnostics.wrong_combinations.most_common(5):
        block(f"Matched, wrong only in: {', '.join(combo)}",
              [(r, r.outcome.gold_items[g], r.outcome.model_items[m], "") for r in rows
               for (g, m, _), pair in zip(r.outcome.match.pairs, r.outcome.pair_scores) if tuple(pair.wrong_fields) == combo])
    return lines


def write_report(evaluation: Evaluation, run_dir: Path) -> None:
    """Write every file listed in the module docstring into the run folder."""
    settings = _settings(run_dir)
    sections = [
        f"# Extraction report: {run_dir.name}", "",
        f"Model: `{settings['model']}`  |  Prompt: `{settings['prompt']}` + `{settings['examples']}` "
        f"(k = {settings['example_count']})  |  {MATCHING_VERSION}, {NORMALIZATION_VERSION}, {DUPLICATES_VERSION}", "",
        *_usefulness_section(evaluation), *_finding_section(evaluation), *_details_section(evaluation),
        *_articles_section(evaluation), *_errors_section(evaluation), *_checks_section(evaluation),
        "Charts: `plot_article_counts.png`, `plot_article_metrics.png`, `plot_field_accuracy.png`, "
        "`plot_article_buckets.png`.", "",
        "Detailed files: `article_metrics.csv`, `matched_items.csv`, `missed_items.csv`, `additional_items.csv`, "
        "`duplicate_candidates.csv`, `field_error_summary.csv`, `kind_error_summary.csv`, `error_examples.md`, "
        "`evaluation_summary.json`.", "",
    ]
    (run_dir / "report.md").write_text("\n".join(sections), encoding="utf-8")
    (run_dir / "evaluation_summary.json").write_text(json.dumps({
        "settings": settings,
        "populations": {name: _summary_json(s) for name, s in evaluation.summaries.items()},
    }, indent=2, default=str), encoding="utf-8")

    rows = _scored(evaluation)
    article_rows = list(_article_rows(evaluation))
    _write_csv(run_dir / "article_metrics.csv", list(article_rows[0]) if article_rows else ["article_id"], article_rows)
    matched = list(_matched_rows(rows))
    _write_csv(run_dir / "matched_items.csv", list(matched[0]) if matched else ["article_id"], matched)
    missed = list(_missed_rows(rows))
    _write_csv(run_dir / "missed_items.csv", list(missed[0]) if missed else ["article_id"], missed)
    additional = list(_additional_rows(rows))
    _write_csv(run_dir / "additional_items.csv", list(additional[0]) if additional else ["article_id"], additional)
    duplicates = list(_duplicate_rows(rows))
    _write_csv(run_dir / "duplicate_candidates.csv",
               ["side", "article_id", "sources", "group", "category", "decision", "reason", "item_index",
                "duplicate_label", "item", "evidence"], duplicates)
    d = evaluation.diagnostics
    _write_csv(run_dir / "field_error_summary.csv", ["field", "compared", "right", "wrong", "missing", "extra", "accuracy"],
               [{"field": name, "compared": sum(c.values()), "right": c[MATCH], "wrong": c[WRONG],
                 "missing": c[MISSING_VALUE], "extra": c[EXTRA_VALUE], "accuracy": safe_divide(c[MATCH], sum(c.values()))}
                for name, c in d.field_results.items() if sum(c.values())])
    _write_csv(run_dir / "kind_error_summary.csv",
               ["kind", "gold", "model", "matched", "missed", "additional", "duplicate extras", "matched under another kind"],
               [{"kind": kind, **{k: c[k] for k in ("gold", "model", "matched", "missed", "additional", "duplicate extras")},
                 "matched under another kind": sum(n for (g, m), n in d.kind_confusion.items() if g == kind and m != kind)}
                for kind, c in d.by_kind.items()])
    (run_dir / "error_examples.md").write_text("\n".join(_error_examples(evaluation)), encoding="utf-8")
    write_plots(evaluation.headline, [r.outcome for r in rows], run_dir)
