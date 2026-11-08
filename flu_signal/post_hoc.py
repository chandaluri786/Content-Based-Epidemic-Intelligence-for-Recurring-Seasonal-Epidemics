"""Post-hoc checks after step 5. Designed on 2026-11-07, AFTER the held-out results were seen.

None of this replaces the pre-set result (output/results_summary.json: early limit -4, the frozen settings).
It only shows how much that result depends on choices we made:

1. Early-limit table: the hit window starts at week -2, -3, -4, -5, -6 or -7 instead of -4. At each limit the
   settings are retuned on the 2015-2021 seasons with that limit, then scored on 2022-2024 (by year), and
   LOSO is rerun with it. -7 is the earliest week a week-by-week detector can alarm (it needs 4 weeks of
   history), so the -7 row is the same as "every week before onset counts".
2. Per-signal table (limit -4): each content signal with its own best 2015-2021 setting, scored on 2022-2024
   against the frozen frequency setting. This is a description, not a new choice of winner.
   avian_articles (bird flu) is a negative control: it should not track seasonal onset.
3. LOSO without content_articles: content_articles includes bird-flu items (79% of them in USA-2024),
   so LOSO is rerun with only the bird-flu-free content signals.

Nothing here writes the frozen settings or the frozen detections. Run from flu_signal/:

    ../llm-extractor/.venv/bin/python post_hoc.py
"""

import json
import sys
from collections import Counter

import signal_config as cfg
from build_tables import write_csv
from build_weekly import read_table
from evaluate import CONTENT, FREQUENCY, season_row, summarize
from loso import headline_weeks, run_loso, setting_label
from run_detectors import DETECTED_SIGNALS, load_frozen_settings, series_by_season
from scoring import Setting
from tune import CONTENT_SIGNALS, FREQUENCY_SIGNAL, choose, score_weeks

AVIAN_SIGNAL = "avian_articles"
ALL_SIGNALS = DETECTED_SIGNALS + (AVIAN_SIGNAL,)
BIRD_FLU_FREE_SIGNALS = tuple(signal for signal in CONTENT_SIGNALS if signal != "content_articles")
EARLY_LIMITS = (2, 3, 4, 5, 6, 7)
WHOLE_WINDOW_LIMIT = 7   # earliest possible week-by-week alarm: week FIRST_WEEK + MIN_WEEKS - 1 = -7

EARLY_LIMIT_PATH = cfg.OUTPUT_DIR / "post_hoc_early_limit.csv"
SIGNALS_PATH = cfg.OUTPUT_DIR / "post_hoc_signals.csv"
SEASONS_PATH = cfg.OUTPUT_DIR / "post_hoc_seasons.csv"
SUMMARY_PATH = cfg.OUTPUT_DIR / "post_hoc_summary.json"
NOTE = ("post hoc: designed after the held-out results were seen (2026-11-07); descriptive only. "
        "The pre-set result is results_summary.json.")


def headline_series(weekly_rows: list[dict]) -> dict[str, dict]:
    """The 22 USA/AUS/IND seasons, both splits, with every signal including bird flu."""
    seasons = {**series_by_season(weekly_rows, cfg.SPLIT_CALIBRATION, ALL_SIGNALS),
               **series_by_season(weekly_rows, cfg.SPLIT_HELD_OUT, ALL_SIGNALS)}
    return {season_id: season for season_id, season in seasons.items() if season["headline"]}


def is_held_out(season_id: str) -> bool:
    return int(season_id.split("-")[1]) >= cfg.HELD_OUT_FROM_YEAR


def by_year(weeks: dict, seasons: dict[str, dict], early_limit: int, content_signals: tuple[str, ...],
            frequency: Setting | None = None) -> tuple[Setting, Setting, list[dict]]:
    """Tune on the calibration seasons only, then score the held-out ones. `frequency` skips its tuning."""
    calibration = [season_id for season_id in seasons if not is_held_out(season_id)]
    scored = score_weeks(weeks, calibration, early_limit)
    content = choose(scored, content_signals)[0]
    frequency = frequency or choose(scored, (FREQUENCY_SIGNAL,))[0]
    rows = [season_row(season_id, seasons[season_id]["country"], weeks[content][season_id],
                       weeks[frequency][season_id], early_limit)
            for season_id in sorted(seasons) if is_held_out(season_id)]
    return content, frequency, rows


def most_chosen(rows: list[dict], role: str) -> str:
    label, count = Counter(row[f"{role}_setting"] for row in rows).most_common(1)[0]
    return f"{label} ({count}/{len(rows)} folds)"


def summary_row(evaluation: str, early_limit: int, rows: list[dict], content: str, frequency: str, **extra) -> dict:
    """One line of a post-hoc table, from the season rows of one evaluation."""
    summary = summarize(rows)
    row = {"evaluation": evaluation, "early_limit": -early_limit, **extra, "content_setting": content,
           "frequency_setting": frequency, "seasons": summary["seasons"]}
    for role in (CONTENT, FREQUENCY):
        for key in ("hits", "false_alarms", "misses", "score", "median_lead_days"):
            row[f"{role}_{key}"] = summary[role][key]
    row.update({key: summary[key] for key in ("content_wins", "frequency_wins", "ties", "sign_test_p",
                                               "content_better")})
    return row


