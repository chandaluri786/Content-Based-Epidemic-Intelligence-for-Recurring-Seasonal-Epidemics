"""
Top-level orchestration for the GDELT flu-article extraction pipeline.

Usage:
    python run_pipeline.py --countries USA AUS IND --start-year 2015

Runs all 10 stages end to end for the requested countries. See README.md
for the full stage-by-stage explanation, required configuration, and the
decisions behind this design.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime
from urllib.parse import urlparse

from config import STUDY_YEARS, TARGET_COUNTRIES
from models import CountrySeasonWindow, ExtractedArticle, MatchedArticle
from pipeline import gkg_downloader, gkg_parser, windows
from pipeline.article_fetcher import fetch_html
from pipeline.content_extractor import extract
from pipeline.ground_truth import compute_season_onsets
from pipeline.quality_gates import is_content_rich, is_retrievable
from pipeline.storage import get_storage_backend
from pipeline.theme_matcher import flu_theme_hits, is_flu_candidate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def build_cohort_windows(countries: list[str], start_year: int) -> list[CountrySeasonWindow]:
    """Stage 1 + 2 for every requested country. The cohort does double duty:
    it drives WHEN the pipeline looks (these windows feed Stage 3's day
    selection) and, via Stage 5's location filter, WHICH places' content
    gets kept -- the same TARGET_COUNTRIES list backs both."""
    all_windows: list[CountrySeasonWindow] = []
    for country in countries:
        onsets = compute_season_onsets(country, start_year)
        logger.info("Stage 1: %s -- %d season onsets found", country, len(onsets))
        all_windows.extend(windows.build_window(onset) for onset in onsets)
    return all_windows


def find_candidates_for_day(day: date, target_countries: dict[str, str]) -> list[MatchedArticle]:
    """Stages 3-5 for a single calendar day: download every 15-minute file,
    parse, and run the combined theme+location filter (is_flu_candidate).
    target_countries is exactly the set requested on the CLI, not
    necessarily the full cohort -- see theme_matcher.countries_mentioned."""
    candidates: list[MatchedArticle] = []

    for file_url in gkg_downloader.iter_day_urls(day):
        lines = gkg_downloader.download_file(file_url)
        if lines is None:
            continue

        for raw_line in lines:
            record = gkg_parser.parse_line(raw_line)
            if record is None or not is_flu_candidate(record, target_countries):
                continue

            candidates.append(MatchedArticle(record=record, flu_theme_hits=flu_theme_hits(record)))

    logger.info("Stage 5: %s -- %d candidate articles matched", day.isoformat(), len(candidates))
    return candidates


def _to_iso_datetime(gkg_timestamp: str) -> str:
    """GKG timestamps are YYYYMMDDHHMMSS strings -- reformatted here to
    ISO 8601 for the stored record, since that's what the schema calls
    "datetime" (see README "Final storage structure")."""
    return datetime.strptime(gkg_timestamp, "%Y%m%d%H%M%S").isoformat()


def fetch_clean_and_store(candidates: list[MatchedArticle], storage, seen_urls: set[str]) -> None:
    """Stages 6-10. Each unique URL is fetched, cleaned, and stored at most
    once for the whole run."""
    for candidate in candidates:
        if candidate.record.url in seen_urls:
            continue
        seen_urls.add(candidate.record.url)

        html = fetch_html(candidate.record.url)
        if html is None:
            continue

        extraction = extract(html)
        retrievable = is_retrievable(extraction)
        rich = retrievable and is_content_rich(candidate.record, candidate.flu_theme_hits)

        if not (retrievable and rich):
            continue  # storage only ever receives articles that pass both quality gates

        article = ExtractedArticle(
            gkg_record_id=candidate.record.record_id,
            url=candidate.record.url,
            gkg_datetime=_to_iso_datetime(candidate.record.timestamp),
            themes=candidate.flu_theme_hits,
            locations=list(candidate.record.locations),
            article_text=extraction.text or "",
        )
        storage.write(article)


def main() -> None:
    parser = argparse.ArgumentParser(description="GDELT flu-article extraction pipeline")
    parser.add_argument(
        "--countries", nargs="+", choices=list(TARGET_COUNTRIES), default=list(TARGET_COUNTRIES),
        help="Cohort countries (default: all configured countries). Drives both the ingestion windows "
             "(Stage 2) and the location filter (Stage 5) -- an article must mention one of these to be kept.",
    )
    parser.add_argument(
        "--start-year", type=int, default=min(STUDY_YEARS),
        help="Earliest season year to pull ground truth for (default: earliest configured study year).",
    )
    args = parser.parse_args()

    cohort_windows = build_cohort_windows(args.countries, args.start_year)
    if not cohort_windows:
        logger.warning("No onsets found for the requested countries/years -- nothing to do.")
        return

    unique_days = windows.unique_days_across_cohort(cohort_windows)
    logger.info(
        "Stage 2: %d unique calendar days to ingest across %d country-seasons",
        len(unique_days), len(cohort_windows),
    )

    storage = get_storage_backend()
    seen_urls: set[str] = set()  # dedupe fetch+clean across the whole run, not just per-day
    target_countries = {iso3: fips for iso3, fips in TARGET_COUNTRIES.items() if iso3 in args.countries}

    for day in sorted(unique_days):
        candidates = find_candidates_for_day(day, target_countries)
        fetch_clean_and_store(candidates, storage, seen_urls)

    logger.info("Done. %d unique articles fetched across the run.", len(seen_urls))


if __name__ == "__main__":
    main()
