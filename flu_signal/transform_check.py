"""Post-hoc check (2026-11-10, after the results were seen): does the result depend on the Anscombe transform?

The whole procedure is rerun with each count transform in detection.TRANSFORMS: anscombe (the method),
log(x + 1) and raw counts. For each one, at the pre-set early limit -4:
- by year: tune on the 2015-2021 headline seasons, score the 2022-2024 ones;
- LOSO: the 22 headline seasons, retuned in every fold.
The grid is the same for every transform. Margin 1 means a different step on each scale (one Poisson noise unit
on the Anscombe scale, one article on raw counts, a rise of e times on the log scale); no chosen setting used it.

Descriptive only: nothing here changes the frozen settings or the pre-set result. The anscombe rows must equal
results_summary.json and loso_summary.json, or the run stops. Run from flu_signal/:

    ../llm-extractor/.venv/bin/python transform_check.py
"""

import json
import sys

import signal_config as cfg
from build_tables import write_csv
from build_weekly import read_table
from detection import DEFAULT_TRANSFORM, TRANSFORMS
from evaluate import CONTENT, FREQUENCY
from loso import LOSO_SUMMARY_PATH, headline_weeks, run_loso, setting_label
from post_hoc import by_year, headline_series, most_chosen, summary_row
from tune import CONTENT_SIGNALS, FREQUENCY_SIGNAL

TRANSFORM_PATH = cfg.OUTPUT_DIR / "post_hoc_transform.csv"
TRANSFORM_SUMMARY_PATH = cfg.OUTPUT_DIR / "post_hoc_transform.json"
NOTE = ("post hoc: designed after the results were seen (2026-11-10); descriptive only. "
        "anscombe is the method; log and raw show how much the result depends on it.")


def transform_rows(seasons: dict[str, dict], transform: str) -> list[dict]:
    """The by-year row and the LOSO row of one transform, at the pre-set early limit."""
    weeks = headline_weeks(seasons, CONTENT_SIGNALS + (FREQUENCY_SIGNAL,), transform)
    content, frequency, rows = by_year(weeks, seasons, cfg.EARLY_LIMIT, CONTENT_SIGNALS)
    folds = run_loso(seasons, cfg.EARLY_LIMIT, CONTENT_SIGNALS, weeks)
    return [summary_row("by_year", cfg.EARLY_LIMIT, rows, setting_label(content), setting_label(frequency),
                        transform=transform),
            summary_row("loso", cfg.EARLY_LIMIT, folds, most_chosen(folds, CONTENT), most_chosen(folds, FREQUENCY),
                        transform=transform)]


def check_against_method(table: list[dict]) -> list[str]:
    """The anscombe rows must reproduce the step 5 by-year result and the LOSO summary."""
    problems = []
    pre_set = json.loads((cfg.OUTPUT_DIR / "results_summary.json").read_text(encoding="utf-8"))["headline_held_out"]
    loso = json.loads(LOSO_SUMMARY_PATH.read_text(encoding="utf-8"))["overall"]
    for evaluation, expected in (("by_year", pre_set), ("loso", loso)):
        row = next(r for r in table if r["transform"] == DEFAULT_TRANSFORM and r["evaluation"] == evaluation)
        for role in (CONTENT, FREQUENCY):
            if row[f"{role}_score"] != expected[role]["score"]:
                problems.append(f"{evaluation} {role} score {row[f'{role}_score']} != {expected[role]['score']}")
        if (row["content_wins"], row["frequency_wins"]) != (expected["content_wins"], expected["frequency_wins"]):
            problems.append(f"{evaluation} wins {row['content_wins']}-{row['frequency_wins']} do not match")
    return problems


def main() -> int:
    seasons = headline_series(read_table(cfg.WEEKLY_PATH))
    table = [row for transform in TRANSFORMS for row in transform_rows(seasons, transform)]
    problems = check_against_method(table)
    if problems:
        print("\n".join(problems))
        return 1
    write_csv(TRANSFORM_PATH, table)
    TRANSFORM_SUMMARY_PATH.write_text(json.dumps({"post_hoc": True, "note": NOTE, "early_limit": -cfg.EARLY_LIMIT,
                                                  "table": table}, indent=2) + "\n", encoding="utf-8")
    for row in table:
        print(f"{row['transform']:<9} {row['evaluation']:<8} content {row['content_hits']}/{row['content_false_alarms']}/"
              f"{row['content_misses']} score {row['content_score']:>3} | frequency {row['frequency_hits']}/"
              f"{row['frequency_false_alarms']}/{row['frequency_misses']} score {row['frequency_score']:>3} | "
              f"wins {row['content_wins']}-{row['frequency_wins']}-{row['ties']} p {row['sign_test_p']}")
        print(f"          content: {row['content_setting']}\n          frequency: {row['frequency_setting']}")
    print(f"\n-> {TRANSFORM_PATH}\n-> {TRANSFORM_SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
