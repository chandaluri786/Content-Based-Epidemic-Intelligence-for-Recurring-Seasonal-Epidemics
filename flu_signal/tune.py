"""Step 4: tune the detection settings on the calibration headline seasons and freeze the best ones.

Every setting (method x cut-off x sustain x margin) is scored on every signal, on the 13 calibration seasons
of USA, AUS and IND only. The best content setting and the best frequency setting are chosen separately
(same grid, same score) among the week-by-week methods, and written to output/frozen_settings.json.
BCP retrospective is scored for comparison with Ganser but never chosen: it uses weeks after the alarm.

When neighbouring cut-offs of the winner tie on score (a plateau), the middle one is frozen, not the edge
(decided 2026-11-07): an edge cut-off is the most likely to flip on new seasons.

Caveat: content's winner is the best of 4 signals x 84 settings, frequency's of 84, so the calibration gap
between them is optimistic. Only the held-out comparison is a fair test.

Run from flu_signal/:

    ../llm-extractor/.venv/bin/python tune.py           # refuses to replace an existing frozen file
    ../llm-extractor/.venv/bin/python tune.py --force   # only before the held-out run
"""

import argparse
import itertools
import json
import subprocess
import sys
from datetime import date

import signal_config as cfg
from build_tables import write_csv
from build_weekly import read_table
from detection import MARGIN_CHOICES, SUSTAIN_CHOICES
from run_detectors import METHODS, SELECTABLE_METHODS, series_by_season, to_week
from scoring import Score, Setting, rank, score_setting

CONTENT_SIGNALS = ("content_articles", "seasonal_articles", "activity_articles", "rising_articles")
FREQUENCY_SIGNAL = "freq_articles"


def calibration_headline_seasons(weekly_rows: list[dict]) -> dict[str, dict]:
    """The series of the calibration seasons of the headline countries. No held-out row is read."""
    seasons = series_by_season(weekly_rows, cfg.SPLIT_CALIBRATION)
    return {season_id: season for season_id, season in seasons.items() if season["headline"]}


def grid(signals: tuple[str, ...]) -> list[Setting]:
    return [Setting(signal, method, cutoff, sustain, margin)
            for signal, method, cutoff, sustain, margin in itertools.product(
                signals, METHODS, cfg.CUTOFF_GRID, SUSTAIN_CHOICES, MARGIN_CHOICES)]


def alarm_weeks(setting: Setting, seasons: dict[str, dict]) -> dict[str, int | None]:
    detect = METHODS[setting.method]
    return {season_id: to_week(detect(season[setting.signal], setting.cutoff, setting.sustain_weeks,
                                      setting.margin).alarm_index)
            for season_id, season in sorted(seasons.items())}


def score_grid(settings: list[Setting], seasons: dict[str, dict]) -> list[tuple[Setting, Score, dict]]:
    scored = []
    for setting in settings:
        weeks = alarm_weeks(setting, seasons)
        scored.append((setting, score_setting(list(weeks.values())), weeks))
    return scored


def best(scored: list[tuple[Setting, Score, dict]], signals: tuple[str, ...]) -> tuple[Setting, Score, dict]:
    candidates = [row for row in scored if row[0].signal in signals and row[0].method in SELECTABLE_METHODS]
    if not candidates:
        raise ValueError(f"no selectable settings for {signals}")
    winner_setting, _ = rank([(setting, score) for setting, score, _ in candidates])[0]
    return next(row for row in candidates if row[0] == winner_setting)


def plateau(winner: tuple[Setting, Score, dict], scored: list[tuple[Setting, Score, dict]]) -> list[tuple]:
    """The run of neighbouring cut-offs (same signal, method, sustain, margin) scoring exactly the winner's score."""
    setting, score, _ = winner
    by_cutoff = {row[0].cutoff: row for row in scored
                 if (row[0].signal, row[0].method, row[0].sustain_weeks, row[0].margin)
                 == (setting.signal, setting.method, setting.sustain_weeks, setting.margin)}
    cutoffs = sorted(by_cutoff)
    start = end = cutoffs.index(setting.cutoff)
    while start > 0 and by_cutoff[cutoffs[start - 1]][1].value == score.value:
        start -= 1
    while end < len(cutoffs) - 1 and by_cutoff[cutoffs[end + 1]][1].value == score.value:
        end += 1
    return [by_cutoff[cutoff] for cutoff in cutoffs[start:end + 1]]


