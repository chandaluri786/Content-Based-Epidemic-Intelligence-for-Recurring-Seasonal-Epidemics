"""
Top-level orchestration for the GDELT flu-article extraction pipeline.

Usage:
    python run_pipeline.py --countries USA AUS IND --start-year 2015 --end-year 2018

    # Smoke test: skip Stage 1/2 (no FluNet call) and run Stages 3-10 against
    # exactly one GDELT 15-minute file:
    python run_pipeline.py --test-timestamp 20230115121500 --countries USA IND

Runs all 10 stages end to end for the requested countries. See README.md
for the full stage-by-stage explanation, required configuration, and the
decisions behind this design.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from config import COMPLETED_DAYS_PATH, RUN_SUMMARY_PATH, STUDY_YEARS, TARGET_COUNTRIES
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


@dataclass(frozen=True)
class StoredArticleSummary:
    """Just enough about one stored article to build the per-window count
    report below -- not the full ExtractedArticle, so a long run doesn't
    have to hold every article's cleaned text in memory a second time on
    top of what's already been written to storage."""
    gkg_datetime: str
    country_fips_mentioned: frozenset[str]


def build_cohort_windows(countries: list[str], start_year: int, end_year: int) -> list[CountrySeasonWindow]:
    """Stage 1 + 2 for every requested country, restricted to season years
    in [start_year, end_year] inclusive. The cohort does double duty: it
    drives WHEN the pipeline looks (these windows feed Stage 3's day
    selection) and, via Stage 5's location filter, WHICH places' content
    gets kept -- the same TARGET_COUNTRIES list backs both."""
    all_windows: list[CountrySeasonWindow] = []
    for country in countries:
        onsets = compute_season_onsets(country, start_year, end_year)
        logger.info("Stage 1: %s -- %d season onsets found", country, len(onsets))
        all_windows.extend(windows.build_window(onset) for onset in onsets)
    return all_windows


def find_candidates_for_day(day, target_countries: dict[str, str]) -> list[MatchedArticle]:
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


def fetch_clean_and_store(candidates: list[MatchedArticle], storage, seen_ids: set[str]) -> list[StoredArticleSummary]:
    """Stages 6-10. Each unique GDELT record is fetched, cleaned, and stored
    at most once. Deduped on gkg_record_id, not url: record_id is
    deterministic -- the same raw GDELT file + line always parses to the
    same record_id -- which is exactly what's needed to recognize "this
    day's file was already processed in an earlier run" (the actual
    mechanism behind duplicate storage on overlapping windows: see
    _day_needs_processing below). seen_ids is seeded from
    storage.already_stored_ids() by the caller, so this also catches
    duplicates across separate runs, not just within one. Returns a
    lightweight summary of every article actually stored, for the
    end-of-run per-window report."""
    stored: list[StoredArticleSummary] = []

    for candidate in candidates:
        if candidate.record.record_id in seen_ids:
            continue
        seen_ids.add(candidate.record.record_id)

        html = fetch_html(candidate.record.url)
        if html is None:
            continue

        extraction = extract(html)
        retrievable = is_retrievable(extraction)
        rich = retrievable and is_content_rich(candidate.record, candidate.flu_theme_hits)

        if not (retrievable and rich):
            continue  # storage only ever receives articles that pass both quality gates

        gkg_datetime = _to_iso_datetime(candidate.record.timestamp)
        article = ExtractedArticle(
            gkg_record_id=candidate.record.record_id,
            url=candidate.record.url,
            gkg_datetime=gkg_datetime,
            themes=candidate.flu_theme_hits,
            locations=list(candidate.record.locations),
            article_text=extraction.text or "",
        )
        storage.write(article)
        stored.append(StoredArticleSummary(
            gkg_datetime=gkg_datetime,
            country_fips_mentioned=frozenset(loc.country_fips for loc in article.locations),
        ))

    return stored


