"""Bucket the pooled articles and draw the 1,200-article labeling sample.

Reads the de-duplicated pool built by prepare_pool.py (data-extraction-pipline branch):
only articles assigned to a country-season are eligible, and only one article per
near-duplicate group, so one story can't appear twice in the sample.

Usage:
    python sampling/run_sampling.py --pool-dir /path/to/output/pool
    python sampling/run_sampling.py --pool-dir /path/to/output/pool --seed 7
"""
import argparse
import ast
import csv
import json
import random
from collections import Counter, defaultdict
from datetime import date
from itertools import zip_longest
from pathlib import Path

from bucketing import bucket_article

# How many articles to draw from each bucket: 600 likely useful, 600 likely not useful.
QUOTAS = {
    "P_A1_counts": 240, "P_B_trend_response": 200, "P_A2_case_event": 130, "Z_zoonotic_human": 30,
    "N_other_flu_mention": 150, "N_awareness": 110, "N_animal_flu": 75, "N_other_disease": 60,
    "N_no_flu_text": 50, "N_research": 40, "N_history_only": 40, "N_flu_idiom": 30,
    "N_business_policy": 20, "JUNK": 25,   # JUNK = spam + too short + index pages
}
JUNK_BUCKETS = {"X_spam_stub", "X_too_short", "X_listing_garbled"}
COLUMNS = ["record_id", "url", "scan_date", "country", "season", "phase", "year", "bucket", "reason",
           "near_dup_group", "group_size"]

# Windows run from 10 weeks before onset to 2 weeks after. Weeks -10..-6 are "early",
# -5..-1 "late" (just before onset), 0..2 "post".
LATE_PHASE_FIRST_WEEK = -5


def phase_of(scan_date: date, onset: date) -> str:
    """Where in the season window the article falls: early, late (just before onset) or post."""
    weeks = (scan_date - onset).days // 7
    if weeks >= 0:
        return "post"
    return "late" if weeks >= LATE_PHASE_FIRST_WEEK else "early"


def _read_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def parse_locations(raw) -> list[dict]:
    """GDELT location mentions ({name, country_fips, offset}); the pool stores them as a Python-style string."""
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return []
    return [{"name": loc.get("name", ""), "country_fips": loc.get("country_fips", ""), "offset": loc.get("offset")}
            for loc in raw if isinstance(loc, dict)]


def _one_per_group(groups: dict[str, dict], rng: random.Random) -> set[str]:
    """Pick one record ID at random from each near-duplicate group."""
    members = defaultdict(list)
    for record_id, row in groups.items():
        members[row["near_dup_group"]].append(record_id)
    return {rng.choice(sorted(ids)) for _, ids in sorted(members.items())}


def read_pool(pool_dir: Path, rng: random.Random) -> list[dict]:
    """Eligible articles from the pool: assigned to a country-season, one per near-duplicate group."""
    windows = json.loads((pool_dir / "season_windows.json").read_text(encoding="utf-8"))
    onsets = {w["season_id"]: date.fromisoformat(w["onset_date"]) for w in windows}
    seasons = {r["gkg_record_id"]: r for r in _read_jsonl(pool_dir / "season_assignments.jsonl") if r["sampling_season"]}
    groups = {r["gkg_record_id"]: r for r in _read_jsonl(pool_dir / "near_dup_groups.jsonl") if r["gkg_record_id"] in seasons}
    missing = len(seasons) - len(groups)
    if missing:
        raise ValueError(f"{missing} assigned articles have no near-duplicate group; rerun prepare_pool.py neardup")
    keep = _one_per_group(groups, rng)

    articles = []
    for rec in _read_jsonl(pool_dir / "pooled_articles.jsonl"):
        record_id = rec["gkg_record_id"]
        if record_id not in keep:
            continue
        season, group = seasons[record_id], groups[record_id]
        scan_date = date.fromisoformat(rec["datetime"][:10])
        articles.append({
            "record_id": record_id, "url": rec["url"], "scan_date": scan_date.isoformat(), "year": scan_date.year,
            "text": rec.get("article") or "", "locations": parse_locations(rec.get("locations")),
            "country": season["sampling_country"], "season": season["sampling_season"],
            "phase": phase_of(scan_date, onsets[season["sampling_season"]]),
            "near_dup_group": group["near_dup_group"], "group_size": group["group_size"],
        })
    return articles


