"""Validate geo_matches_comparative (the fixed, comparative-count version of
the audit-scale geo heuristic) before wiring it into the Wave 1 audit rerun.

Two checks, same discipline as the original LLM-based geo_crosscheck
validation (investigation/validate_geo_crosscheck.py):

1. Known mismatch: the India/Australia bird-flu cluster (already confirmed
   as a mistag) -- must be flagged False (excluded) for IND.
2. Specificity guard: named, well-known Indian domestic outlets (not a
   random sample -- validate_geo_crosscheck.py's own note explains why a
   random IND sample isn't a safe "known good" pool, since it independently
   turned up a second real mistagged cluster) -- must mostly still pass
   (not over-excluded).
"""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.gdelt.article_fetcher import fetch_article_text
from investigation.geo_heuristic_recheck import GEO_KEYWORDS, geo_matches_comparative

REPO_ROOT = Path(__file__).resolve().parent.parent
COHORT = ["USA", "AUS", "BRA", "IND", "KEN", "IDN"]

KNOWN_MISMATCH_URLS = [
    "https://www.portstephensexaminer.com.au/story/8637577/australias-first-human-case-of-bird-flu-detected-in-victoria/?cs=2763",
    "https://www.theadvocate.com.au/story/8637577/australias-first-human-case-of-bird-flu-detected-in-victoria/?cs=9676",
    "https://www.macleayargus.com.au/story/8637577/australias-first-human-case-of-bird-flu-detected-in-victoria/?cs=9676",
    "https://www.mandurahmail.com.au/story/8637577/australias-first-human-case-of-bird-flu-detected-in-victoria/?cs=30776",
]

# Same named-domain specificity guard as validate_geo_crosscheck.py, not a
# random sample of IND's matched set.
IND_GENUINE_DOMAINS = (
    "timesofindia.indiatimes.com",
    "indianexpress.com",
    "thehindu.com",
    "hindustantimes.com",
    "ndtv.com",
    "business-standard.com",
    "livemint.com",
    "deccanherald.com",
    "indiatoday.in",
)


def load_ind_genuine_urls(max_per_domain: int = 3) -> list[str]:
    with (REPO_ROOT / "data" / "gdelt_matched" / "IND.jsonl").open() as f:
        urls = [json.loads(line)["url"] for line in f]
    picked: list[str] = []
    per_domain_count: dict[str, int] = {}
    for u in urls:
        domain = urlparse(u).netloc.lower().replace("www.", "")
        if domain in IND_GENUINE_DOMAINS and per_domain_count.get(domain, 0) < max_per_domain:
            picked.append(u)
            per_domain_count[domain] = per_domain_count.get(domain, 0) + 1
    return picked


def main() -> None:
    print("=== Check 1: known India/Australia mismatch cluster (must be excluded) ===")
    mismatch_results = []
    for url in KNOWN_MISMATCH_URLS:
        article = fetch_article_text(url)
        if not article.text or len(article.text.strip()) == 0:
            print(f"  {url[:70]}...  NO TEXT (skipped)")
            continue
        matches = geo_matches_comparative(article.text, "IND", COHORT)
        mismatch_results.append(matches)
        verdict = "FAIL (still passes as IND)" if matches else "PASS (correctly excluded)"
        print(f"  {url[:70]}...  {verdict}")

    n_correctly_excluded = sum(1 for m in mismatch_results if not m)
    print(
        f"\nResult: {n_correctly_excluded}/{len(mismatch_results)} known-mismatch URLs "
        "correctly excluded."
    )

    print("\n=== Check 2: specificity guard -- genuine India domestic outlets (must mostly pass) ===")
    genuine_urls = load_ind_genuine_urls()
    print(f"Testing {len(genuine_urls)} URLs from named Indian domestic outlets...")
    genuine_results = []
    for url in genuine_urls:
        article = fetch_article_text(url)
        if not article.text or len(article.text.strip()) == 0:
            print(f"  {url[:70]}...  NO TEXT (skipped)")
            continue
        matches = geo_matches_comparative(article.text, "IND", COHORT)
        genuine_results.append((url, matches))
        verdict = "PASS (correctly kept)" if matches else "FAIL (wrongly excluded)"
        print(f"  {url[:70]}...  {verdict}")

    n_pass = sum(1 for _, m in genuine_results if m)
    n_total = len(genuine_results)
    print(f"\nResult: {n_pass}/{n_total} genuine India articles correctly kept "
          f"({100*n_pass/n_total:.0f}% pass rate)." if n_total else "no results")

    out = {
        "known_mismatch": {
            "n_tested": len(mismatch_results),
            "n_correctly_excluded": n_correctly_excluded,
        },
        "specificity_guard": {
            "n_tested": n_total,
            "n_correctly_kept": n_pass,
            "pass_rate_pct": round(100 * n_pass / n_total, 1) if n_total else None,
            "wrongly_excluded": [u for u, m in genuine_results if not m],
        },
    }
    out_path = REPO_ROOT / "investigation" / "validate_geo_heuristic_comparative_results.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
