"""Step 5 robustness check: leave one season out, over the 22 headline seasons (USA, AUS, IND).

For each season: the full step 4 tuning (grid, score, ranking, plateau-middle rule, content and frequency
separately) is redone on the other 21 seasons, and the two chosen settings are scored on the left-out one.
Run only after the headline result is written. Run from flu_signal/:

    ../llm-extractor/.venv/bin/python loso.py
    ../llm-extractor/.venv/bin/python loso.py --items    # item signals, post hoc (COMBINED_SIGNAL_RULES.md)

A detector's alarm in one season does not depend on the other seasons, so every setting's alarm week is
worked out once per season, and each fold only re-scores and re-ranks.
"""

import json
import sys
from collections import Counter
from datetime import date, timedelta
from statistics import median_low

import signal_config as cfg
from detection import DEFAULT_TRANSFORM
from build_tables import write_csv
from build_weekly import read_table
import bcp
import bocpd
from detection import SUSTAIN_CHOICES
from evaluate import season_row, summarize
from run_detectors import SELECTABLE_METHODS, series_by_season, to_week
from scoring import Setting, classify, score_setting
from tune import CONTENT_SIGNALS, FREQUENCY_SIGNAL, alarm_weeks, choose, grid, score_weeks

LOSO_PATH = cfg.OUTPUT_DIR / "loso_results.csv"
LOSO_SUMMARY_PATH = cfg.OUTPUT_DIR / "loso_summary.json"


def headline_seasons(weekly_rows: list[dict]) -> dict[str, dict]:
    seasons = {**series_by_season(weekly_rows, cfg.SPLIT_CALIBRATION), **series_by_season(weekly_rows, cfg.SPLIT_HELD_OUT)}
    return {season_id: season for season_id, season in seasons.items() if season["headline"]}


def fold(left_out: str, weeks_by_setting: dict, seasons: dict[str, dict], early_limit: int = cfg.EARLY_LIMIT,
         content_signals: tuple[str, ...] = CONTENT_SIGNALS) -> dict:
    """Tune on every season but `left_out`, then score the two chosen settings on `left_out`."""
    training = [season_id for season_id in sorted(seasons) if season_id != left_out]
    scored = score_weeks(weeks_by_setting, training, early_limit)
    chosen = {role: choose(scored, signals)[0]
              for role, signals in (("content", content_signals), ("frequency", (FREQUENCY_SIGNAL,)))}
    row = season_row(left_out, seasons[left_out]["country"], weeks_by_setting[chosen["content"]][left_out],
                     weeks_by_setting[chosen["frequency"]][left_out], early_limit, trained_on=len(training))
    for role, setting in chosen.items():
        row[f"{role}_setting"] = setting_label(setting)
    return row


def setting_label(setting: Setting) -> str:
    return (f"{setting.signal} {setting.method} cutoff {setting.cutoff} "
            f"sustain {setting.sustain_weeks} margin {setting.margin}")


def headline_weeks(seasons: dict[str, dict], signals: tuple[str, ...] = CONTENT_SIGNALS + (FREQUENCY_SIGNAL,),
                   transform: str = DEFAULT_TRANSFORM) -> dict:
    """Every grid setting's alarm week in every season, worked out once."""
    return {setting: alarm_weeks(setting, seasons, transform) for setting in grid(signals)}


def run_loso(seasons: dict[str, dict], early_limit: int = cfg.EARLY_LIMIT,
             content_signals: tuple[str, ...] = CONTENT_SIGNALS, weeks_by_setting: dict | None = None) -> list[dict]:
    weeks = weeks_by_setting if weeks_by_setting is not None else headline_weeks(seasons)
    return [fold(season_id, weeks, seasons, early_limit, content_signals) for season_id in sorted(seasons)]


def main() -> int:
    if "--items" in sys.argv[1:]:
        return items_main()
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


# ---------------------------------------------------------------------------------------------------------------
# Item signals (post hoc, 2026-11-19): COMBINED_SIGNAL_RULES.md; section numbers below refer to it. Nothing here
# changes the run above or its outputs.
# ---------------------------------------------------------------------------------------------------------------