def build_window_report(
    cohort_windows: list[CountrySeasonWindow],
    stored: list[StoredArticleSummary],
    target_countries: dict[str, str],
) -> list[dict]:
    """For each (country, season_year) window, counts how many stored
    articles fall inside it by date -- regardless of which country they
    mention -- and, within that subset, how many mention each requested
    country.

    Both kinds of overlap are expected, not bugs: a window's total can
    include articles about a different cohort country (its calendar days
    can be shared with another country's window -- see README section 6 /
    section 7 on why `locations` isn't narrowed), and the per-country counts
    can sum to more than the window's total if a single article mentions
    more than one requested country.
    """
    report: list[dict] = []
    for window in cohort_windows:
        in_window = [
            s for s in stored
            if window.window_start <= datetime.fromisoformat(s.gkg_datetime).date() <= window.window_end
        ]
        per_country_counts = {
            iso3: sum(1 for s in in_window if fips in s.country_fips_mentioned)
            for iso3, fips in target_countries.items()
        }
        report.append({
            "country": window.country_iso3,
            "season_year": window.season_year,
            "window_start": window.window_start.isoformat(),
            "window_end": window.window_end.isoformat(),
            "total_articles": len(in_window),
            "per_country_counts": per_country_counts,
        })
    return report


def _log_and_save_report(report: list[dict], summary_path: str = RUN_SUMMARY_PATH) -> None:
    logger.info("Per-window article counts:")
    for row in report:
        logger.info(
            "  %s season %s (%s to %s): total=%d, per-country=%s",
            row["country"], row["season_year"], row["window_start"], row["window_end"],
            row["total_articles"], row["per_country_counts"],
        )

    path = Path(summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    logger.info("Window summary written to %s", path)


def _load_completed_days(path: str) -> dict[date, set[str]]:
    """Each entry: a calendar day -> the set of countries whose candidates
    were already checked for that day in some previous run. Day + country
    set together, not day alone -- see _day_needs_processing for why."""
    p = Path(path)
    if not p.exists():
        return {}
    raw: dict[str, list[str]] = json.loads(p.read_text())
    return {date.fromisoformat(day): set(countries) for day, countries in raw.items()}


def _save_completed_days(completed: dict[date, set[str]], path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    serializable = {day.isoformat(): sorted(countries) for day, countries in completed.items()}
    p.write_text(json.dumps(serializable, indent=2))


def _day_needs_processing(day: date, requested_countries: set[str], completed: dict[date, set[str]]) -> bool:
    """A day can be skipped only if every country this run cares about was
    already checked for that day in some earlier run. If a later run asks
    for a country that wasn't part of that earlier check (e.g. an earlier
    run only covered --countries USA and this one adds IND), the day must
    be reprocessed -- a day's checkpoint entry is a lower bound on what's
    been checked, never an upper bound on what COULD be found there."""
    already_checked = completed.get(day, set())
    return not requested_countries.issubset(already_checked)


def run_test_timestamp(timestamp: str, countries: list[str]) -> None:
    """Smoke-test mode: skips Stage 1/2 entirely (no FluNet call, no real
    season window) and runs Stages 3-10 against exactly one GDELT file.
    Reports against a single synthetic one-day "window" (country_iso3
    "TEST") since there's no real season window to report against here --
    this is for checking the mechanics work, not for real counts."""
    target_countries = {iso3: fips for iso3, fips in TARGET_COUNTRIES.items() if iso3 in countries}
    file_url = gkg_downloader.file_url_for_timestamp(timestamp)

    lines = gkg_downloader.download_file(file_url)
    if lines is None:
        logger.warning(
            "Could not download %s -- that 15-minute slot may have no published file, or the request failed.",
            file_url,
        )
        return

    candidates: list[MatchedArticle] = []
    for raw_line in lines:
        record = gkg_parser.parse_line(raw_line)
        if record is None or not is_flu_candidate(record, target_countries):
            continue
        candidates.append(MatchedArticle(record=record, flu_theme_hits=flu_theme_hits(record)))

    logger.info("Test file %s: %d raw lines, %d candidates after Stage 5", file_url, len(lines), len(candidates))

    storage = get_storage_backend()
    seen_ids = storage.already_stored_ids()
    stored = fetch_clean_and_store(candidates, storage, seen_ids)
    logger.info("Test file %s: %d articles stored after Stages 8-9", file_url, len(stored))

    test_date = datetime.strptime(timestamp, "%Y%m%d%H%M%S").date()
    synthetic_window = CountrySeasonWindow(
        country_iso3="TEST", season_year=test_date.year, onset_date=test_date,
        window_start=test_date, window_end=test_date,
    )
    report = build_window_report([synthetic_window], stored, target_countries)
    _log_and_save_report(report, summary_path="./output/test_run_summary.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="GDELT flu-article extraction pipeline")
    parser.add_argument(
        "--countries", nargs="+", choices=list(TARGET_COUNTRIES), default=list(TARGET_COUNTRIES),
        help="Cohort countries (default: all configured countries). Drives both the ingestion windows "
             "(Stage 2) and the location filter (Stage 5) -- an article must mention one of these to be kept.",
    )
    parser.add_argument(
        "--start-year", type=int, default=min(STUDY_YEARS),
        help="Earliest season year to pull ground truth for, inclusive (default: earliest configured study year).",
    )
    parser.add_argument(
        "--end-year", type=int, default=max(STUDY_YEARS),
        help="Latest season year to pull ground truth for, inclusive (default: latest configured study year).",
    )
    parser.add_argument(
        "--test-timestamp", metavar="YYYYMMDDHHMMSS",
        help="Smoke-test mode: skip Stage 1/2 (no FluNet call) and run Stages 3-10 against exactly one "
             "GDELT file, e.g. 20230115121500. Ignores --start-year/--end-year.",
    )
    args = parser.parse_args()

    if args.test_timestamp:
        run_test_timestamp(args.test_timestamp, args.countries)
        return

    if args.end_year < args.start_year:
        parser.error(f"--end-year ({args.end_year}) must be >= --start-year ({args.start_year})")

    cohort_windows = build_cohort_windows(args.countries, args.start_year, args.end_year)
    if not cohort_windows:
        logger.warning("No onsets found for the requested countries/years -- nothing to do.")
        return

    unique_days = windows.unique_days_across_cohort(cohort_windows)
    logger.info(
        "Stage 2: %d unique calendar days to ingest across %d country-seasons",
        len(unique_days), len(cohort_windows),
    )

    requested_countries = set(args.countries)
    completed_days = _load_completed_days(COMPLETED_DAYS_PATH)
    days_to_process = sorted(
        day for day in unique_days if _day_needs_processing(day, requested_countries, completed_days)
    )
    skipped_count = len(unique_days) - len(days_to_process)
    if skipped_count:
        logger.info(
            "Skipping %d day(s) already fully checked for %s in a previous run (see %s)",
            skipped_count, sorted(requested_countries), COMPLETED_DAYS_PATH,
        )

    storage = get_storage_backend()
    seen_ids: set[str] = storage.already_stored_ids()  # dedupe across this run AND prior runs, by gkg_record_id
    target_countries = {iso3: fips for iso3, fips in TARGET_COUNTRIES.items() if iso3 in args.countries}

    all_stored: list[StoredArticleSummary] = []
    for day in days_to_process:
        candidates = find_candidates_for_day(day, target_countries)
        all_stored.extend(fetch_clean_and_store(candidates, storage, seen_ids))
        completed_days[day] = completed_days.get(day, set()) | requested_countries
        _save_completed_days(completed_days, COMPLETED_DAYS_PATH)  # save after each day, not just at the end

    logger.info("Done. %d new unique article(s) stored this run.", len(all_stored))

    report = build_window_report(cohort_windows, all_stored, target_countries)
    _log_and_save_report(report)


if __name__ == "__main__":
    main()
