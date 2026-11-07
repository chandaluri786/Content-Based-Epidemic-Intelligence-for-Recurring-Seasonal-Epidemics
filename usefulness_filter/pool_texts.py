"""Step 1: copy the texts of the 50,640 eligible articles out of the 2 GB pool file.

Streams repo/output/pool/pooled_articles.jsonl line by line and writes data/pool_texts.jsonl
(record_id, bucket, country, year, scan_date, link, article), in the order of the bucket list.

    ../llm-extractor/.venv/bin/python pool_texts.py
"""

import json
import sys

import filter_config as cfg
from data_io import load_pool_buckets


def main() -> int:
    pool_rows = load_pool_buckets()
    wanted = {row["record_id"]: row for row in pool_rows}
    texts: dict[str, str] = {}
    bad_lines = 0
    with open(cfg.POOL_TEXTS_SOURCE, encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            rid = record.get("gkg_record_id")
            if rid in wanted and rid not in texts:
                texts[rid] = record.get("article") or ""
    missing = [rid for rid in wanted if rid not in texts]
    if missing:
        print(f"stopped: {len(missing)} eligible articles have no text in the pool, e.g. {missing[:5]}")
        return 1
    cfg.DATA_DIR.mkdir(exist_ok=True)
    with open(cfg.POOL_TEXTS_PATH, "w", encoding="utf-8") as out:
        for row in pool_rows:
            out.write(json.dumps({"record_id": row["record_id"], "bucket": row["bucket"],
                                  "country": row["country"], "year": row["year"],
                                  "scan_date": row["scan_date"], "link": row["url"],
                                  "article": texts[row["record_id"]]}, ensure_ascii=False) + "\n")
    print(f"wrote {len(pool_rows)} texts to {cfg.POOL_TEXTS_PATH} ({bad_lines} unreadable pool lines skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