ITEM_ONSET = "item_onset"                                  # 5: the earliest alarm of the five item series
ITEM_ONSET_NO_SUSPICION = "item_onset_no_suspicion"        # 8: the same without the suspicion series
ARTICLE_SIGNALS = (FREQUENCY_SIGNAL, "content_articles")   # read from weekly_signals.csv
BASELINES = (FREQUENCY_SIGNAL,)                           # the performance baseline: GDELT tag frequency
CANDIDATES = ("content_articles", *cfg.ITEM_SERIES, ITEM_ONSET, ITEM_ONSET_NO_SUSPICION)
MAIN = {"candidate": ITEM_ONSET, "baseline": FREQUENCY_SIGNAL, "early_limit": cfg.EARLY_LIMIT}
ITEMS_NOTE = ("post hoc: designed 2026-11-19, after the held-out results; exploratory. Rules: "
              "COUNT_SIGNAL_RULES.md and COMBINED_SIGNAL_RULES.md.")


def _rise_in_data_so_far(method: str, seen: list[int], cutoff: float, sustain_weeks: int, margin: float) -> bool:
    """Does the detector, run on the weeks seen so far, report a lasting rise? BCP: one run on those weeks, from
    bcp.MIN_WEEKS weeks on (bcp.prospective makes the same check week by week). BOCPD: a confirmed alarm within
    those weeks (it is online, so earlier weeks never read later ones)."""
    if method == "bcp_prospective":
        return len(seen) >= bcp.MIN_WEEKS and bcp.first_rising_change(seen, cutoff, sustain_weeks, margin).change_index is not None
    if method == "bocpd_prospective":
        return len(seen) >= bocpd.PRIOR_WEEKS and bocpd.prospective(seen, cutoff, sustain_weeks, margin).alarm_index is not None
    raise ValueError(f"{method} is not a week-by-week method")


def realtime_alarm(method: str, vintages: list[list[int]], cutoff: float, sustain_weeks: int,
                   margin: float = cfg.ITEM_MARGIN) -> int | None:
    """Section 3-4: the first season week t at which the detector, run on the series as known at the end of week
    t (vintages[t], weeks up to t), reports a lasting rise. For a series that is never revised (every vintage
    the same) this is the detector's own prospective alarm."""
    for t, vintage in enumerate(vintages):
        if _rise_in_data_so_far(method, vintage[:t + 1], cutoff, sustain_weeks, margin):
            return to_week(t)
    return None


def item_grid(signals: tuple[str, ...]) -> list[Setting]:
    """Section 6: the existing week-by-week methods, cut-offs and sustain choices, with the margin fixed."""
    return [Setting(signal, method, cutoff, sustain, cfg.ITEM_MARGIN) for signal in signals
            for method in SELECTABLE_METHODS for cutoff in cfg.CUTOFF_GRID for sustain in SUSTAIN_CHOICES]


def item_seasons(weekly_rows: list[dict], item_weekly_rows: list[dict], vintage_rows: list[dict]) -> dict[str, dict]:
    """{season_id: {"country", "headline", "vintages": {signal: [12 series, one per as-of week]}}} for the headline
    seasons. Article signals are counted by scan date and never revised, so all their vintages are the same."""
    weeks = cfg.LAST_WEEK - cfg.FIRST_WEEK + 1
    seasons: dict[str, dict] = {}
    for season_id, season in headline_seasons(weekly_rows).items():
        series = {signal: season[signal] for signal in ARTICLE_SIGNALS}
        seasons[season_id] = {"country": season["country"], "headline": True,
                              "vintages": {signal: [values] * weeks for signal, values in series.items()}}
    item_weekly_seasons = {row["season_id"] for row in item_weekly_rows}
    vintage_seasons = {row["season_id"] for row in vintage_rows}
    stale = sorted(set(seasons) - (item_weekly_seasons & vintage_seasons))
    if stale:
        raise ValueError(f"{cfg.ITEM_WEEKLY_PATH.name} / {cfg.ITEM_VINTAGES_PATH.name} have no rows for {stale}: "
                         f"they are older than {cfg.WEEKLY_PATH.name}; run build_weekly.py again")
    grid_rows: dict[tuple, list] = {}
    for row in vintage_rows:
        if row["season_id"] in seasons:
            key = (row["season_id"], row["signal"], int(row["as_of_week"]))
            grid_rows.setdefault(key, []).append((int(row["week"]), int(row["value"])))
    for season_id, season in seasons.items():
        for signal in cfg.ITEM_SERIES:
            season["vintages"][signal] = [[value for _, value in sorted(grid_rows[(season_id, signal, as_of)])]
                                          for as_of in range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1)]
    for season_id, season in seasons.items():
        for signal, vintages in season["vintages"].items():
            if len(vintages) != weeks or any(len(v) != weeks for v in vintages):
                raise ValueError(f"{season_id} {signal}: expected {weeks} vintages of {weeks} weeks")
    return seasons


