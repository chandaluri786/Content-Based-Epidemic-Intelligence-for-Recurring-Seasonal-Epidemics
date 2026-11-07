"""Run the change-point detectors on the weekly signals and write output/detections_<split>.csv.

Calibration seasons only, unless --final is given. Held-out seasons are run once, after the content
signal and the cut-off are frozen on calibration (step 4). Run from flu_signal/:

    ../llm-extractor/.venv/bin/python run_detectors.py                 # calibration, cut-off 0.5, sustain 1
    ../llm-extractor/.venv/bin/python run_detectors.py --cutoff 0.6 --sustain-weeks 2
"""

import argparse
import sys
from collections import defaultdict

import bcp
import bocpd
import signal_config as cfg
from build_tables import write_csv
from build_weekly import read_table
from detection import SUSTAIN_CHOICES
from weekly import SIGNALS

# BOCPD is online by design, so it has only the week-by-week run. BCP has both (decided 2026-11-07).
METHODS = {
    "bcp_retrospective": bcp.retrospective,
    "bcp_prospective": bcp.prospective,
    "bocpd_prospective": bocpd.prospective,
}
DETECTED_SIGNALS = tuple(signal for signal in SIGNALS if signal != "avian_articles")   # avian is a check only


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


def detect_all(seasons: dict[str, dict], cutoff: float, sustain_weeks: int) -> list[dict]:
    rows = []
    for season_id, season in sorted(seasons.items()):
        for signal in DETECTED_SIGNALS:
            for method, detect in METHODS.items():
                found = detect(season[signal], cutoff, sustain_weeks)
                rows.append({"season_id": season_id, "country": season["country"], "headline": season["headline"],
                             "signal": signal, "method": method, "cutoff": cutoff, "sustain_weeks": sustain_weeks,
                             "alarm_week": to_week(found.alarm_index), "change_week": to_week(found.change_index),
                             "probability": None if found.probability is None else round(found.probability, 3),
                             "total": sum(season[signal])})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cutoff", type=float, default=0.5, help="posterior probability needed for an alarm")
    parser.add_argument("--sustain-weeks", type=int, default=1, choices=SUSTAIN_CHOICES,
                        help="weeks a rise must stay up before it alarms")
    parser.add_argument("--final", action="store_true", help="run the held-out seasons (once, after freezing)")
    args = parser.parse_args()
    if not 0.0 < args.cutoff < 1.0:
        parser.error("--cutoff must be between 0 and 1")

    split = cfg.SPLIT_HELD_OUT if args.final else cfg.SPLIT_CALIBRATION
    seasons = series_by_season(read_table(cfg.WEEKLY_PATH), split)
    rows = detect_all(seasons, args.cutoff, args.sustain_weeks)
    out_path = cfg.OUTPUT_DIR / f"detections_{split}_sustain{args.sustain_weeks}.csv"
    write_csv(out_path, rows)
    print(f"{len(seasons)} {split} seasons, {len(rows)} detections -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
