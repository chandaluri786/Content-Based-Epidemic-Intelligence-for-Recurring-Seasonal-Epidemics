"""Wave 1 checkpoint-1 audit re-run: USA, AUS, IND -- the three countries
where content-richness + geo-crosscheck fixes can move real, measurable
numbers (Phase 1 native-term matching was dropped after evidence showed it
wouldn't help BRA/KEN; BRA/KEN are documented structural limitations, not
addressed by this run -- see dev/active/flu-pipeline/context.md).

Sequencing (Phase 4): fetch -> score content-richness (pipeline.gdelt.
content_richness, the fixed structural scorer) -> geo-crosscheck the
content-rich subset only (geo_matches_comparative, validated 2026-09-18
against the known India/Australia mismatch and a named-domain specificity
guard) -> final retrievable / content-rich / geo-agreeing % vs the
existing 60%/50% bars.

Usage:
    python -m investigation.wave1_audit_rerun
"""

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.gdelt.article_fetcher import fetch_article_text
from pipeline.gdelt.content_richness import score_content_richness
from investigation.geo_heuristic_recheck import GEO_KEYWORDS, geo_matches_comparative

REPO_ROOT = Path(__file__).resolve().parent.parent
MATCHED_DIR = REPO_ROOT / "data" / "gdelt_matched"
OUT_DIR = Path(__file__).resolve().parent

FETCH_CONCURRENCY = 16
RETRIEVABILITY_BAR_PCT = 60.0
CONTENT_RICH_BAR_PCT = 50.0

COHORT = list(GEO_KEYWORDS.keys())  # USA, AUS, BRA, IND, KEN, IDN

# USA sampled (58,458 total, matching prior audit methodology); AUS/IND full sets.
TARGETS: list[tuple[str, int | None]] = [
    ("USA", 800),
    ("AUS", None),
    ("IND", None),
]

# Prior baseline numbers (data/gdelt_matched, old RETRIEVABLE_MIN_TEXT_LEN-only
# retrievability + CHALLENGE_MARKERS-based content_marker_hits definition),
# for the before/after comparison in the final report.
OLD_BASELINE_PCT = {
    "USA": {"retrievable": 46.6, "content_rich": 42.75},
    "AUS": {"retrievable": 49.79, "content_rich": 45.05},
    "IND": {"retrievable": 61.55, "content_rich": 58.36},
}


def load_matched_urls(iso3: str, sample_n: int | None) -> list[str]:
    urls = []
    with (MATCHED_DIR / f"{iso3}.jsonl").open(encoding="utf-8") as f:
        for line in f:
            urls.append(json.loads(line)["url"])
    if sample_n is not None and sample_n < len(urls):
        random.seed(2024)  # same seed as the original USA sample, for comparability
        urls = random.sample(urls, sample_n)
    return urls


def fetch_and_score(url: str) -> dict:
    article = fetch_article_text(url)
    text = article.text or ""
    score = score_content_richness(text)
    return {
        "url": url,
        "retrievable": article.retrievable,
        "text_len": score.text_len,
        "is_content_rich": score.is_content_rich,
        "sentence_count": score.sentence_count,
        "type_token_ratio": score.type_token_ratio,
        "avg_chunk_words": score.avg_chunk_words,
        "content_marker_hits": score.content_marker_hits,
    }


def fetch_all(iso3: str, urls: list[str]) -> list[dict]:
    results = []
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        futures = {pool.submit(fetch_and_score, u): u for u in urls}
        for i, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if i % 500 == 0 or i == len(urls):
                print(f"    [{iso3}] {i}/{len(urls)} fetched+scored", flush=True)
    return results


def geo_check_rich_subset(iso3: str, rich_results: list[dict]) -> dict[str, bool]:
    """Re-fetch text for the content-rich subset only (already fetched once
    above, but article_fetcher doesn't cache -- re-fetching is simpler than
    threading raw text through and keeps this script self-contained; the
    subset is much smaller than the full matched set, matching the same
    optimization geo_heuristic_recheck.py already uses)."""
    urls = [r["url"] for r in rich_results]
    verdicts: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        futures = {pool.submit(fetch_article_text, u): u for u in urls}
        for i, fut in enumerate(as_completed(futures), 1):
            url = futures[fut]
            article = fut.result()
            if not article.text or len(article.text.strip()) == 0:
                verdicts[url] = True  # unknown -> don't exclude without text to check
            else:
                verdicts[url] = geo_matches_comparative(article.text, iso3, COHORT)
            if i % 300 == 0 or i == len(urls):
                print(f"    [{iso3}] geo-check {i}/{len(urls)}", flush=True)
    return verdicts