def item_alarm_weeks(seasons: dict[str, dict]) -> dict[Setting, dict]:
    """Every setting's alarm week in every season, for every signal, plus the item onset alarms (Section 5): for each
    method, cut-off and sustain, the earliest alarm week among the series (one shared setting)."""
    signals = (*BASELINES, "content_articles", *cfg.ITEM_SERIES)
    weeks = {setting: {season_id: realtime_alarm(setting.method, season["vintages"][setting.signal], setting.cutoff,
                                                 setting.sustain_weeks, setting.margin)
                       for season_id, season in sorted(seasons.items())}
             for setting in item_grid(signals)}
    members = {ITEM_ONSET: tuple(cfg.ITEM_SERIES),
               ITEM_ONSET_NO_SUSPICION: tuple(s for s in cfg.ITEM_SERIES if s not in cfg.SUSPICION_SERIES)}
    for onset, series in members.items():
        for setting in item_grid((onset,)):
            per_series = [weeks[Setting(s, setting.method, setting.cutoff, setting.sustain_weeks, setting.margin)]
                          for s in series]
            weeks[setting] = {season_id: min((w[season_id] for w in per_series if w[season_id] is not None),
                                             default=None) for season_id in sorted(seasons)}
    return weeks


def decision(summary: dict) -> str:
    """Section 8: better when both conditions hold, not better when neither, mixed when one."""
    score_ok = summary["content"]["score"] >= summary["frequency"]["score"]
    wins_ok = summary["content_wins"] > summary["frequency_wins"]
    return "better" if score_ok and wins_ok else ("not better" if not (score_ok or wins_ok) else "mixed")


def item_folds(weeks: dict, seasons: dict[str, dict], early_limit: int) -> list[dict]:
    """Leave one season out for every candidate against every baseline. Each fold scores the settings on the other
    seasons only, and chooses each signal's setting with the existing step 4 rule (tune.choose)."""
    rows = []
    for left_out in sorted(seasons):
        training = [season_id for season_id in sorted(seasons) if season_id != left_out]
        scored = score_weeks(weeks, training, early_limit)
        chosen = {signal: choose(scored, (signal,))[0] for signal in (*BASELINES, *CANDIDATES)}
        for baseline in BASELINES:
            for candidate in CANDIDATES:
                cand, base = chosen[candidate], chosen[baseline]
                rows.append(season_row(left_out, seasons[left_out]["country"], weeks[cand][left_out],
                                       weeks[base][left_out], early_limit, candidate=candidate, baseline=baseline,
                                       early_limit_week=-early_limit, trained_on=len(training),
                                       candidate_setting=setting_label(cand), baseline_setting=setting_label(base),
                                       candidate_sustain=cand.sustain_weeks))
    return rows


