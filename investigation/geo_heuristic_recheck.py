"""Audit-scale proxy for the geotagging cross-check
(pipeline.extraction.geo_crosscheck), re-running the full 6-country
retrievability/content-depth audit with likely-mistagged content excluded.

This is explicitly an APPROXIMATION, not the production mechanism: the real
cross-check (pipeline.extraction.geo_crosscheck.classify_geo_match) compares
GDELT's tag against the LLM extraction step's own `primary_country` judgment
(see pipeline/extraction/schema.py, prompt.py). Running that LLM check across
every content-rich article in all 6 countries -- thousands of calls -- is
blocked by the same Groq TPD cap documented in
dev/active/flu-pipeline/context.md (~2.3 months for a full 6-country run).
This script instead reuses the same keyword/demonym-presence heuristic that
check_aus_ind_usa_full_audit.py's RELEVANCE_KEYWORDS/relevance_check already
used (on a 40-URL spot-check sample) to catch India's Australian bird-flu
cluster, extended to every country and applied to every content-rich article,
not just a sample.

To avoid re-fetching everything from scratch, this reuses the
retrievable/content_marker_hits numbers already computed and persisted by the
last full audit (usa/aus/ind_full_audit_results.json,
bra_idn_full_retrievability_results.json, ken_full_retrievability_results.json)
-- those numbers are the "before" column here, unchanged -- and only
re-fetches the (much smaller) content-rich subset of each country to score
the new geo-keyword check, since a non-content-rich article was never in the
numerator either way.

Usage:
    python -m investigation.geo_heuristic_recheck
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.gdelt.article_fetcher import fetch_article_text

REPO_ROOT = Path(__file__).resolve().parents[1]
IN_DIR = Path(__file__).resolve().parent
OUT_PATH = IN_DIR / "geo_heuristic_recheck_results.json"

FETCH_CONCURRENCY = 24
RETRIEVABILITY_BAR_PCT = 60.0
CONTENT_RICH_BAR_PCT = 50.0

# Country name / demonym / major-city / capital keywords -- same spirit as
# check_aus_ind_usa_full_audit.py's RELEVANCE_KEYWORDS, extended to all 6
# active-cohort countries. Not exhaustive; a defensible heuristic proxy for
# "does this article's own text ever mention the country it's filed under."
GEO_KEYWORDS: dict[str, list[str]] = {
    "USA": [
        "united states", "u.s.", "usa", "america", "american", "cdc",
        "washington", "new york", "california", "texas", "florida",
    ],
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
    "BRA": [
        "brazil", "brazilian", "brasil", "sao paulo", "rio de janeiro",
        "brasilia", "belo horizonte", "salvador", "fortaleza", "bovespa",
    ],
    "IDN": [
        "indonesia", "indonesian", "jakarta", "surabaya", "bandung",
        "medan", "bali", "jokowi", "widodo",
    ],
    "KEN": [
        "kenya", "kenyan", "nairobi", "mombasa", "kisumu", "nakuru",
        "kenyatta", "ministry of health kenya",
    ],
}

# (iso3, source json path, how to pull its flat article list)
SOURCES: dict[str, tuple[Path, str]] = {
    "USA": (IN_DIR / "usa_full_audit_results.json", "nested_summary"),
    "AUS": (IN_DIR / "aus_full_audit_results.json", "nested_summary"),
    "IND": (IN_DIR / "ind_full_audit_results.json", "nested_summary"),
    "BRA": (IN_DIR / "bra_idn_full_retrievability_results.json", "by_country_key"),
    "IDN": (IN_DIR / "bra_idn_full_retrievability_results.json", "by_country_key"),
    "KEN": (IN_DIR / "ken_full_retrievability_results.json", "flat_list"),
}


def load_cached_articles(iso3: str) -> list[dict]:
    path, shape = SOURCES[iso3]
    data = json.loads(path.read_text(encoding="utf-8"))
    if shape == "nested_summary":
        return data["articles"]
    if shape == "by_country_key":
        return data[iso3]["articles"]
    if shape == "flat_list":
        return data
    raise ValueError(f"unknown shape {shape}")


def geo_mentions_country(text: str, iso3: str) -> bool:
    low = text.lower()
    return any(k in low for k in GEO_KEYWORDS[iso3])


def geo_matches_comparative(text: str, tagged_country: str, cohort: list[str]) -> bool:
    """Stricter replacement for geo_mentions_country: the tagged country's
    keyword count must strictly exceed every OTHER cohort country's keyword
    count in this text, not just be present at all.

    geo_mentions_country was found (2026-09-18 validation, see
    dev/active/flu-pipeline/context.md) to incorrectly pass the known India/
    Australia bird-flu mistag -- the article mentions India once ("the child
    contracted the severe infection in India") inside a story that mentions
    Australia 17 times; a bare presence check can't tell "mentioned once in
    passing" from "what the article is actually about." Comparing counts
    across the whole cohort fixes that specific failure mode without needing
    the real LLM-based primary_country judgment (pipeline.extraction.
    geo_crosscheck), which isn't affordable at audit scale."""
    low = text.lower()
    counts = {c: sum(low.count(k) for k in GEO_KEYWORDS[c]) for c in cohort}
    tagged_count = counts[tagged_country]
    return all(tagged_count > counts[c] for c in cohort if c != tagged_country)


def refetch_geo_check(iso3: str, urls: list[str]) -> dict[str, bool | None]:
    """Fetch each URL fresh and test for the country's own keywords in the
    text. None means the refetch itself failed/came back empty -- treated as
    "unknown", not excluded, since we can't confidently flag a mismatch
    without text to check."""
    verdicts: dict[str, bool | None] = {}
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        futures = {pool.submit(fetch_article_text, u): u for u in urls}
        for i, fut in enumerate(as_completed(futures), 1):
            url = futures[fut]
            article = fut.result()
            if not article.text or len(article.text.strip()) == 0:
                verdicts[url] = None
            else:
                verdicts[url] = geo_mentions_country(article.text, iso3)
            if i % 300 == 0 or i == len(urls):
                print(f"    [{iso3}] geo-recheck {i}/{len(urls)}", flush=True)
    return verdicts


def summarize(iso3: str, cached: list[dict], geo_verdicts: dict[str, bool | None]) -> dict:
    n = len(cached)
    retrievable = sum(1 for a in cached if a["retrievable"])
    rich = [a for a in cached if a["content_marker_hits"] >= 1]
    content_rich_before = len(rich)

    unknown = sum(1 for a in rich if geo_verdicts.get(a["url"]) is None)
    excluded = sum(1 for a in rich if geo_verdicts.get(a["url"]) is False)
    content_rich_after = content_rich_before - excluded

    retrievable_pct = 100 * retrievable / n if n else 0.0
    rich_pct_before = 100 * content_rich_before / n if n else 0.0
    rich_pct_after = 100 * content_rich_after / n if n else 0.0

    return {
        "iso3": iso3,
        "n": n,
        "retrievable": retrievable,
        "retrievable_pct": retrievable_pct,
        "content_rich_before": content_rich_before,
        "content_rich_pct_before": rich_pct_before,
        "geo_mismatch_excluded": excluded,
        "geo_recheck_unknown": unknown,
        "content_rich_after": content_rich_after,
        "content_rich_pct_after": rich_pct_after,
        "retrievable_pass": retrievable_pct >= RETRIEVABILITY_BAR_PCT,
        "content_rich_pass_before": rich_pct_before >= CONTENT_RICH_BAR_PCT,
        "content_rich_pass_after": rich_pct_after >= CONTENT_RICH_BAR_PCT,
    }


def main() -> None:
    summaries = []
    for iso3 in ["USA", "AUS", "IND", "BRA", "IDN", "KEN"]:
        print(f"=== {iso3} ===")
        cached = load_cached_articles(iso3)
        rich_urls = [a["url"] for a in cached if a["content_marker_hits"] >= 1]
        print(f"  {len(cached)} matched (cached), {len(rich_urls)} content-rich to geo-recheck")
        geo_verdicts = refetch_geo_check(iso3, rich_urls)
        summaries.append(summarize(iso3, cached, geo_verdicts))

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump({"summaries": summaries}, f, indent=2, ensure_ascii=False)

    print(
        "\n=== BEFORE / AFTER: retrievability & content-depth, geo-heuristic exclusion applied ==="
    )
    header = (
        f"{'':4} {'N':>7} {'Retr%':>7} {'Rich%before':>12} {'Rich%after':>11} "
        f"{'Excluded':>9} {'Unknown':>8} {'PassBefore':>11} {'PassAfter':>10}"
    )
    print(header)
    for s in summaries:
        print(
            f"{s['iso3']:4} {s['n']:7} {s['retrievable_pct']:6.1f}% "
            f"{s['content_rich_pct_before']:11.1f}% {s['content_rich_pct_after']:10.1f}% "
            f"{s['geo_mismatch_excluded']:9} {s['geo_recheck_unknown']:8} "
            f"{str(s['content_rich_pass_before']):>11} {str(s['content_rich_pass_after']):>10}"
        )

    print(
        "\nNote: this is a keyword/demonym-presence heuristic proxy for the production "
        "LLM-based geo cross-check (pipeline.extraction.geo_crosscheck) -- not the same "
        "mechanism that governs USA/AUS/IND's real Step 3 content-comparison track. See "
        "dev/active/flu-pipeline/context.md for why a full LLM pass at this scale isn't "
        "feasible on the current Groq free tier. Retrievability/content_marker_hits reused "
        "from the prior full audit (usa/aus/ind_full_audit_results.json, "
        "bra_idn_full_retrievability_results.json, ken_full_retrievability_results.json), "
        "not recomputed here, for an apples-to-apples 'before' number."
    )
    print(f"Results written to {OUT_PATH}")


if __name__ == "__main__":
    main()
