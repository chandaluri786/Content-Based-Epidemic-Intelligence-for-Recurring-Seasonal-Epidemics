"""Phase 3b: independent validation of the new content-richness scorer
(pipeline/gdelt/content_richness.py) against real, already-identified
failure cases in this repo's own audit data -- not synthetic examples.

Two checks:
1. Regression test: the 148 AUS articles the OLD CHALLENGE_MARKERS keyword
   blocklist flagged as "challenge" pages, which a spot-check showed are
   actually genuine 6,000+ character articles (false positives). Re-fetch
   their real text and confirm the new scorer does NOT penalize them.
2. Human-review table: the near-threshold short "retrievable" USA examples
   (245/296 chars) that are genuinely ambiguous on inspection -- report the
   new scorer's verdict for a person to sign off on, not a hard assertion.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.gdelt.article_fetcher import fetch_article_text
from pipeline.gdelt.content_richness import score_content_richness

REPO_ROOT = Path(__file__).resolve().parent.parent
FETCH_CONCURRENCY = 16

NEAR_THRESHOLD_USA_URLS = [
    "http://iusbpreface.com/2016/01/21/bird-flu-hits-major-us-turkey-producer-in-indiana-97459/",
    "https://www.zerohedge.com/medical/cdc-admits-no-data-support-advice-take-mpox-influenza-and-covid-shots-together",
]


def load_aus_challenge_urls() -> list[str]:
    with (REPO_ROOT / "investigation" / "aus_full_audit_results.json").open() as f:
        data = json.load(f)
    return [a["url"] for a in data["articles"] if a.get("challenge")]


def fetch_and_score(url: str) -> dict:
    article = fetch_article_text(url)
    score = score_content_richness(article.text) if article.text else None
    return {
        "url": url,
        "old_retrievable": article.retrievable,
        "fetched_text_len": len(article.text.strip()) if article.text else 0,
        "new_is_content_rich": score.is_content_rich if score else False,
        "new_text_len": score.text_len if score else 0,
        "new_sentence_count": score.sentence_count if score else 0,
        "new_ttr": score.type_token_ratio if score else 0.0,
        "new_avg_chunk_words": score.avg_chunk_words if score else 0.0,
        "new_marker_hits": score.content_marker_hits if score else 0,
    }


def main() -> None:
    print("=== Check 1: 148 AUS CHALLENGE_MARKERS false positives (regression test) ===")
    aus_urls = load_aus_challenge_urls()
    print(f"Re-fetching {len(aus_urls)} URLs at {FETCH_CONCURRENCY}x concurrency...")

    aus_results = []
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        futures = {pool.submit(fetch_and_score, u): u for u in aus_urls}
        for i, fut in enumerate(as_completed(futures), 1):
            aus_results.append(fut.result())
            if i % 50 == 0 or i == len(aus_urls):
                print(f"  {i}/{len(aus_urls)} fetched")

    # Some URLs may no longer be live years later -- only judge the ones we
    # could actually re-fetch real text for for the regression assertion.
    still_retrievable = [r for r in aus_results if r["old_retrievable"] and r["fetched_text_len"] > 0]
    correctly_not_penalized = [r for r in still_retrievable if r["new_is_content_rich"]]
    still_flagged = [r for r in still_retrievable if not r["new_is_content_rich"]]
    dead_links = [r for r in aus_results if r["fetched_text_len"] == 0]

    print(f"\nOf {len(aus_results)} originally-flagged URLs:")
    print(f"  Still live/retrievable now: {len(still_retrievable)}")
    print(f"  Dead/unfetchable now (excluded from verdict): {len(dead_links)}")
    print(
        f"  Correctly NOT penalized by new scorer: {len(correctly_not_penalized)}/{len(still_retrievable)}"
    )
    print(f"  STILL flagged as not-content-rich by new scorer: {len(still_flagged)}/{len(still_retrievable)}")
    if still_flagged:
        print("  Examples still flagged (needs review):")
        for r in still_flagged[:10]:
            print(f"    {r['url']}  text_len={r['new_text_len']} sentences={r['new_sentence_count']}"
                  f" ttr={r['new_ttr']} avg_chunk={r['new_avg_chunk_words']} markers={r['new_marker_hits']}")

    print("\n=== Check 2: near-threshold short USA examples (human review, not asserted) ===")
    for url in NEAR_THRESHOLD_USA_URLS:
        r = fetch_and_score(url)
        print(f"\n  {url}")
        print(f"    fetched_text_len={r['fetched_text_len']}  new_is_content_rich={r['new_is_content_rich']}")
        print(f"    sentences={r['new_sentence_count']} ttr={r['new_ttr']} avg_chunk={r['new_avg_chunk_words']}"
              f" markers={r['new_marker_hits']}")

    out_path = REPO_ROOT / "investigation" / "validate_content_richness_fix_results.json"
    out_path.write_text(json.dumps({
        "aus_challenge_regression": {
            "total_originally_flagged": len(aus_results),
            "still_retrievable": len(still_retrievable),
            "dead_links_excluded": len(dead_links),
            "correctly_not_penalized": len(correctly_not_penalized),
            "still_flagged": len(still_flagged),
            "details": aus_results,
        },
        "near_threshold_usa_review": [fetch_and_score(u) for u in NEAR_THRESHOLD_USA_URLS],
    }, indent=2))
    print(f"\nWrote {out_path}")

    if still_flagged:
        print(
            f"\nRESULT: {len(still_flagged)}/{len(still_retrievable)} known false positives NOT fixed "
            "-- review before treating thresholds as final."
        )
    else:
        print(f"\nRESULT: all {len(still_retrievable)} known false positives correctly NOT penalized.")


if __name__ == "__main__":
    main()