def early_limit_table(weeks: dict, seasons: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    table, season_rows = [], []
    for limit in EARLY_LIMITS:
        content, frequency, rows = by_year(weeks, seasons, limit, CONTENT_SIGNALS)
        table.append(summary_row("by_year", limit, rows, setting_label(content), setting_label(frequency)))
        season_rows += [{"evaluation": "by_year", "early_limit": -limit, **row} for row in rows]
        for evaluation, signals in (("loso", CONTENT_SIGNALS), ("loso_no_content_articles", BIRD_FLU_FREE_SIGNALS)):
            folds = run_loso(seasons, limit, signals, weeks)
            table.append(summary_row(evaluation, limit, folds, most_chosen(folds, CONTENT), most_chosen(folds, FREQUENCY)))
            season_rows += [{"evaluation": evaluation, "early_limit": -limit, **row} for row in folds]
    return table, season_rows


def bird_flu_share(signal: str, seasons: dict[str, dict]) -> float:
    """Share of the signal's held-out articles that are bird flu. Only content_articles mixes the two."""
    if signal == AVIAN_SIGNAL:
        return 1.0
    if signal != "content_articles":
        return 0.0
    held_out = [season for season_id, season in seasons.items() if is_held_out(season_id)]
    total = sum(sum(season[signal]) for season in held_out)
    return round(sum(sum(season[AVIAN_SIGNAL]) for season in held_out) / total, 3) if total else 0.0


def signals_table(weeks: dict, seasons: dict[str, dict], frozen_frequency: Setting) -> tuple[list[dict], list[dict]]:
    table, season_rows = [], []
    for signal in CONTENT_SIGNALS + (AVIAN_SIGNAL,):
        content, _, rows = by_year(weeks, seasons, cfg.EARLY_LIMIT, (signal,), frozen_frequency)
        role = "negative control" if signal == AVIAN_SIGNAL else "content signal"
        table.append(summary_row("by_year_one_signal", cfg.EARLY_LIMIT, rows, setting_label(content),
                                 setting_label(frozen_frequency), signal=signal, role=role,
                                 bird_flu_share_held_out=bird_flu_share(signal, seasons)))
        season_rows += [{"evaluation": "by_year_one_signal", "early_limit": -cfg.EARLY_LIMIT, "signal": signal, **row}
                        for row in rows]
    return table, season_rows


def uniform(rows: list[dict]) -> list[dict]:
    """Rows with the same columns (blank where a row has none), so they fit one CSV."""
    columns = list(dict.fromkeys(key for row in rows for key in row))
    return [{column: row.get(column, "") for column in columns} for row in rows]


def frozen_setting(entry: dict) -> Setting:
    return Setting(entry["signal"], entry["method"], entry["cutoff"], entry["sustain_weeks"], entry["margin"])


def check_against_pre_set(table: list[dict], signals: list[dict], frozen: dict) -> list[str]:
    """The -4 rows must reproduce the frozen settings and the step 5 numbers exactly."""
    problems = []
    pre_set = json.loads((cfg.OUTPUT_DIR / "results_summary.json").read_text(encoding="utf-8"))["headline_held_out"]
    row = next(r for r in table if r["evaluation"] == "by_year" and r["early_limit"] == -cfg.EARLY_LIMIT)
    for role in (CONTENT, FREQUENCY):
        if row[f"{role}_setting"] != setting_label(frozen_setting(frozen[role])):
            problems.append(f"-4 {role} setting {row[f'{role}_setting']} is not the frozen one")
        if row[f"{role}_score"] != pre_set[role]["score"]:
            problems.append(f"-4 {role} score {row[f'{role}_score']} != results_summary {pre_set[role]['score']}")
    rising = next(r for r in signals if r["signal"] == "rising_articles")
    if (rising["content_score"], rising["content_wins"]) != (row["content_score"], row["content_wins"]):
        problems.append("the rising_articles row does not match the headline")
    return problems


def main() -> int:
    seasons = headline_series(read_table(cfg.WEEKLY_PATH))
    frozen = load_frozen_settings()
    weeks = headline_weeks(seasons, ALL_SIGNALS)
    table, early_seasons = early_limit_table(weeks, seasons)
    signals, signal_seasons = signals_table(weeks, seasons, frozen_setting(frozen[FREQUENCY]))
    problems = check_against_pre_set(table, signals, frozen)
    if problems:
        print("\n".join(problems))
        return 1
    write_csv(EARLY_LIMIT_PATH, table)
    write_csv(SIGNALS_PATH, uniform(signals))
    write_csv(SEASONS_PATH, uniform(early_seasons + signal_seasons))
    SUMMARY_PATH.write_text(json.dumps({"post_hoc": True, "note": NOTE, "whole_window_limit": -WHOLE_WINDOW_LIMIT,
                                        "early_limit_table": table, "signals_table": signals}, indent=2) + "\n",
                            encoding="utf-8")
    for row in table + signals:
        print(f"{row['evaluation']:<26} {row['early_limit']:>3} {row.get('signal', ''):<18} "
              f"content {row['content_hits']}/{row['content_false_alarms']}/{row['content_misses']} "
              f"score {row['content_score']:>3} | frequency {row['frequency_hits']}/{row['frequency_false_alarms']}/"
              f"{row['frequency_misses']} score {row['frequency_score']:>3} | wins {row['content_wins']}-"
              f"{row['frequency_wins']}-{row['ties']} p {row['sign_test_p']}")
    print(f"\n-> {EARLY_LIMIT_PATH}\n-> {SIGNALS_PATH}\n-> {SEASONS_PATH}\n-> {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
