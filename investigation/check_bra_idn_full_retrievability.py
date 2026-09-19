"""Real-data (not 5-day-sample) retrievability/content-depth check for
Brazil and Indonesia, to confirm or overturn the earlier 5-day extended
sample's 33% figure (investigation/check_gdelt_flu_content_extended.py,
which fetched only up to 10 URLs/day x 5 days x 2 countries = up to 100
articles total).

This script instead fetches *every* URL already matched during the Step 2
full-window volume-check ingestion (593 BRA + 216 IDN articles across all
their defined-onset seasons, data/gdelt_matched/{BRA,IDN}.jsonl), using the
same production `fetch_article_text` (pipeline/gdelt/article_fetcher.py,
retrievable = len(text.strip()) > RETRIEVABLE_MIN_TEXT_LEN=200, comparable
to the original feasibility spike's 88% figure) and the same content-marker
list/threshold (>=1 marker) used by every prior check_gdelt_flu_content*.py
script in this project, for a same-method, larger-N confirmation.

Usage:
    python -m investigation.check_bra_idn_full_retrievability
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.gdelt.article_fetcher import fetch_article_text

REPO_ROOT = Path(__file__).resolve().parents[1]
MATCHED_DIR = REPO_ROOT / "data" / "gdelt_matched"
OUT_PATH = Path(__file__).resolve().parent / "bra_idn_full_retrievability_results.json"

TARGET_COUNTRIES = ["BRA", "IDN"]
FETCH_CONCURRENCY = 16

CONTENT_MARKERS = [
    "case", "cases", "hospitaliz", "death", "outbreak", "epidemic", "strain",
    "h1n1", "h3n2", "influenza b", "surge", "vaccine", "severe",
    "world health organization",
]


def content_score(text: str) -> int:
    low = text.lower()
    return sum(1 for m in CONTENT_MARKERS if m in low)


def load_matched_urls(iso3: str) -> list[str]:
    path = MATCHED_DIR / f"{iso3}.jsonl"
    urls = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            urls.append(json.loads(line)["url"])
    return urls


def check_country(iso3: str) -> dict:
    urls = load_matched_urls(iso3)
    results = []
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        futures = {pool.submit(fetch_article_text, url): url for url in urls}
        for i, fut in enumerate(as_completed(futures), 1):
            url = futures[fut]
            article = fut.result()
            depth = content_score(article.text) if article.text else 0
            results.append({"url": url, "retrievable": article.retrievable, "content_marker_hits": depth})
            if i % 50 == 0 or i == len(urls):
                print(f"  [{iso3}] {i}/{len(urls)} fetched", flush=True)
    return {"iso3": iso3, "n_matched": len(urls), "articles": results}


def main() -> None:
    all_results = {}
    for iso3 in TARGET_COUNTRIES:
        print(f"=== {iso3} ===")
        all_results[iso3] = check_country(iso3)

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print("\n=== SUMMARY: full matched-set retrievability/content-depth, BRA/IDN ===")
    grand_sampled, grand_retrievable, grand_rich = 0, 0, 0
    for iso3, r in all_results.items():
        arts = r["articles"]
        sampled = len(arts)
        retrievable = sum(1 for a in arts if a["retrievable"])
        rich = sum(1 for a in arts if a["content_marker_hits"] >= 1)
        grand_sampled += sampled
        grand_retrievable += retrievable
        grand_rich += rich
        if sampled:
            print(f"{iso3}: {sampled} matched, {retrievable}/{sampled} retrievable "
                  f"({100 * retrievable / sampled:.1f}%), {rich}/{sampled} content-rich "
                  f"({100 * rich / sampled:.1f}%)")
        else:
            print(f"{iso3}: 0 matched articles")

    print(f"\nCombined: {grand_sampled} matched", end="")
    if grand_sampled:
        print(
            f", {grand_retrievable}/{grand_sampled} retrievable "
            f"({100 * grand_retrievable / grand_sampled:.1f}%, threshold >=60%)"
            f", {grand_rich}/{grand_sampled} content-rich "
            f"({100 * grand_rich / grand_sampled:.1f}%, threshold >=50%)"
        )
    print(f"Results written to {OUT_PATH}")


if __name__ == "__main__":
    main()
