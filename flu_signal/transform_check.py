"""Post-hoc check (2026-11-10, after the results were seen): does the result depend on the Anscombe transform?

The whole procedure is rerun with each count transform in detection.TRANSFORMS: anscombe (the method),
log(x + 1) and raw counts. For each one, at the pre-set early limit -4:
- by year: tune on the 2015-2021 headline seasons, score the 2022-2024 ones;
- LOSO: the 22 headline seasons, retuned in every fold.
The grid is the same for every transform. Margin 1 means a different step on each scale (one Poisson noise unit
on the Anscombe scale, one article on raw counts, a rise of e times on the log scale); no chosen setting used it.

The JSON also has a `diagnostics` block per transform, to show WHY a result moves (added 2026-11-10). It scores
settings on all 22 seasons at once: that is in-sample, so it explains the mechanism and is not an evaluation.

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
from run_detectors import SELECTABLE_METHODS
from scoring import HIT, Score, Setting, classify, rank
from tune import CONTENT_SIGNALS, FREQUENCY_SIGNAL, score_weeks

TRANSFORM_PATH = cfg.OUTPUT_DIR / "post_hoc_transform.csv"
TRANSFORM_SUMMARY_PATH = cfg.OUTPUT_DIR / "post_hoc_transform.json"
# Fixed settings scored on all 22 seasons in every transform: the two LOSO frequency picks and the LOSO content pick.
FIXED_SETTINGS = (Setting("freq_articles", "bcp_prospective", 0.5, 1, 0.0),
                  Setting("freq_articles", "bcp_prospective", 0.4, 1, 0.0),
                  Setting("content_articles", "bcp_prospective", 0.3, 3, 0.0))
NOTE = ("post hoc: designed after the results were seen (2026-11-10); descriptive only. "
        "anscombe is the method; log and raw show how much the result depends on it.")


def near_best(scored: list[tuple[Setting, Score, dict]], signals: tuple[str, ...],
              within: int = 1) -> tuple[Setting, Score, int]:
    """(best selectable setting, its score, how many selectable settings score within `within` points of it).
    Many near-ties make a leave-one-out choice unstable."""
    ranked = rank([(setting, score) for setting, score, _ in scored
                   if setting.signal in signals and setting.method in SELECTABLE_METHODS])
    best_setting, best_score = ranked[0]
    return best_setting, best_score, sum(1 for _, score in ranked if score.value >= best_score.value - within)


def outcome_counts(score: Score) -> str:
    return f"{score.hits}/{score.false_alarms}/{score.misses}"


def diagnostics(weeks: dict, folds: list[dict]) -> dict:
    """Why a transform's result moves: in-sample scores on all 22 seasons, and how stable the LOSO choice is."""
    season_ids = sorted(next(iter(weeks.values())))
    scored = score_weeks(weeks, season_ids)
    result = {"in_sample_note": "scored on all 22 seasons at once; diagnostic only, not an evaluation"}
    for role, signals in ((CONTENT, CONTENT_SIGNALS), (FREQUENCY, (FREQUENCY_SIGNAL,))):
        setting, score, crowd = near_best(scored, signals)
        result[role] = {"best_in_sample": setting_label(setting), "best_hits_false_misses": outcome_counts(score),
                        "best_score": score.value, "settings_within_1_point": crowd,
                        "loso_different_picks": len({row[f"{role}_setting"] for row in folds})}
        result[role]["loso_folds_missing_where_best_hits"] = [
            row["season_id"] for row in folds
            if classify(weeks[setting][row["season_id"]]) == HIT and row[f"{role}_outcome"] != HIT]
    by_setting = {setting: score for setting, score, _ in scored}
    result["fixed_settings"] = {setting_label(setting): outcome_counts(by_setting[setting]) for setting in FIXED_SETTINGS}
    return result


def transform_rows(seasons: dict[str, dict], transform: str) -> tuple[list[dict], dict]:
    """The by-year row and the LOSO row of one transform at the pre-set early limit, and its diagnostics."""
    weeks = headline_weeks(seasons, CONTENT_SIGNALS + (FREQUENCY_SIGNAL,), transform)
    content, frequency, rows = by_year(weeks, seasons, cfg.EARLY_LIMIT, CONTENT_SIGNALS)
    folds = run_loso(seasons, cfg.EARLY_LIMIT, CONTENT_SIGNALS, weeks)
    return ([summary_row("by_year", cfg.EARLY_LIMIT, rows, setting_label(content), setting_label(frequency),
                         transform=transform),
             summary_row("loso", cfg.EARLY_LIMIT, folds, most_chosen(folds, CONTENT), most_chosen(folds, FREQUENCY),
                         transform=transform)],
            diagnostics(weeks, folds))


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
    results = {transform: transform_rows(seasons, transform) for transform in TRANSFORMS}
    table = [row for rows, _ in results.values() for row in rows]
    problems = check_against_method(table)
    if problems:
        print("\n".join(problems))
        return 1
    write_csv(TRANSFORM_PATH, table)
    TRANSFORM_SUMMARY_PATH.write_text(json.dumps({"post_hoc": True, "note": NOTE, "early_limit": -cfg.EARLY_LIMIT,
                                                  "table": table,
                                                  "diagnostics": {t: d for t, (_, d) in results.items()}}, indent=2) + "\n", encoding="utf-8")
    for row in table:
        print(f"{row['transform']:<9} {row['evaluation']:<8} content {row['content_hits']}/{row['content_false_alarms']}/"
              f"{row['content_misses']} score {row['content_score']:>3} | frequency {row['frequency_hits']}/"
              f"{row['frequency_false_alarms']}/{row['frequency_misses']} score {row['frequency_score']:>3} | "
              f"wins {row['content_wins']}-{row['frequency_wins']}-{row['ties']} p {row['sign_test_p']}")
        print(f"          content: {row['content_setting']}\n          frequency: {row['frequency_setting']}")
    for transform, (_, diag) in results.items():
        print(f"{transform}: " + " | ".join(
            f"{role} best in-sample {diag[role]['best_hits_false_misses']}, {diag[role]['settings_within_1_point']} "
            f"within 1 point, {diag[role]['loso_different_picks']} LOSO picks, "
            f"{len(diag[role]['loso_folds_missing_where_best_hits'])} folds lost" for role in (CONTENT, FREQUENCY)))
        print("    fixed: " + "; ".join(f"{k} {v}" for k, v in diag["fixed_settings"].items()))
    print(f"\n-> {TRANSFORM_PATH}\n-> {TRANSFORM_SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
