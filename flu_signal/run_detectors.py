"""Run the change-point detectors on the weekly signals and write output/detections_*.csv.

Calibration seasons only, with the settings given on the command line. --final runs the held-out seasons
with the frozen settings from tune.py (output/frozen_settings.json) and nothing else; it refuses to run
without that file. Run from flu_signal/:

    ../llm-extractor/.venv/bin/python run_detectors.py                 # calibration, cut-off 0.5, sustain 1
    ../llm-extractor/.venv/bin/python run_detectors.py --cutoff 0.6 --sustain-weeks 2 --margin 1
    ../llm-extractor/.venv/bin/python run_detectors.py --final         # once, after tune.py
"""

import argparse
import json
import sys
from collections import defaultdict

import bcp
import bocpd
import signal_config as cfg
from build_tables import write_csv
from build_weekly import read_table
from detection import MARGIN_CHOICES, SUSTAIN_CHOICES
from weekly import SIGNALS

# BOCPD is online by design, so it has only the week-by-week run. BCP has both (decided 2026-11-07).
METHODS = {
    "bcp_retrospective": bcp.retrospective,
    "bcp_prospective": bcp.prospective,
    "bocpd_prospective": bocpd.prospective,
}
DETECTED_SIGNALS = tuple(signal for signal in SIGNALS if signal != "avian_articles")   # avian is a check only
# Only week-by-week methods can be frozen: BCP retrospective uses weeks after the alarm.
SELECTABLE_METHODS = ("bcp_prospective", "bocpd_prospective")
ROLES = ("content", "frequency")


def series_by_season(rows: list[dict], split: str) -> dict[str, dict]:
    """{season_id: {"country", "headline", signal: [12 counts in week order]}} for one split."""
    seasons: dict[str, dict] = defaultdict(lambda: {signal: [] for signal in DETECTED_SIGNALS})
    for row in sorted((r for r in rows if r["split"] == split), key=lambda r: (r["season_id"], int(r["week"]))):
        season = seasons[row["season_id"]]
        season["country"], season["headline"] = row["country"], row["headline"] == "True"
        for signal in DETECTED_SIGNALS:
            season[signal].append(int(row[signal]))
    expected_weeks = cfg.LAST_WEEK - cfg.FIRST_WEEK + 1
    for season_id, season in seasons.items():
        if len(season["freq_articles"]) != expected_weeks:
            raise ValueError(f"{season_id} has {len(season['freq_articles'])} weeks, expected {expected_weeks}")
    return dict(seasons)


def to_week(index: int | None) -> int | None:
    return None if index is None else cfg.FIRST_WEEK + index


def detection_row(season_id: str, season: dict, signal: str, method: str, cutoff: float, sustain_weeks: int,
                  margin: float, role: str = "") -> dict:
    found = METHODS[method](season[signal], cutoff, sustain_weeks, margin)
    return {"season_id": season_id, "country": season["country"], "headline": season["headline"], "role": role,
            "signal": signal, "method": method, "cutoff": cutoff, "sustain_weeks": sustain_weeks, "margin": margin,
            "alarm_week": to_week(found.alarm_index), "change_week": to_week(found.change_index),
            "probability": None if found.probability is None else round(found.probability, 3),
            "total": sum(season[signal])}


def detect_all(seasons: dict[str, dict], cutoff: float, sustain_weeks: int, margin: float = 0.0) -> list[dict]:
    """Every signal x method on every season, with one cut-off, sustain and margin."""
    return [detection_row(season_id, season, signal, method, cutoff, sustain_weeks, margin)
            for season_id, season in sorted(seasons.items())
            for signal in DETECTED_SIGNALS for method in METHODS]


def setting_problems(entry: dict) -> list[str]:
    """Why a frozen setting is not one tune.py could have chosen (empty when it is fine)."""
    checks = [("method", SELECTABLE_METHODS), ("signal", DETECTED_SIGNALS), ("cutoff", cfg.CUTOFF_GRID),
              ("sustain_weeks", SUSTAIN_CHOICES), ("margin", MARGIN_CHOICES)]
    return [f"{field} {entry.get(field)!r} is not one of {allowed}" for field, allowed in checks
            if entry.get(field) not in allowed]


def load_frozen_settings(path=cfg.FROZEN_SETTINGS_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"missing {path}: run tune.py on calibration first; the held-out run needs frozen settings")
    frozen = json.loads(path.read_text(encoding="utf-8"))
    for role in ROLES:
        if role not in frozen:
            raise ValueError(f"{path} has no '{role}' setting")
        problems = setting_problems(frozen[role])
        if problems:
            raise ValueError(f"{path} '{role}' setting is not valid: {'; '.join(problems)}")
    return frozen


def detect_frozen(seasons: dict[str, dict], frozen: dict) -> list[dict]:
    """Only the two frozen settings (content and frequency) on every season."""
    rows = []
    for season_id, season in sorted(seasons.items()):
        for role in ROLES:
            s = frozen[role]
            rows.append(detection_row(season_id, season, s["signal"], s["method"], s["cutoff"],
                                      s["sustain_weeks"], s["margin"], role))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cutoff", type=float, default=0.5, help="posterior probability needed for an alarm")
    parser.add_argument("--sustain-weeks", type=int, default=1, choices=SUSTAIN_CHOICES,
                        help="weeks a rise must stay up before it alarms")
    parser.add_argument("--margin", type=float, default=0.0, choices=MARGIN_CHOICES,
                        help="how far above the earlier level the rise must be (Anscombe scale)")
    parser.add_argument("--final", action="store_true", help="run the held-out seasons with the frozen settings")
    args = parser.parse_args()
    if not 0.0 < args.cutoff < 1.0:
        parser.error("--cutoff must be between 0 and 1")

    weekly_rows = read_table(cfg.WEEKLY_PATH)
    if args.final:
        # The frozen settings on every season: held-out for the headline result, and calibration too
        # (including BRA/KEN/IDN, never tuned on) for the all-38 table. Nothing is retuned here.
        frozen = load_frozen_settings()
        for split in (cfg.SPLIT_HELD_OUT, cfg.SPLIT_CALIBRATION):
            seasons = series_by_season(weekly_rows, split)
            out_path = cfg.OUTPUT_DIR / f"detections_{split}_frozen.csv"
            write_csv(out_path, detect_frozen(seasons, frozen))
            print(f"{len(seasons)} {split} seasons, frozen settings -> {out_path}")
        return 0

    seasons = series_by_season(weekly_rows, cfg.SPLIT_CALIBRATION)
    rows = detect_all(seasons, args.cutoff, args.sustain_weeks, args.margin)
    out_path = cfg.OUTPUT_DIR / f"detections_calibration_c{args.cutoff}_s{args.sustain_weeks}_m{args.margin:g}.csv"
    write_csv(out_path, rows)
    print(f"{len(seasons)} seasons, {len(rows)} detections -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
