"""Write output/weekly_signals.csv and output/weekly_report.json from the step 1 tables. Run from flu_signal/:

    ../llm-extractor/.venv/bin/python build_weekly.py
"""

import csv
import json
import sys
from collections import Counter

import data_io
import signal_config as cfg
from build_tables import write_csv
from tables import parse_windows
from weekly import SIGNALS, build_weekly


def read_table(path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"missing {path}: run build_tables.py first")
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def season_totals(rows: list[dict]) -> dict[str, dict]:
    """{season_id: {split, headline, signal totals}}."""
    totals: dict[str, dict] = {}
    for row in rows:
        season = totals.setdefault(row["season_id"], {"split": row["split"], "headline": row["headline"],
                                                       **{signal: 0 for signal in SIGNALS}})
        for signal in SIGNALS:
            season[signal] += row[signal]
    return totals


def main() -> int:
    windows = parse_windows(data_io.load_season_windows())
    rows = build_weekly(read_table(cfg.ARTICLES_PATH), read_table(cfg.ITEMS_PATH), windows)
    write_csv(cfg.WEEKLY_PATH, rows)

    totals = season_totals(rows)
    groups = Counter((t["split"], "headline" if t["headline"] else "other") for t in totals.values())
    report = {
        "seasons": len(totals),
        "weeks_per_season": cfg.LAST_WEEK - cfg.FIRST_WEEK + 1,
        "seasons_by_split": {f"{split}/{group}": n for (split, group), n in sorted(groups.items())},
        "per_season": totals,
    }
    cfg.WEEKLY_REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["seasons_by_split"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
