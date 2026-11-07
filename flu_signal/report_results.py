"""Step 5: build the results tables from the frozen detections. Run from flu_signal/, after
`run_detectors.py --final`:

    ../llm-extractor/.venv/bin/python report_results.py

Writes output/results_headline.csv (the 9 held-out USA/AUS/IND seasons), output/results_all38.csv (every
season with the frozen settings; calibration seasons flagged tuned_on) and output/results_summary.json.
The rules are in evaluate.py; they were fixed before the held-out run.
"""

import json
import sys

import signal_config as cfg
from build_tables import write_csv
from build_weekly import read_table
from evaluate import CONTENT, FREQUENCY, season_row, summarize

HELD_OUT_DETECTIONS = cfg.OUTPUT_DIR / f"detections_{cfg.SPLIT_HELD_OUT}_frozen.csv"
CALIBRATION_DETECTIONS = cfg.OUTPUT_DIR / f"detections_{cfg.SPLIT_CALIBRATION}_frozen.csv"
HEADLINE_PATH = cfg.OUTPUT_DIR / "results_headline.csv"
ALL38_PATH = cfg.OUTPUT_DIR / "results_all38.csv"
SUMMARY_PATH = cfg.OUTPUT_DIR / "results_summary.json"


def _week(value: str) -> int | None:
    return int(value) if value not in ("", None) else None


def paired_rows(detections: list[dict], split: str) -> list[dict]:
    """One results row per season from detections with one content and one frequency row per season."""
    by_season: dict[str, dict] = {}
    for row in detections:
        by_season.setdefault(row["season_id"], {})[row["role"]] = row
    rows = []
    for season_id, roles in sorted(by_season.items()):
        if set(roles) != {CONTENT, FREQUENCY}:
            raise ValueError(f"{season_id} needs one content and one frequency detection, has {sorted(roles)}")
        headline = roles[CONTENT]["headline"] == "True"
        rows.append(season_row(season_id, roles[CONTENT]["country"], _week(roles[CONTENT]["alarm_week"]),
                               _week(roles[FREQUENCY]["alarm_week"]), split=split, headline=headline,
                               tuned_on=split == cfg.SPLIT_CALIBRATION and headline))
    return rows


def per_country(rows: list[dict]) -> dict[str, dict]:
    countries = sorted({row["country"] for row in rows})
    return {country: summarize([row for row in rows if row["country"] == country]) for country in countries}


def build_report(held_out: list[dict], calibration: list[dict]) -> tuple[list[dict], list[dict], dict]:
    held_out_rows = paired_rows(held_out, cfg.SPLIT_HELD_OUT)
    all_rows = held_out_rows + paired_rows(calibration, cfg.SPLIT_CALIBRATION)
    headline_rows = [row for row in held_out_rows if row["headline"]]
    not_tuned = [row for row in all_rows if not row["tuned_on"]]
    summary = {
        "headline_held_out": summarize(headline_rows),
        "held_out_all_countries": summarize(held_out_rows),
        "all_38": summarize(all_rows),
        "all_38_not_tuned_on": summarize(not_tuned),
        "per_country_all_38": per_country(all_rows),
    }
    return headline_rows, sorted(all_rows, key=lambda row: row["season_id"]), summary


def print_headline(rows: list[dict], summary: dict) -> None:
    print("Held-out headline seasons (alarm week, onset = 0; '-' = no alarm):")
    for row in rows:
        content, frequency = row["content_alarm_week"], row["frequency_alarm_week"]
        print(f"  {row['season_id']:9} content {'-' if content is None else content:>3} ({row['content_outcome']:11}) "
              f"frequency {'-' if frequency is None else frequency:>3} ({row['frequency_outcome']:11}) "
              f"winner {row['winner']}")
    print(json.dumps(summary, indent=2))


def main() -> int:
    for path in (HELD_OUT_DETECTIONS, CALIBRATION_DETECTIONS):
        if not path.exists():
            print(f"missing {path}: run run_detectors.py --final first")
            return 1
    headline_rows, all_rows, summary = build_report(read_table(HELD_OUT_DETECTIONS), read_table(CALIBRATION_DETECTIONS))
    write_csv(HEADLINE_PATH, headline_rows)
    write_csv(ALL38_PATH, all_rows)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print_headline(headline_rows, summary["headline_held_out"])
    print(f"\n-> {HEADLINE_PATH}\n-> {ALL38_PATH}\n-> {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
