"""Step 5 robustness check: leave one season out, over the 22 headline seasons (USA, AUS, IND).

For each season: the full step 4 tuning (grid, score, ranking, plateau-middle rule, content and frequency
separately) is redone on the other 21 seasons, and the two chosen settings are scored on the left-out one.
Run only after the headline result is written. Run from flu_signal/:

    ../llm-extractor/.venv/bin/python loso.py

A detector's alarm in one season does not depend on the other seasons, so every setting's alarm week is
worked out once per season, and each fold only re-scores and re-ranks.
"""

import json
import sys

import signal_config as cfg
from build_tables import write_csv
from build_weekly import read_table
from evaluate import season_row, summarize
from run_detectors import series_by_season
from scoring import score_setting
from tune import CONTENT_SIGNALS, FREQUENCY_SIGNAL, alarm_weeks, best, grid, plateau_middle

LOSO_PATH = cfg.OUTPUT_DIR / "loso_results.csv"
LOSO_SUMMARY_PATH = cfg.OUTPUT_DIR / "loso_summary.json"


def headline_seasons(weekly_rows: list[dict]) -> dict[str, dict]:
    seasons = {**series_by_season(weekly_rows, cfg.SPLIT_CALIBRATION), **series_by_season(weekly_rows, cfg.SPLIT_HELD_OUT)}
    return {season_id: season for season_id, season in seasons.items() if season["headline"]}


def fold(left_out: str, weeks_by_setting: dict, seasons: dict[str, dict]) -> dict:
    """Tune on every season but `left_out`, then score the two chosen settings on `left_out`."""
    training = [season_id for season_id in sorted(seasons) if season_id != left_out]
    scored = []
    for setting, weeks in weeks_by_setting.items():
        training_weeks = {season_id: weeks[season_id] for season_id in training}
        scored.append((setting, score_setting(list(training_weeks.values())), training_weeks))
    chosen = {role: plateau_middle(best(scored, signals), scored)[0]
              for role, signals in (("content", CONTENT_SIGNALS), ("frequency", (FREQUENCY_SIGNAL,)))}
    row = season_row(left_out, seasons[left_out]["country"], weeks_by_setting[chosen["content"]][left_out],
                     weeks_by_setting[chosen["frequency"]][left_out], trained_on=len(training))
    for role, setting in chosen.items():
        row[f"{role}_setting"] = (f"{setting.signal} {setting.method} cutoff {setting.cutoff} "
                                  f"sustain {setting.sustain_weeks} margin {setting.margin}")
    return row


def run_loso(seasons: dict[str, dict]) -> list[dict]:
    weeks_by_setting = {setting: alarm_weeks(setting, seasons) for setting in grid(CONTENT_SIGNALS + (FREQUENCY_SIGNAL,))}
    return [fold(season_id, weeks_by_setting, seasons) for season_id in sorted(seasons)]


def main() -> int:
    seasons = headline_seasons(read_table(cfg.WEEKLY_PATH))
    rows = run_loso(seasons)
    write_csv(LOSO_PATH, rows)
    summary = {"seasons": len(rows), "overall": summarize(rows),
               "held_out_seasons_only": summarize([r for r in rows if int(r["season_id"].split("-")[1]) >= cfg.HELD_OUT_FROM_YEAR]),
               "content_settings_chosen": sorted({r["content_setting"] for r in rows}),
               "frequency_settings_chosen": sorted({r["frequency_setting"] for r in rows})}
    LOSO_SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\n-> {LOSO_PATH}\n-> {LOSO_SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
