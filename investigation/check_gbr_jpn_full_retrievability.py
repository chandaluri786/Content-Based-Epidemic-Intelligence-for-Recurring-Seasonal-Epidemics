"""Real-data (not sampled) retrievability/content-depth check for GBR and
JPN, mirroring check_bra_idn_full_retrievability.py and
check_ken_full_retrievability.py -- run before any decision to re-include
either country in the content-based comparison cohort (see context.md,
"New consequence that needs a team decision").

GBR and JPN were dropped from the active GDELT cohort in an earlier team
decision (onset-detection-method uniformity, not content quality -- see
context.md), but their full-window Step 2 matches (3,707 GBR + 3,000 JPN,
ingested via manifest_batch2.jsonl before the cohort change) are still on
disk. This script checks whether their content is actually usable, and
whether either has the same kind of single-story syndication contamination
found in Kenya (one wire story geo-tagged across 100+ unrelated URLs,
inflating the raw match count without adding real country-specific signal).

Uses the same production `fetch_article_text` (pipeline/gdelt/article_fetcher.py)
and the same content-marker list/threshold as every check_gdelt_flu_content*.py
script in this project, for a same-method, full-N comparison against
BRA/IDN/KEN's numbers.

Usage:
    python -m investigation.check_gbr_jpn_full_retrievability
"""

import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.gdelt.article_fetcher import fetch_article_text

REPO_ROOT = Path(__file__).resolve().parents[1]
MATCHED_DIR = REPO_ROOT / "data" / "gdelt_matched"
OUT_PATH = Path(__file__).resolve().parent / "gbr_jpn_full_retrievability_results.json"

TARGET_COUNTRIES = ["GBR", "JPN"]
FETCH_CONCURRENCY = 16

# Any single slug shared by at least this many distinct matched URLs is
# reported as probable syndication contamination (the KEN wire story hit
# 100+; this is set low enough to also flag smaller but still-notable
# pileups worth a human look).
SYNDICATION_MIN_COUNT = 10

CONTENT_MARKERS = [
    "case", "cases", "hospitaliz", "death", "outbreak", "epidemic", "strain",
    "h1n1", "h3n2", "influenza b", "surge", "vaccine", "severe",
    "world health organization",
]

SLUG_RE = re.compile(r"/([a-z0-9-]{20,})(?:\.\w+)?(?:[/?].*)?$")


def content_score(text: str) -> int:
    low = text.lower()
    return sum(1 for m in CONTENT_MARKERS if m in low)


def slug(url: str) -> str:
    m = SLUG_RE.search(url)
    return m.group(1)[:80] if m else url


def load_matched_urls(iso3: str) -> list[str]:
    urls = []
    with (MATCHED_DIR / f"{iso3}.jsonl").open(encoding="utf-8") as f:
        for line in f:
            urls.append(json.loads(line)["url"])
    return urls


def find_syndication_clusters(urls: list[str]) -> list[tuple[str, int]]:
    counts = Counter(slug(u) for u in urls)
    return sorted(
        ((s, n) for s, n in counts.items() if n >= SYNDICATION_MIN_COUNT),
        key=lambda kv: -kv[1],
    )


def check_country(iso3: str) -> dict:
    urls = load_matched_urls(iso3)
    clusters = find_syndication_clusters(urls)
    cluster_slugs = {s for s, _ in clusters}

    results = []
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        futures = {pool.submit(fetch_article_text, url): url for url in urls}
        for i, fut in enumerate(as_completed(futures), 1):
            url = futures[fut]
            article = fut.result()
            depth = content_score(article.text) if article.text else 0
            results.append({
                "url": url,
                "retrievable": article.retrievable,
                "content_marker_hits": depth,
                "syndication_cluster": slug(url) if slug(url) in cluster_slugs else None,
            })
            if i % 100 == 0 or i == len(urls):
                print(f"  [{iso3}] {i}/{len(urls)} fetched", flush=True)

    return {"iso3": iso3, "n_matched": len(urls), "clusters": clusters, "articles": results}


def main() -> None:
    all_results = {}
    for iso3 in TARGET_COUNTRIES:
        print(f"=== {iso3} ===")
        all_results[iso3] = check_country(iso3)

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print("\n=== SUMMARY: full matched-set retrievability/content-depth, GBR/JPN ===")
    grand_n, grand_retr, grand_rich, grand_stories = 0, 0, 0, 0
    for iso3, r in all_results.items():
        arts = r["articles"]
        n = len(arts)
        retr = sum(1 for a in arts if a["retrievable"])
        rich = [a for a in arts if a["content_marker_hits"] >= 1]
        contaminated = sum(1 for a in arts if a["syndication_cluster"])
        contaminated_rich = sum(1 for a in rich if a["syndication_cluster"])

        # Distinct underlying stories among content-rich hits: group by slug
        # (any shared slug, not just >=SYNDICATION_MIN_COUNT clusters) so a
        # story syndicated even 2-3x doesn't inflate the story count.
        rich_slug_counts = Counter(slug(a["url"]) for a in rich)
        distinct_rich_stories = len(rich_slug_counts)
        top_rich_stories = rich_slug_counts.most_common(5)

        grand_n += n
        grand_retr += retr
        grand_rich += len(rich)
        grand_stories += distinct_rich_stories
        print(f"\n{iso3}: {n} matched, {retr}/{n} retrievable ({100*retr/n:.1f}%, threshold >=60%), "
              f"{len(rich)}/{n} content-rich ({100*len(rich)/n:.1f}%, threshold >=50%)")
        print(f"  Content-rich hits represent {distinct_rich_stories} distinct underlying stories "
              f"(vs {len(rich)} raw content-rich matches -- a ratio near 1.0 means genuine breadth, "
              f"well below 1.0 means a few stories syndicated widely).")
        if top_rich_stories:
            print("  Largest content-rich story clusters:")
            for s, cnt in top_rich_stories:
                print(f"    {cnt:4d}x  {s}")
        if r["clusters"]:
            print(f"  All-matches syndication clusters (>= {SYNDICATION_MIN_COUNT} URLs sharing one slug):")
            for s, cnt in r["clusters"]:
                print(f"    {cnt:4d}x  {s}")
            print(f"  Total in clusters: {contaminated}/{n} ({100*contaminated/n:.1f}%); "
                  f"of nominal content-rich, {contaminated_rich}/{len(rich)} are clustered/syndicated.")
        else:
            print(f"  No syndication clusters >= {SYNDICATION_MIN_COUNT} found among all matches.")

    print(f"\nCombined: {grand_n} matched, {grand_retr}/{grand_n} retrievable "
          f"({100*grand_retr/grand_n:.1f}%), {grand_rich}/{grand_n} content-rich "
          f"({100*grand_rich/grand_n:.1f}%), representing {grand_stories} distinct stories combined "
          f"(note: story identity isn't deduplicated across countries, so this is a simple sum).")
    print(f"Results written to {OUT_PATH}")


if __name__ == "__main__":
    main()
