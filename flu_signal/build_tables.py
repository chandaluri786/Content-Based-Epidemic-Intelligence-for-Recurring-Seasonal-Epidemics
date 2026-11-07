"""Write output/articles.csv, output/items.csv and output/tables_report.json. Run from flu_signal/:

    ../llm-extractor/.venv/bin/python build_tables.py
"""

import csv
import json
import sys
from collections import Counter

import data_io
import signal_config as cfg
from tables import build_tables, parse_windows


def write_csv(path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"no rows to write to {path}")
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def per_country_counts(articles: list[dict], items: list[dict]) -> dict[str, dict]:
    """Per cohort country: articles in the frequency signal, articles with items, items."""
    frequency, content, item_count = Counter(), Counter(), Counter()
    for row in articles:
        for season in filter(None, row["frequency_seasons"].split(";")):
            frequency[season.split("-")[0]] += 1
        for season in filter(None, row["content_seasons"].split(";")):
            content[season.split("-")[0]] += 1
    for row in items:
        item_count[row["item_country"]] += 1
    return {country: {"frequency_articles": frequency[country], "articles_with_items": content[country],
                      "items": item_count[country]} for country in cfg.COHORT_COUNTRIES.values()}


def main() -> int:
    bucket_rows = data_io.load_pool_buckets()
    layers = data_io.load_filter_layers()
    assignments = data_io.load_season_assignments({row["record_id"] for row in bucket_rows})
    gold = data_io.load_gold_answers()
    llm = data_io.load_llm_answers()
    windows = parse_windows(data_io.load_season_windows())

    articles, items, report = build_tables(bucket_rows, layers, assignments, gold, llm, windows)
    report["per_country"] = per_country_counts(articles, items)

    cfg.OUTPUT_DIR.mkdir(exist_ok=True)
    write_csv(cfg.ARTICLES_PATH, articles)
    write_csv(cfg.ITEMS_PATH, items)
    cfg.TABLES_REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
