"""Step 2: apply the keyword filter and write the extractor's input for the whole pool.

The team chose the keyword filter alone (no classifier): in gold it drops no useful article. An
article goes to the LLM when it is not in gold and it is in a P_/Z_ bucket or has a flu word.

Reads data/pool_texts.jsonl and the gold labels. Writes output/filter_decisions.csv (every pool
article with its layer and gold flag) and output/pool_articles.json (the articles to send, in the
format of llm-extractor/data/articles.json). Run from usefulness_filter/:

    ../llm-extractor/.venv/bin/python pool_articles.py
    cd ../llm-extractor && .venv/bin/python run_extraction.py --articles-file ../usefulness_filter/output/pool_articles.json
"""

import csv
import json
import sys
from collections import Counter

import filter_config as cfg
from data_io import load_gold_useful
from layers import keyword_hits, layer_for

KNOWN_LAYERS = (cfg.LAYER_KEEP_BUCKET, cfg.LAYER_DROP_KEYWORD, cfg.LAYER_FLU_WORD)
DECISION_COLUMNS = ("record_id", "bucket", "country", "year", "layer", "keyword_hits", "in_gold")


def decide_layers(texts: list[dict], gold_ids: set[str]) -> list[dict]:
    """One decision row per pool article, in pool order."""
    rows = []
    for record in texts:
        hits = keyword_hits(record["article"])
        rows.append({"record_id": record["record_id"], "bucket": record["bucket"], "country": record["country"],
                     "year": record["year"], "layer": layer_for(record["bucket"], hits), "keyword_hits": hits,
                     "in_gold": record["record_id"] in gold_ids})
    return rows


def gold_check(decisions: list[dict], gold_useful: dict[str, bool]) -> tuple[int, int]:
    """(useful gold articles the keyword layer drops, useful gold articles in all)."""
    layers = {row["record_id"]: row["layer"] for row in decisions}
    missing = [article_id for article_id in gold_useful if article_id not in layers]
    if missing:
        raise ValueError(f"{len(missing)} gold articles are not in the pool, e.g. {missing[:5]}")
    useful = [article_id for article_id, is_useful in gold_useful.items() if is_useful]
    return sum(layers[article_id] == cfg.LAYER_DROP_KEYWORD for article_id in useful), len(useful)


def is_call_to_make(row: dict) -> bool:
    """True when the article goes to the LLM: it is not dropped by the keyword layer and not in gold."""
    if row["layer"] not in KNOWN_LAYERS:
        raise ValueError(f"article {row['record_id']}: unknown layer {row['layer']!r}")
    return row["layer"] != cfg.LAYER_DROP_KEYWORD and not row["in_gold"]


def build_pool_articles(decisions: list[dict], texts: list[dict]) -> list[dict]:
    """The articles to send, in decision order, each in the extractor's format."""
    by_id = {record["record_id"]: record for record in texts}
    articles, missing = [], []
    for row in decisions:
        if not is_call_to_make(row):
            continue
        record = by_id.get(row["record_id"])
        if record is None or not (record.get("article") or "").strip():
            missing.append(row["record_id"])
            continue
        articles.append({"article_id": record["record_id"], "scan_date": record["scan_date"],
                         "link": record["link"], "sources": [], "article": record["article"]})
    if missing:
        raise ValueError(f"{len(missing)} articles to send have no text, e.g. {missing[:5]}")
    return articles


def write_decisions(decisions: list[dict]) -> None:
    cfg.OUTPUT_DIR.mkdir(exist_ok=True)
    with open(cfg.DECISIONS_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DECISION_COLUMNS)
        writer.writeheader()
        writer.writerows(decisions)


def main() -> int:
    with open(cfg.POOL_TEXTS_PATH, encoding="utf-8") as f:
        texts = [json.loads(line) for line in f if line.strip()]
    gold_useful = load_gold_useful()
    decisions = decide_layers(texts, set(gold_useful))
    try:
        lost, useful = gold_check(decisions, gold_useful)
        articles = build_pool_articles(decisions, texts)
    except ValueError as error:
        print(f"stopped: {error}")
        return 1
    write_decisions(decisions)
    cfg.POOL_ARTICLES_PATH.write_text(json.dumps(articles, ensure_ascii=False), encoding="utf-8")
    print(f"layers of the {len(decisions)} pool articles: {dict(Counter(row['layer'] for row in decisions))}")
    print(f"useful gold articles dropped by the keyword layer: {lost} of {useful}")
    print(f"wrote {len(articles)} articles to send to {cfg.POOL_ARTICLES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
