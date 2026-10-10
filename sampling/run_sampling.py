"""Bucket the stored articles and draw the 1,200-article labeling sample.

Usage (from inside the sampling/ folder):
    python run_sampling.py
    python run_sampling.py --data-dir /path/to/extracted_articles --seed 7
"""
import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from itertools import zip_longest
from pathlib import Path

from bucketing import bucket_article

REPO_DIR = Path(__file__).resolve().parents[1]
STUDY_COUNTRIES = {"USA": "US", "AUS": "AS", "BRA": "BR", "IND": "IN", "KEN": "KE", "IDN": "ID"}  # GDELT country codes

# How many articles to draw from each bucket: 600 likely useful, 600 likely not useful.
QUOTAS = {
    "P_A1_counts": 240, "P_B_trend_response": 200, "P_A2_case_event": 130, "Z_zoonotic_human": 30,
    "N_other_flu_mention": 150, "N_awareness": 110, "N_animal_flu": 75, "N_other_disease": 60,
    "N_no_flu_text": 50, "N_research": 40, "N_history_only": 40, "N_flu_idiom": 30,
    "N_business_policy": 20, "JUNK": 25,   # JUNK = spam + too short + index pages
}
JUNK_BUCKETS = {"X_spam_stub", "X_too_short", "X_listing_garbled"}
COLUMNS = ["record_id", "url", "scan_date", "country", "year", "bucket", "reason"]


def read_articles(data_dir: Path) -> list[dict]:
    """Read <data_dir>/<year>/matched_articles.jsonl into plain dictionaries."""
    articles = []
    for path in sorted(data_dir.glob("*/matched_articles.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    codes = {loc["country_fips"] for loc in rec.get("locations", [])}
                    articles.append({
                        "record_id": rec["gkg_record_id"], "url": rec["url"], "scan_date": rec["datetime"][:10],
                        "text": rec.get("article") or "",
                        "countries": [c for c, code in STUDY_COUNTRIES.items() if code in codes],
                    })
    return articles


def add_buckets(articles: list[dict]) -> None:
    """Give every article a bucket, a reason, a year and one country (its rarest study country)."""
    totals = Counter(c for a in articles for c in a["countries"])
    for a in articles:
        a["year"] = int(a["scan_date"][:4])
        a["bucket"], a["reason"] = bucket_article(a["text"], a["year"])
        # Rarest country first, so Kenya or Indonesia is not hidden behind the USA.
        a["country"] = min(a["countries"], key=lambda c: totals[c]) if a["countries"] else "none"


def draw(articles: list[dict], rng: random.Random) -> list[dict]:
    """Draw each bucket's quota, spreading evenly over country and year."""
    pools = defaultdict(list)
    for a in articles:
        pools["JUNK" if a["bucket"] in JUNK_BUCKETS else a["bucket"]].append(a)

    sample = []
    for name, quota in QUOTAS.items():
        # Group the bucket by (country, year), shuffle each group, then take one from each group in turn.
        groups = defaultdict(list)
        for a in pools[name]:
            groups[(a["country"], a["year"])].append(a)
        for g in groups.values():
            rng.shuffle(g)
        order = list(groups.values())
        rng.shuffle(order)
        turns = (a for round_ in zip_longest(*order) for a in round_ if a is not None)
        sample.extend(a for a, _ in zip(turns, range(quota)))
    return sample


def save(out_dir: Path, articles: list[dict], sample: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "all_articles_buckets.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(articles)
    with open(out_dir / "sample_1200.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sample)
    with open(out_dir / "sample_1200.jsonl", "w", encoding="utf-8") as f:   # includes the article text
        for a in sample:
            f.write(json.dumps({k: a[k] for k in COLUMNS + ["text"]}, ensure_ascii=False) + "\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Bucket stored flu articles and draw the labeling sample.")
    p.add_argument("--data-dir", type=Path, default=REPO_DIR.parent / "extracted_articles")
    p.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "output")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    articles = read_articles(args.data_dir)
    add_buckets(articles)
    sample = draw(articles, random.Random(args.seed))
    save(args.out_dir, articles, sample)

    print(f"read {len(articles)} articles")
    print("buckets:", dict(Counter(a["bucket"] for a in articles).most_common()))
    print(f"sample: {len(sample)}")
    print("  by bucket :", dict(Counter(a["bucket"] for a in sample).most_common()))
    print("  by country:", dict(Counter(a["country"] for a in sample)))
    print("  by year   :", dict(sorted(Counter(a["year"] for a in sample).items())))
    print(f"saved to {args.out_dir}")


if __name__ == "__main__":
    main()