def summarize(iso3: str, results: list[dict], geo_verdicts: dict[str, bool]) -> dict:
    n = len(results)
    retrievable = sum(1 for r in results if r["retrievable"])
    rich = [r for r in results if r["is_content_rich"]]
    content_rich_before = len(rich)

    geo_excluded = sum(1 for r in rich if not geo_verdicts.get(r["url"], True))
    content_rich_after = content_rich_before - geo_excluded

    retrievable_pct = 100 * retrievable / n if n else 0.0
    rich_pct_before = 100 * content_rich_before / n if n else 0.0
    rich_pct_after = 100 * content_rich_after / n if n else 0.0

    old = OLD_BASELINE_PCT.get(iso3, {})

    return {
        "iso3": iso3,
        "n": n,
        "retrievable": retrievable,
        "retrievable_pct": round(retrievable_pct, 2),
        "old_retrievable_pct": old.get("retrievable"),
        "content_rich_before_geo": content_rich_before,
        "content_rich_pct_before_geo": round(rich_pct_before, 2),
        "old_content_rich_pct": old.get("content_rich"),
        "geo_mismatch_excluded": geo_excluded,
        "content_rich_after_geo": content_rich_after,
        "content_rich_pct_after_geo": round(rich_pct_after, 2),
        "retrievable_pass": retrievable_pct >= RETRIEVABILITY_BAR_PCT,
        "content_rich_pass_after_geo": rich_pct_after >= CONTENT_RICH_BAR_PCT,
    }


def main() -> None:
    summaries = []
    for iso3, sample_n in TARGETS:
        label = "full set" if sample_n is None else f"sample n={sample_n}"
        print(f"=== {iso3} ({label}) ===")
        urls = load_matched_urls(iso3, sample_n)
        print(f"  {len(urls)} URLs to fetch")
        results = fetch_all(iso3, urls)

        rich_results = [r for r in results if r["is_content_rich"]]
        print(f"  {len(rich_results)} content-rich (structural score); geo-checking this subset...")
        geo_verdicts = geo_check_rich_subset(iso3, rich_results)

        summary = summarize(iso3, results, geo_verdicts)
        summaries.append(summary)

        with (OUT_DIR / f"wave1_{iso3.lower()}_results.json").open("w", encoding="utf-8") as f:
            json.dump({"summary": summary, "articles": results}, f, indent=2, ensure_ascii=False)

    print("\n\n=== WAVE 1 CHECKPOINT AUDIT: BEFORE (old) vs AFTER (new fixes) ===")
    header = (
        f"{'':4} {'N':>7} {'Retr%old':>9} {'Retr%new':>9} "
        f"{'Rich%old':>9} {'Rich%new(pre-geo)':>18} {'GeoExcl':>8} "
        f"{'Rich%new(post-geo)':>19} {'PassRetr':>9} {'PassRich':>9}"
    )
    print(header)
    for s in summaries:
        print(
            f"{s['iso3']:4} {s['n']:7} "
            f"{s['old_retrievable_pct']:8.1f}% {s['retrievable_pct']:8.1f}% "
            f"{s['old_content_rich_pct']:8.1f}% {s['content_rich_pct_before_geo']:17.1f}% "
            f"{s['geo_mismatch_excluded']:8} {s['content_rich_pct_after_geo']:18.1f}% "
            f"{str(s['retrievable_pass']):>9} {str(s['content_rich_pass_after_geo']):>9}"
        )

    out_path = OUT_DIR / "wave1_audit_summary.json"
    out_path.write_text(json.dumps(summaries, indent=2))
    print(f"\nSummary written to {out_path}")


if __name__ == "__main__":
    main()
