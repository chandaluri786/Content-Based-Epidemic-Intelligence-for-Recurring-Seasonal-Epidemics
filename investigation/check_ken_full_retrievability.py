"""Real-data (not sampled) retrievability/content-depth check for Kenya,
mirroring check_bra_idn_full_retrievability.py -- run after the finding that
Kenya's 163 matched articles (data/gdelt_matched/KEN.jsonl, all 8
defined-onset seasons 2015-2024) had been left in the content-comparison
track by default, without being checked against the project's own
>=60%/>=50% retrievability/content-depth rule the way BRA/IDN were.

Uses the same production `fetch_article_text` (pipeline/gdelt/article_fetcher.py)
and the same content-marker list/threshold as every check_gdelt_flu_content*.py
script in this project, for a same-method, full-N comparison against BRA/IDN's
numbers.

Usage:
    python -m investigation.check_ken_full_retrievability
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.gdelt.article_fetcher import fetch_article_text

REPO_ROOT = Path(__file__).resolve().parents[1]
MATCHED_PATH = REPO_ROOT / "data" / "gdelt_matched" / "KEN.jsonl"
OUT_PATH = Path(__file__).resolve().parent / "ken_full_retrievability_results.json"

FETCH_CONCURRENCY = 16

CONTENT_MARKERS = [
    "case", "cases", "hospitaliz", "death", "outbreak", "epidemic", "strain",
    "h1n1", "h3n2", "influenza b", "surge", "vaccine", "severe",
    "world health organization",
]

# The single wire story found to account for 113/163 of Kenya's total matched
# articles across the full decade (see context.md) -- included here so the
# contamination breakdown is reproducible from this script, not just a
# one-off analysis.
WIRE_STORY_URL_FRAGMENTS = (
    "more-hospitals-are-requiring-masks",
    "hospitals-requiring-masks-as-flu",
)


def content_score(text: str) -> int:
    low = text.lower()
    return sum(1 for m in CONTENT_MARKERS if m in low)


def is_wire_story(url: str) -> bool:
    return any(frag in url for frag in WIRE_STORY_URL_FRAGMENTS)


def load_matched_urls() -> list[str]:
    urls = []
    with MATCHED_PATH.open(encoding="utf-8") as f:
        for line in f:
            urls.append(json.loads(line)["url"])
    return urls


def main() -> None:
    urls = load_matched_urls()
    print(f"=== KEN: {len(urls)} matched articles ===")

    results = []
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        futures = {pool.submit(fetch_article_text, url): url for url in urls}
        for i, fut in enumerate(as_completed(futures), 1):
            url = futures[fut]
            article = fut.result()
            depth = content_score(article.text) if article.text else 0
            results.append({"url": url, "retrievable": article.retrievable, "content_marker_hits": depth})
            if i % 30 == 0 or i == len(urls):
                print(f"  {i}/{len(urls)} fetched", flush=True)

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    n = len(results)
    retrievable = sum(1 for r in results if r["retrievable"])
    rich = [r for r in results if r["content_marker_hits"] >= 1]
    wire_rich = [r for r in rich if is_wire_story(r["url"])]
    genuine_rich = [r for r in rich if not is_wire_story(r["url"])]
    wire_total = sum(1 for r in results if is_wire_story(r["url"]))

    print("\n=== SUMMARY: full matched-set retrievability/content-depth, KEN ===")
    print(f"KEN: {n} matched, {retrievable}/{n} retrievable ({100 * retrievable / n:.1f}%, threshold >=60%), "
          f"{len(rich)}/{n} content-rich ({100 * len(rich) / n:.1f}%, threshold >=50%)")
    print(f"\nWire-story contamination: {wire_total}/{n} ({100 * wire_total / n:.1f}%) of all matched articles "
          f"are the same syndicated AP story, unrelated to Kenya.")
    print(f"Of {len(rich)} nominally content-rich matches: {len(wire_rich)} are the wire story, "
          f"{len(genuine_rich)} are genuine (non-wire-story) content.")
    print(f"\nResults written to {OUT_PATH}")


if __name__ == "__main__":
    main()