def grade_rows(weeks: dict, fold_rows: list[dict]) -> list[dict]:
    """Section 5: for the main comparison, the series that triggered each season's item onset alarm, the grade at the
    alarm and the grade in every later week (the most serious series that has alarmed so far)."""
    rows = []
    for row in fold_rows:
        if (row["candidate"], row["baseline"]) != (ITEM_ONSET, FREQUENCY_SIGNAL):
            continue
        _, method, _, cutoff, _, sustain, _, margin = row["candidate_setting"].split()
        series_weeks = {s: weeks[Setting(s, method, float(cutoff), int(sustain), float(margin))][row["season_id"]]
                        for s in cfg.ITEM_SERIES}
        onset = row["content_alarm_week"]
        triggers = sorted(s for s, w in series_weeks.items() if onset is not None and w == onset)
        out = {"season_id": row["season_id"], "country": row["country"], "early_limit_week": row["early_limit_week"],
               "setting": row["candidate_setting"], "item_onset_week": onset, "outcome": row["content_outcome"],
               "triggered_by": ";".join(triggers),
               "grade_at_alarm": max((cfg.ITEM_GRADES[s] for s in triggers), default=None),
               **{f"{s}_alarm_week": series_weeks[s] for s in cfg.ITEM_SERIES}}
        for week in range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1):
            alarmed = [cfg.ITEM_GRADES[s] for s, w in series_weeks.items() if w is not None and w <= week]
            out[f"grade_week_{week}"] = max(alarmed) if onset is not None and week >= onset else None
        rows.append(out)
    return rows


def coverage_rows(seasons: dict[str, dict]) -> list[dict]:
    """How much data each item series has per season (the final vintage)."""
    rows = []
    for season_id, season in sorted(seasons.items()):
        for signal in cfg.ITEM_SERIES:
            final = season["vintages"][signal][-1]
            rows.append({"season_id": season_id, "country": season["country"], "signal": signal,
                         "weeks_with_value": sum(1 for v in final if v > 0), "weeks": len(final), "total": sum(final)})
    return rows


CALENDAR = "calendar_usual_onset"


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def calendar_alarm_weeks(weekly_rows: list[dict]) -> dict[str, int | None]:
    """A reference with no news at all: each headline season "alarms" in the ISO week of the usual onset date,
    the median (lower median) day offset from 1 January of the season year over the same country's other
    headline seasons. Leave one season out, like the detectors. A date before the window counts as an alarm in
    its first week (a false alarm either way); one after the window is a miss."""
    onsets = {}
    for row in weekly_rows:
        if row["headline"] == "True":
            onsets[row["season_id"]] = (row["country"], int(row["season_year"]), date.fromisoformat(row["onset_date"]))
    weeks = {}
    for season_id, (country, year, onset) in sorted(onsets.items()):
        offsets = [(o - date(y, 1, 1)).days for other, (c, y, o) in onsets.items() if c == country and other != season_id]
        if not offsets:
            weeks[season_id] = None
            continue
        usual = date(year, 1, 1) + timedelta(days=median_low(offsets))
        week = (_monday(usual) - _monday(onset)).days // 7
        weeks[season_id] = None if week > cfg.LAST_WEEK else max(week, cfg.FIRST_WEEK)
    return weeks


def calendar_reference(weekly_rows: list[dict]) -> dict:
    """The calendar reference scored at each early limit, overall and by country (no tuning, no wins test)."""
    weeks = calendar_alarm_weeks(weekly_rows)
    countries = {season_id: season_id.split("-")[0] for season_id in weeks}

    def scored(season_ids: list[str], limit: int) -> dict:
        score = score_setting([weeks[s] for s in season_ids], limit)
        return {"hits": score.hits, "false_alarms": score.false_alarms, "misses": score.misses, "score": score.value}

    return {
        "signal": CALENDAR,
        "note": "reference only: alarm in the ISO week of the country's usual onset date (other seasons' median)",
        "by_early_limit": {
            str(-limit): {**scored(sorted(weeks), limit),
                          "by_country": {c: scored(sorted(s for s in weeks if countries[s] == c), limit)
                                         for c in sorted(set(countries.values()))},
                          "seasons": {s: {"alarm_week": weeks[s], "outcome": classify(weeks[s], limit)}
                                      for s in sorted(weeks)}}
            for limit in cfg.ITEM_EARLY_LIMITS},
    }


