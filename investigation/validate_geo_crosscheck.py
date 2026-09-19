"""Validates the geotagging cross-check (pipeline.extraction.geo_crosscheck)
against the three confirmed GDELT mistagging cases found this session, before
trusting it for real use in run_step3_extract.py.

Case 1 (Brazil): the original feasibility spike's bobfm.co.uk article, about
Australia's Northern Territory flu-vaccine rollout, mistagged as Brazil
(investigation/report.md).
Case 2 (Kenya): the AP wire story about US hospital mask mandates, mistagged
to 117 of Kenya's 163 matched articles (dev/active/flu-pipeline/context.md;
WIRE_STORY_URL_FRAGMENTS reused from check_ken_full_retrievability.py).
Case 3 (India): an Australian bird-flu story, GDELT's largest single
mistagged cluster within India's matched articles (SLUG_RE reused from
check_aus_ind_usa_full_audit.py).

Also runs a specificity guard against Kenya's confirmed-genuine outlets and a
random India sample outside the known-bad cluster, so sensitivity isn't
coming at the cost of over-flagging well-tagged content.

Usage:
    python -m investigation.validate_geo_crosscheck
"""

import json
import os
import random
import re
from pathlib import Path

from dotenv import load_dotenv

from pipeline.config import GROQ_EXTRACTION_MODEL_POOL
from pipeline.extraction.geo_crosscheck import classify_geo_match
from pipeline.extraction.llm_client import ExtractionFailure, GroqExtractionClient
from pipeline.extraction.multi_model_client import MultiModelExtractionClient
from pipeline.extraction.relevance import passes_rule_prefilter
from pipeline.gdelt.article_fetcher import fetch_article_text

REPO_ROOT = Path(__file__).resolve().parents[1]
MATCHED_DIR = REPO_ROOT / "data" / "gdelt_matched"
OUT_PATH = Path(__file__).resolve().parent / "geo_crosscheck_validation_results.json"

SAMPLE_SIZE = 20
# Kenya's wire-story URLs (mostly ephemeral US local-TV syndication pages from
# Jan 2024) have an unusually high link-rot rate -- confirmed empirically:
# 15/20 of a first sample were already not_retrievable, leaving too small a
# classified count (n=4) to read the disagree rate reliably. Sampling more
# compensates for that attrition rather than trusting a tiny surviving subset.
KEN_BAD_SAMPLE_SIZE = 60
GOOD_SAMPLE_SIZE = 15
SEED = 2026
DISAGREE_RATE_BAR = 0.9
FALSE_POSITIVE_BAR = 0.10

# Case 2: same fragments as check_ken_full_retrievability.py.
WIRE_STORY_URL_FRAGMENTS = (
    "more-hospitals-are-requiring-masks",
    "hospitals-requiring-masks-as-flu",
)

# Kenya's confirmed genuine outlets (context.md) -- used for the specificity guard.
KEN_GENUINE_DOMAINS = (
    "standardmedia.co.ke",
    "businessdailyafrica.com",
    "kenyans.co.ke",
    "capitalfm.co.ke",
)

# Major Indian news domains -- used for the India specificity guard. A plain
# random sample of India's matched set is NOT a reliable "known good" pool:
# it independently turned up a second real mistagged cluster (a regional FAO
# avian-flu bulletin syndicated across Cambodia/Sri Lanka/poultry-trade sites,
# tagged to India) during validation, confirming India's matched set has more
# than the one known bad cluster. Named, well-known domestic outlets are a
# much safer "genuinely about India" signal for measuring false positives.
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

# Case 3: same slug regex/cluster as check_aus_ind_usa_full_audit.py.
SLUG_RE = re.compile(r"/([a-z0-9-]{20,})(?:\.\w+)?(?:[/?].*)?$")
IND_MISTAGGED_SLUG = "australias-first-human-case-of-bird-flu-detected-in-victoria"

# Case 1: the bobfm.co.uk mistag from the original spike (investigation/report.md).
# NOTE (found during this validation, not assumed going in): the article's
# HEADLINE says "Northern Territory" (Australia) but its BODY text lists real
# Brazilian state names/abbreviations (Acre, Amazonas, Amapa, Para, Rondonia,
# Roraima, Tocantins) with vaccine-dose figures per state -- a content-farm
# template mismatch (recycled headline, swapped-in body), not a clean
# Australia-vs-Brazil case with zero counter-evidence. The model agreeing
# with BRA here is a defensible reading of the actual fetched text, not
# obviously a cross-check failure -- reported as informational, not a hard
# pass/fail gate, unlike Cases 2 and 3 which have unambiguous ground truth.
BRA_KNOWN_BAD_URL = (
    "https://www.bobfm.co.uk/the-northern-territory-receives-more-than-6-5-million-doses-of-flu-vaccine/"
)


def load_urls(iso3: str) -> list[str]:
    urls = []
    with (MATCHED_DIR / f"{iso3}.jsonl").open(encoding="utf-8") as f:
        for line in f:
            urls.append(json.loads(line)["url"])
    return urls


def slug(url: str) -> str:
    m = SLUG_RE.search(url)
    return m.group(1)[:80] if m else url


def build_client() -> MultiModelExtractionClient:
    api_key = os.environ["GROQ_API_KEY"]
    clients = [GroqExtractionClient(api_key=api_key, model=m) for m in GROQ_EXTRACTION_MODEL_POOL]
    return MultiModelExtractionClient(clients)


