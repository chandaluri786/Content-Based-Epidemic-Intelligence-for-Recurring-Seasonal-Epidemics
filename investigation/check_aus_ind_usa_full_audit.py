"""Full four-part audit for AUS, IND (full matched-URL set) and USA (a large
random sample), matching the rigor already applied to BRA/IDN/KEN/GBR/JPN:

1. Retrievability/content-depth (fixed header pipeline) vs the >=60%/>=50% bars.
2. Boilerplate/challenge-page false positives among nominal "retrievable"
   hits -- the issue found in GBR/KEN, where a 200-char length threshold
   counted cookie notices, JS-loading shells, or stub pages as retrievable.
3. Syndication concentration -- how many of the content-rich hits are
   distinct underlying stories vs a few duplicated articles (the Kenya
   wire-story issue), via the same slug-based grouping used elsewhere.
4. Country-mislabeling spot-check -- the issue found in the original spike
   (a UK content-farm site mistagged as Brazil): for a random subsample of
   each country's matched articles, check whether the country's own name,
   demonym, or major-city names actually appear in the fetched text, rather
   than just trusting GDELT's location tag.

Uses the same production `fetch_article_text` (pipeline/gdelt/article_fetcher.py,
now with the fixed default User-Agent) and the same content-marker list used
throughout this project's checks.

Usage:
    python -m investigation.check_aus_ind_usa_full_audit
"""

import json
import random
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.gdelt.article_fetcher import fetch_article_text

REPO_ROOT = Path(__file__).resolve().parents[1]
MATCHED_DIR = REPO_ROOT / "data" / "gdelt_matched"
OUT_DIR = Path(__file__).resolve().parent

FETCH_CONCURRENCY = 16
RELEVANCE_SAMPLE_SIZE = 40
RELEVANCE_SEED = 2025

# (iso3, full-set or sampled-N, random-sample-N-or-None)
TARGETS = [
    ("AUS", None),
    ("IND", None),
    ("USA", 800),
]

CONTENT_MARKERS = [
    "case", "cases", "hospitaliz", "death", "outbreak", "epidemic", "strain",
    "h1n1", "h3n2", "influenza b", "surge", "vaccine", "severe",
    "world health organization",
]

CHALLENGE_MARKERS = [
    "captcha", "attention required", "just a moment", "cloudflare",
    "access denied", "are you a human", "enable javascript and cookies",
    "request unsuccessful", "challenge validation", "subscribe to continue",
    "sign in to read", "create a free account",
]

# Country name / demonym / major-city keywords for the relevance spot-check.
# Not exhaustive -- a reasonable, defensible heuristic, same spirit as the
# check that caught bobfm.co.uk never mentioning "Brazil" at all.
RELEVANCE_KEYWORDS = {
    "AUS": [
        "australia", "australian", "sydney", "melbourne", "canberra",
        "brisbane", "perth", "adelaide", "queensland", "new south wales",
        "victoria state", "nsw",
    ],
    "IND": [
        "india", "indian", "delhi", "mumbai", "bengaluru", "bangalore",
        "chennai", "kolkata", "hyderabad", "kerala", "punjab",
        "maharashtra", "uttar pradesh", "modi",
    ],
    "USA": [
        "united states", "u.s.", "usa", "america", "american", "cdc",
        "washington", "new york", "california", "texas", "florida",
    ],
}

SLUG_RE = re.compile(r"/([a-z0-9-]{20,})(?:\.\w+)?(?:[/?].*)?$")


def content_score(text: str) -> int:
    low = text.lower()
    return sum(1 for m in CONTENT_MARKERS if m in low)


def has_challenge_marker(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in CHALLENGE_MARKERS)


def slug(url: str) -> str:
    m = SLUG_RE.search(url)
    return m.group(1)[:80] if m else url


def load_matched_urls(iso3: str, sample_n: int | None) -> list[str]:
    urls = []
    with (MATCHED_DIR / f"{iso3}.jsonl").open(encoding="utf-8") as f:
        for line in f:
            urls.append(json.loads(line)["url"])
    if sample_n is not None and sample_n < len(urls):
        random.seed(2024)
        urls = random.sample(urls, sample_n)
    return urls


def fetch_all(urls: list[str]) -> list[dict]:
    results = []
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        futures = {pool.submit(fetch_article_text, u): u for u in urls}
        for i, fut in enumerate(as_completed(futures), 1):
            url = futures[fut]
            article = fut.result()
            results.append({
                "url": url,
                "retrievable": article.retrievable,
                "content_marker_hits": content_score(article.text) if article.text else 0,
                "challenge": has_challenge_marker(article.text) if article.retrievable else False,
                "text_len": len(article.text.strip()) if article.text else 0,
            })
            if i % 200 == 0 or i == len(urls):
                print(f"    {i}/{len(urls)} fetched", flush=True)
    return results


