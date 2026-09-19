"""Step 3: fetch article text, apply the rule-based relevance prefilter, and
run LLM extraction on one country's Step 2 matched URLs.

Resumable via ExtractionStore: already-processed URLs are skipped, and a
DailyQuotaExceeded (Groq's 1000 RPD cap) stops the run cleanly rather than
raising -- rerun the same command on a later day to continue where it left
off, no flags needed to resume.

Usage:
    python -m pipeline.cli.run_step3_extract --country USA [--max-articles N]
"""

import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from pipeline.common.io_jsonl import read_jsonl_tolerant
from pipeline.config import GROQ_EXTRACTION_MODEL_POOL
from pipeline.extraction.extraction_store import ExtractionStore
from pipeline.extraction.geo_crosscheck import classify_geo_match
from pipeline.extraction.llm_client import (
    DailyQuotaExceeded,
    ExtractionFailure,
    GroqExtractionClient,
)
from pipeline.extraction.multi_model_client import MultiModelExtractionClient
from pipeline.extraction.relevance import passes_rule_prefilter
from pipeline.gdelt.article_fetcher import fetch_article_text

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MATCHED_DIR = DATA_DIR / "gdelt_matched"
EXTRACTIONS_DIR = DATA_DIR / "extractions"


def load_matched_urls(country: str) -> dict[str, str]:
    """Return {url: first_seen_stamp} for a country's Step 2 matched output."""
    matched_path = MATCHED_DIR / f"{country}.jsonl"
    urls: dict[str, str] = {}
    for record in read_jsonl_tolerant(str(matched_path)):
        urls.setdefault(record["url"], record["stamp"])
    return urls


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", required=True, help="ISO3, e.g. USA or KEN")
    parser.add_argument(
        "--max-articles", type=int, default=None, help="Stop after N new articles this run"
    )
    args = parser.parse_args()

    matched = load_matched_urls(args.country)
    EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
    store = ExtractionStore(str(EXTRACTIONS_DIR / f"{args.country}.jsonl"))

    api_key = os.environ["GROQ_API_KEY"]
    per_model_clients = [
        GroqExtractionClient(api_key=api_key, model=m) for m in GROQ_EXTRACTION_MODEL_POOL
    ]
    client = MultiModelExtractionClient(per_model_clients)
    print(f"Model pool (waterfall order): {', '.join(GROQ_EXTRACTION_MODEL_POOL)}")

    todo = [(url, stamp) for url, stamp in matched.items() if not store.is_done(url)]
    print(f"{len(matched)} total matched URLs for {args.country}, {len(todo)} not yet processed")
    if args.max_articles:
        todo = todo[: args.max_articles]

    start = time.monotonic()
    completed_this_run = 0  # every store.record(), regardless of status
    llm_calls_this_run = 0  # only extracted/failed -- what actually spends daily quota
    stopped_early = False

    for url, stamp in todo:
        article = fetch_article_text(url)
        if not article.retrievable:
            store.record(url, stamp=stamp, status="not_retrievable")
            completed_this_run += 1
            continue
        if not passes_rule_prefilter(article.text):
            store.record(url, stamp=stamp, status="skipped_prefilter")
            completed_this_run += 1
            continue

        try:
            result = client.extract(article.text, country_hint=args.country)
        except DailyQuotaExceeded:
            print(
                f"All {len(GROQ_EXTRACTION_MODEL_POOL)} pooled models exhausted their daily quota "
                f"after {llm_calls_this_run} LLM calls this run -- stopping cleanly."
            )
            stopped_early = True
            break

        if isinstance(result, ExtractionFailure):
            store.record(
                url,
                stamp=stamp,
                status="failed",
                reason=result.reason,
                model=client.last_used_model,
            )
        else:
            extraction = result.model_dump()
            geo_verdict = classify_geo_match(
                primary_country=extraction["primary_country"], gdelt_country=args.country
            )
            if geo_verdict == "disagree":
                store.record(
                    url,
                    stamp=stamp,
                    status="excluded_geo_mismatch",
                    extraction=extraction,
                    reason=f"geo_mismatch: gdelt_tag={args.country}, "
                    f"primary_country={extraction['primary_country']}",
                    model=client.last_used_model,
                )
            else:
                store.record(
                    url,
                    stamp=stamp,
                    status="extracted",
                    extraction=extraction,
                    model=client.last_used_model,
                )
        completed_this_run += 1
        llm_calls_this_run += 1

        if completed_this_run % 50 == 0:
            elapsed = time.monotonic() - start
            print(f"  [{completed_this_run}/{len(todo)}] elapsed {elapsed:.0f}s")

    total_remaining = len(matched) - len(store.iter_records())
    status = "stopped early (daily quota)" if stopped_early else "finished this batch"
    print(
        f"{status}: completed {completed_this_run} URLs this run ({llm_calls_this_run} LLM calls), "
        f"{total_remaining} remain overall for {args.country}."
    )


if __name__ == "__main__":
    main()