def items_summary(fold_rows: list[dict], calendar: dict | None = None) -> dict:
    groups: dict[tuple, list] = {}
    for row in fold_rows:
        groups.setdefault((row["baseline"], row["early_limit_week"], row["candidate"]), []).append(row)
    comparisons = []
    for (baseline, limit, candidate), rows in sorted(groups.items()):
        summary = summarize(rows)
        comparisons.append({
            "candidate": candidate, "baseline": baseline, "early_limit_week": limit,
            "decision": decision(summary), **summary,
            "candidate_sustain_chosen": dict(sorted(Counter(r["candidate_sustain"] for r in rows).items())),
            "candidate_settings_chosen": dict(Counter(r["candidate_setting"] for r in rows).most_common()),
            "by_country": {country: summarize([r for r in rows if r["country"] == country])
                           for country in sorted({r["country"] for r in rows})},
        })
    main = next(c for c in comparisons if (c["candidate"], c["baseline"], c["early_limit_week"])
                == (MAIN["candidate"], MAIN["baseline"], -MAIN["early_limit"]))
    summary = {"post_hoc": True, "note": ITEMS_NOTE, "main_comparison": MAIN, "main_decision": main["decision"],
               "comparisons": comparisons}
    if calendar is not None:
        summary["calendar_reference"] = calendar
    return summary


def items_main() -> int:
    missing = [path.name for path in (cfg.WEEKLY_PATH, cfg.ITEM_WEEKLY_PATH, cfg.ITEM_VINTAGES_PATH) if not path.exists()]
    if missing:
        print(f"missing {', '.join(missing)} in {cfg.OUTPUT_DIR}: run build_weekly.py first (it needs "
              f"{cfg.ARTICLES_PATH.name}, {cfg.ITEMS_PATH.name} and season_windows.json)")
        return 1
    weekly_rows = read_table(cfg.WEEKLY_PATH)
    seasons = item_seasons(weekly_rows, read_table(cfg.ITEM_WEEKLY_PATH), read_table(cfg.ITEM_VINTAGES_PATH))
    weeks = item_alarm_weeks(seasons)
    fold_rows = [row for limit in cfg.ITEM_EARLY_LIMITS for row in item_folds(weeks, seasons, limit)]
    summary = items_summary(fold_rows, calendar_reference(weekly_rows))
    write_csv(cfg.LOSO_ITEMS_SEASONS_PATH, fold_rows)
    write_csv(cfg.LOSO_ITEMS_TRIGGERS_PATH, grade_rows(weeks, fold_rows))
    write_csv(cfg.LOSO_ITEMS_COVERAGE_PATH, coverage_rows(seasons))
    cfg.LOSO_ITEMS_SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for c in summary["comparisons"]:
        print(f"{c['baseline']:<24} {c['early_limit_week']:>3} {c['candidate']:<24} "
              f"{c['content']['hits']}/{c['content']['false_alarms']}/{c['content']['misses']} "
              f"score {c['content']['score']:>3} | base {c['frequency']['hits']}/{c['frequency']['false_alarms']}/"
              f"{c['frequency']['misses']} score {c['frequency']['score']:>3} | wins {c['content_wins']}-"
              f"{c['frequency_wins']}-{c['ties']} {c['decision']}")
    for limit, ref in summary["calendar_reference"]["by_early_limit"].items():
        print(f"{'reference':<24} {limit:>3} {CALENDAR:<24} {ref['hits']}/{ref['false_alarms']}/{ref['misses']} "
              f"score {ref['score']:>3}")
    print(f"\nmain ({MAIN['candidate']} vs {MAIN['baseline']}, -{MAIN['early_limit']}): {summary['main_decision']}")
    for path in (cfg.LOSO_ITEMS_SEASONS_PATH, cfg.LOSO_ITEMS_TRIGGERS_PATH, cfg.LOSO_ITEMS_COVERAGE_PATH,
                 cfg.LOSO_ITEMS_SUMMARY_PATH):
        print(f"-> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