def relevance_check(iso3: str, urls: list[str]) -> dict:
    """Fetch a small random subsample and check whether country-relevance
    keywords appear anywhere in the retrieved text."""
    random.seed(RELEVANCE_SEED)
    sample = random.sample(urls, min(RELEVANCE_SAMPLE_SIZE, len(urls)))
    keywords = RELEVANCE_KEYWORDS[iso3]

    checked, relevant, irrelevant_examples = 0, 0, []
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        futures = {pool.submit(fetch_article_text, u): u for u in sample}
        for fut in as_completed(futures):
            url = futures[fut]
            article = fut.result()
            if not article.text or len(article.text.strip()) == 0:
                continue  # can't assess relevance with no text at all
            checked += 1
            low = article.text.lower()
            if any(k in low for k in keywords):
                relevant += 1
            else:
                irrelevant_examples.append(url)

    return {
        "checked": checked,
        "relevant": relevant,
        "irrelevant_examples": irrelevant_examples[:10],
    }


def summarize(iso3: str, results: list[dict], relevance: dict) -> dict:
    n = len(results)
    retr = [r for r in results if r["retrievable"]]
    rich = [r for r in results if r["content_marker_hits"] >= 1]
    challenge_flagged = [r for r in retr if r["challenge"]]
    rich_slugs = Counter(slug(r["url"]) for r in rich)

    return {
        "iso3": iso3,
        "n": n,
        "retrievable": len(retr),
        "retrievable_pct": 100 * len(retr) / n if n else 0,
        "content_rich": len(rich),
        "content_rich_pct": 100 * len(rich) / n if n else 0,
        "challenge_flagged_of_retrievable": len(challenge_flagged),
        "distinct_stories_of_rich": len(rich_slugs),
        "top_story_clusters": rich_slugs.most_common(5),
        "relevance_checked": relevance["checked"],
        "relevance_relevant": relevance["relevant"],
        "relevance_irrelevant_examples": relevance["irrelevant_examples"],
    }


def main() -> None:
    all_summaries = []
    for iso3, sample_n in TARGETS:
        print(f"=== {iso3} {'(full set)' if sample_n is None else f'(sample n={sample_n})'} ===")
        urls = load_matched_urls(iso3, sample_n)
        print(f"  {len(urls)} URLs to fetch for retrievability/content-depth")
        results = fetch_all(urls)

        print(f"  Running country-relevance spot-check ({RELEVANCE_SAMPLE_SIZE} URLs)...")
        all_urls_for_relevance = load_matched_urls(iso3, None)
        relevance = relevance_check(iso3, all_urls_for_relevance)

        summary = summarize(iso3, results, relevance)
        all_summaries.append(summary)

        with (OUT_DIR / f"{iso3.lower()}_full_audit_results.json").open("w", encoding="utf-8") as f:
            json.dump({"summary": summary, "articles": results, "relevance": relevance}, f, indent=2, ensure_ascii=False)

    print("\n\n=== CONSOLIDATED AUDIT SUMMARY ===")
    for s in all_summaries:
        print(f"\n{s['iso3']}: n={s['n']}")
        print(f"  Retrievable: {s['retrievable']}/{s['n']} ({s['retrievable_pct']:.1f}%, threshold >=60%)")
        print(f"  Content-rich: {s['content_rich']}/{s['n']} ({s['content_rich_pct']:.1f}%, threshold >=50%)")
        print(f"  Challenge/boilerplate flagged among retrievable: {s['challenge_flagged_of_retrievable']}/{s['retrievable']}")
        print(f"  Distinct stories among content-rich: {s['distinct_stories_of_rich']}/{s['content_rich']}")
        if s["top_story_clusters"]:
            print("  Largest content-rich clusters:")
            for slug_name, cnt in s["top_story_clusters"]:
                if cnt > 1:
                    print(f"    {cnt}x {slug_name}")
        print(f"  Country-relevance spot-check: {s['relevance_relevant']}/{s['relevance_checked']} mention the country/demonym/major city")
        if s["relevance_irrelevant_examples"]:
            print("  Examples with NO country-relevance keyword found:")
            for u in s["relevance_irrelevant_examples"]:
                print(f"    {u}")

    print(f"\nResults written to {OUT_DIR}/{{aus,ind,usa}}_full_audit_results.json")


if __name__ == "__main__":
    main()