def add_buckets(articles: list[dict]) -> list[dict]:
    """A copy of each article with its bucket and reason added."""
    bucketed = []
    for a in articles:
        bucket, reason = bucket_article(a["text"], a["year"])
        bucketed.append({**a, "bucket": bucket, "reason": reason})
    return bucketed


def quota_name(bucket: str) -> str:
    """The QUOTAS entry a bucket draws from (the three junk buckets share one)."""
    return "JUNK" if bucket in JUNK_BUCKETS else bucket


def draw(articles: list[dict], rng: random.Random) -> list[dict]:
    """Draw each bucket's quota, spreading evenly over country, season and phase."""
    pools = defaultdict(list)
    for a in articles:
        pools[quota_name(a["bucket"])].append(a)

    sample = []
    for name, quota in QUOTAS.items():
        # Group the bucket by (country, season, phase), shuffle each group, then take one from each group in turn.
        groups = defaultdict(list)
        for a in pools[name]:
            groups[(a["country"], a["season"], a["phase"])].append(a)
        order = [rng.sample(g, len(g)) for _, g in sorted(groups.items())]
        rng.shuffle(order)
        turns = (a for round_ in zip_longest(*order) for a in round_ if a is not None)
        sample.extend(a for a, _ in zip(turns, range(quota)))
    return sample


def bucket_sizes(articles: list[dict]) -> dict:
    """How many eligible articles each quota bucket held, overall and by country. The sample takes
    a fixed number per bucket, so these are needed to turn sample rates back into pool-wide rates."""
    per_country = defaultdict(Counter)
    for a in articles:
        per_country[quota_name(a["bucket"])][a["country"]] += 1
    return {
        "eligible_articles": len(articles),
        "quotas": QUOTAS,
        "per_bucket": {name: sum(per_country[name].values()) for name in QUOTAS},
        "per_bucket_country": {name: dict(sorted(per_country[name].items())) for name in QUOTAS},
    }


def save(out_dir: Path, articles: list[dict], sample: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("all_articles_buckets.csv", articles), ("sample_1200.csv", sample)):
        with open(out_dir / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    with open(out_dir / "sample_1200.jsonl", "w", encoding="utf-8") as f:   # includes the article text
        for a in sample:
            f.write(json.dumps({k: a[k] for k in COLUMNS + ["text", "locations"]}, ensure_ascii=False) + "\n")
    (out_dir / "bucket_sizes.json").write_text(json.dumps(bucket_sizes(articles), indent=2), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Bucket pooled flu articles and draw the labeling sample.")
    p.add_argument("--pool-dir", type=Path, required=True,
                   help="prepare_pool.py output folder (pooled_articles.jsonl, season_assignments.jsonl, "
                        "near_dup_groups.jsonl, season_windows.json)")
    p.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "output")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    rng = random.Random(args.seed)
    articles = add_buckets(read_pool(args.pool_dir, rng))
    sample = draw(articles, rng)
    save(args.out_dir, articles, sample)

    print(f"read {len(articles)} eligible articles (one per near-duplicate group)")
    print("buckets:", dict(Counter(a["bucket"] for a in articles).most_common()))
    print(f"sample: {len(sample)}")
    print("  by bucket :", dict(Counter(a["bucket"] for a in sample).most_common()))
    print("  by country:", dict(Counter(a["country"] for a in sample).most_common()))
    print("  by phase  :", dict(Counter(a["phase"] for a in sample).most_common()))
    print("  by season :", dict(sorted(Counter(a["season"] for a in sample).items())))
    print(f"saved to {args.out_dir}")


if __name__ == "__main__":
    main()