def plateau_middle(winner: tuple[Setting, Score, dict], scored: list[tuple[Setting, Score, dict]]) -> tuple:
    """The middle cut-off of the winner's plateau (the lower middle when the plateau has an even length)."""
    run = plateau(winner, scored)
    return run[(len(run) - 1) // 2]


def neighbour_scores(winner: Setting, scored: list[tuple[Setting, Score, dict]]) -> dict[str, int]:
    """Scores of the same setting at the other cut-offs: a lone peak means the winner may be luck."""
    return {f"{setting.cutoff:.1f}": score.value for setting, score, _ in scored
            if (setting.signal, setting.method, setting.sustain_weeks, setting.margin)
            == (winner.signal, winner.method, winner.sustain_weeks, winner.margin)}


def tuning_rows(scored: list[tuple[Setting, Score, dict]]) -> list[dict]:
    rows = []
    for setting, score, weeks in scored:
        rows.append({"signal": setting.signal, "method": setting.method, "cutoff": setting.cutoff,
                     "sustain_weeks": setting.sustain_weeks, "margin": setting.margin,
                     "selectable": setting.method in SELECTABLE_METHODS, "score": score.value, "hits": score.hits,
                     "false_alarms": score.false_alarms, "misses": score.misses,
                     "median_hit_week": score.median_hit_week,
                     **{season_id: "" if week is None else week for season_id, week in weeks.items()}})
    return rows


def frozen_entry(best_ranked: tuple[Setting, Score, dict], scored: list[tuple[Setting, Score, dict]]) -> dict:
    """The frozen setting: the middle of the best-ranked setting's plateau, with the tie-break on record."""
    setting, score, weeks = plateau_middle(best_ranked, scored)
    return {"signal": setting.signal, "method": setting.method, "cutoff": setting.cutoff,
            "sustain_weeks": setting.sustain_weeks, "margin": setting.margin,
            "tie_break": {"best_ranked_cutoff": best_ranked[0].cutoff,
                          "plateau_cutoffs": [row[0].cutoff for row in plateau(best_ranked, scored)],
                          "rule": "middle cut-off of the plateau"},
            "calibration": {"score": score.value, "hits": score.hits, "false_alarms": score.false_alarms,
                            "misses": score.misses, "median_hit_week": score.median_hit_week,
                            "alarm_weeks": weeks, "score_by_cutoff": neighbour_scores(setting, scored)}}


def git_commit() -> str:
    """The commit of the code that ran, with '-dirty' when there were uncommitted changes."""
    result = subprocess.run(["git", "describe", "--always", "--dirty"], cwd=cfg.SIGNAL_DIR,
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def print_top(scored: list[tuple[Setting, Score, dict]], signals: tuple[str, ...], label: str, top: int = 5) -> None:
    candidates = [(s, sc) for s, sc, _ in scored if s.signal in signals and s.method in SELECTABLE_METHODS]
    print(f"\nTop {top} {label} settings (score = hits - false alarms, of {len(next(iter(scored))[2])} seasons):")
    for setting, score in rank(candidates)[:top]:
        print(f"  {score.value:3}  hits {score.hits:2}  false {score.false_alarms}  median week "
              f"{score.median_hit_week}  {setting.signal} {setting.method} cutoff {setting.cutoff} "
              f"sustain {setting.sustain_weeks} margin {setting.margin}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="replace an existing frozen_settings.json")
    args = parser.parse_args()
    if cfg.FROZEN_SETTINGS_PATH.exists() and not args.force:
        print(f"{cfg.FROZEN_SETTINGS_PATH} exists: the settings are frozen. Use --force only before the held-out run.")
        return 1

    seasons = calibration_headline_seasons(read_table(cfg.WEEKLY_PATH))
    scored = score_grid(grid(CONTENT_SIGNALS + (FREQUENCY_SIGNAL,)), seasons)
    write_csv(cfg.TUNING_PATH, tuning_rows(scored))

    content = best(scored, CONTENT_SIGNALS)
    frequency = best(scored, (FREQUENCY_SIGNAL,))
    frozen = {
        "created": date.today().isoformat(),
        "git_commit": git_commit(),
        "seasons": sorted(seasons),
        "rule": {"hit": f"alarm in weeks -{cfg.EARLY_LIMIT}..{cfg.LAST_WEEK}", "false_alarm": f"before week -{cfg.EARLY_LIMIT}",
                 "score": "hits - false alarms", "chosen_among": list(SELECTABLE_METHODS)},
        "content": frozen_entry(content, scored),
        "frequency": frozen_entry(frequency, scored),
    }
    cfg.FROZEN_SETTINGS_PATH.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")

    print_top(scored, CONTENT_SIGNALS, "content")
    print_top(scored, (FREQUENCY_SIGNAL,), "frequency")
    for role in ("content", "frequency"):
        entry = frozen[role]
        print(f"\nfrozen {role}: {entry['signal']} {entry['method']} cutoff {entry['cutoff']} "
              f"(plateau {entry['tie_break']['plateau_cutoffs']}) sustain {entry['sustain_weeks']} "
              f"margin {entry['margin']}: hits {entry['calibration']['hits']}, "
              f"false alarms {entry['calibration']['false_alarms']}")
    print(f"\n{len(scored)} settings scored -> {cfg.TUNING_PATH}\nfrozen -> {cfg.FROZEN_SETTINGS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