def classify_one(client: MultiModelExtractionClient, url: str, gdelt_country: str) -> dict:
    article = fetch_article_text(url)
    if not article.retrievable:
        return {"url": url, "outcome": "not_retrievable"}
    if not passes_rule_prefilter(article.text):
        return {"url": url, "outcome": "skipped_prefilter"}
    result = client.extract(article.text, country_hint=gdelt_country)
    if isinstance(result, ExtractionFailure):
        return {"url": url, "outcome": "failed", "reason": result.reason}
    verdict = classify_geo_match(result.primary_country, gdelt_country)
    return {
        "url": url,
        "outcome": "classified",
        "primary_country": result.primary_country,
        "verdict": verdict,
    }


def run_case(client: MultiModelExtractionClient, label: str, urls: list[str], gdelt_country: str) -> dict:
    print(f"=== {label}: {len(urls)} URLs ===")
    records = [classify_one(client, u, gdelt_country) for u in urls]
    classified = [r for r in records if r["outcome"] == "classified"]
    disagree = [r for r in classified if r["verdict"] == "disagree"]
    rate = len(disagree) / len(classified) if classified else 0.0
    print(
        f"  {len(classified)}/{len(urls)} classified, "
        f"{len(disagree)}/{len(classified) or 1} flagged disagree ({rate:.0%})"
    )
    return {
        "label": label,
        "records": records,
        "classified": len(classified),
        "disagree": len(disagree),
        "disagree_rate": rate,
    }


def main() -> None:
    load_dotenv()
    client = build_client()

    ind_urls = load_urls("IND")
    ind_bad = [u for u in ind_urls if slug(u) == IND_MISTAGGED_SLUG]
    ind_good_pool = [u for u in ind_urls if any(d in u for d in IND_GENUINE_DOMAINS)]

    ken_urls = load_urls("KEN")
    ken_bad = [u for u in ken_urls if any(f in u for f in WIRE_STORY_URL_FRAGMENTS)]
    ken_good = [u for u in ken_urls if any(d in u for d in KEN_GENUINE_DOMAINS)]

    random.seed(SEED)
    ind_bad_sample = random.sample(ind_bad, min(SAMPLE_SIZE, len(ind_bad)))
    ken_bad_sample = random.sample(ken_bad, min(KEN_BAD_SAMPLE_SIZE, len(ken_bad)))
    ind_good_sample = random.sample(ind_good_pool, min(GOOD_SAMPLE_SIZE, len(ind_good_pool)))

    results = {
        "case1_brazil": run_case(
            client, "Case 1: Brazil/bobfm.co.uk (known bad, n=1)", [BRA_KNOWN_BAD_URL], "BRA"
        ),
        "case2_kenya_bad": run_case(
            client, "Case 2: Kenya wire story (known bad)", ken_bad_sample, "KEN"
        ),
        "case3_india_bad": run_case(
            client, "Case 3: India/Australia bird-flu cluster (known bad)", ind_bad_sample, "IND"
        ),
        "specificity_kenya_good": run_case(
            client, "Specificity guard: Kenya known-genuine outlets", ken_good, "KEN"
        ),
        "specificity_india_good": run_case(
            client, "Specificity guard: India known-genuine outlets", ind_good_sample, "IND"
        ),
    }

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n=== VALIDATION SUMMARY ===")
    c1 = results["case1_brazil"]
    c2 = results["case2_kenya_bad"]
    c3 = results["case3_india_bad"]
    sg_ken = results["specificity_kenya_good"]
    sg_ind = results["specificity_india_good"]

    case2_pass = c2["classified"] > 0 and c2["disagree_rate"] >= DISAGREE_RATE_BAR
    case3_pass = c3["classified"] > 0 and c3["disagree_rate"] >= DISAGREE_RATE_BAR
    total_good_classified = sg_ken["classified"] + sg_ind["classified"]
    total_good_disagree = sg_ken["disagree"] + sg_ind["disagree"]
    fp_rate = total_good_disagree / total_good_classified if total_good_classified else 0.0
    fp_pass = fp_rate <= FALSE_POSITIVE_BAR

    print(
        f"Case 1 (Brazil, informational -- see BRA_KNOWN_BAD_URL note, not a hard gate): "
        f"primary_country={c1['records'][0].get('primary_country') if c1['records'] else 'n/a'}"
    )
    print(
        f"Case 2 (Kenya, >={DISAGREE_RATE_BAR:.0%} disagree): {'PASS' if case2_pass else 'FAIL'} "
        f"({c2['disagree_rate']:.0%})"
    )
    print(
        f"Case 3 (India, >={DISAGREE_RATE_BAR:.0%} disagree): {'PASS' if case3_pass else 'FAIL'} "
        f"({c3['disagree_rate']:.0%})"
    )
    print(
        f"Specificity guard (<={FALSE_POSITIVE_BAR:.0%} false-positive rate on known-good): "
        f"{'PASS' if fp_pass else 'FAIL'} ({fp_rate:.0%})"
    )
    overall = case2_pass and case3_pass and fp_pass
    verdict = "READY to wire into run_step3_extract.py" if overall else "NOT READY -- revise prompt/schema first"
    print(f"\nOVERALL: {verdict}")
    print(f"Results written to {OUT_PATH}")


if __name__ == "__main__":
    main()
