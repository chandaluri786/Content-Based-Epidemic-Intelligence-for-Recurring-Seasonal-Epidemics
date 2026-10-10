"""
Builds the pooled labeling corpus from every teammate's pipeline output
(read by the labeling sampler, sampling/ on the sample-extractor
branch). Run the subcommands in order:

    python prepare_pool.py dedup      # Step 1: exact dedup across dataset/<year>/ files
    python prepare_pool.py windows    # Step 2: season windows (FluNet) + old-vs-new onset table
    python prepare_pool.py gaps       # Step 2: window days missing from the pool -> seeded checkpoint
    python prepare_pool.py assign     # Step 2: country_seasons / sampling_country per article
    python prepare_pool.py neardup    # Step 3: near-duplicate groups (MinHash LSH)

After a gap-fill pipeline run, copy its output into dataset/ and re-run
dedup, assign and neardup. Every output lands in --out (default
output/pool/); see README "Pooled labeling corpus".
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from config import POOL_DIR, STUDY_YEARS, TARGET_COUNTRIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POOLED_ARTICLES_FILE = "pooled_articles.jsonl"
SEASON_WINDOWS_FILE = "season_windows.json"


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    logger.info("Wrote %s", path)


def cmd_dedup(args: argparse.Namespace) -> None:
    from dataset_prep.exact_dedup import dedup_dataset

    report = dedup_dataset(Path(args.dataset_dir), Path(args.out) / POOLED_ARTICLES_FILE)
    _write_json(Path(args.out) / "dedup_report.json", report)
    logger.info(
        "Exact dedup: %d records in, %d out (%d duplicates removed, %d bad lines)",
        report["rows_in"], report["rows_out"], report["duplicates_removed"], report["bad_lines"],
    )


def cmd_windows(args: argparse.Namespace) -> None:
    from dataclasses import asdict

    from dataset_prep.season_report import build_cohort, format_table
    from pipeline.windows import save_windows

    cohort, diagnostics = build_cohort(list(TARGET_COUNTRIES), args.start_year, args.end_year)
    save_windows(cohort, Path(args.out) / SEASON_WINDOWS_FILE)
    _write_json(Path(args.out) / "season_diagnostics.json",
                [{**asdict(d), "onset_date": d.onset_date.isoformat() if d.onset_date else None} for d in diagnostics])
    print(format_table(diagnostics))
    logger.info("%d country-season windows saved to %s", len(cohort), Path(args.out) / SEASON_WINDOWS_FILE)


def _write_gapfill_dir(directory: Path, cohort, days, countries: set[str]) -> None:
    from dataset_prep.gap_days import seeded_checkpoint
    from run_pipeline import _save_completed_days

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "target_days.txt").write_text("".join(f"{d.isoformat()}\n" for d in days))
    _save_completed_days(seeded_checkpoint(cohort, days, countries), str(directory / "completed_days.json"))


def cmd_gaps(args: argparse.Namespace) -> None:
    from collections import Counter

    from dataset_prep.gap_days import covered_days, find_gap_days, shard_days
    from pipeline.windows import load_windows

    out = Path(args.out)
    cohort = load_windows(out / SEASON_WINDOWS_FILE)
    gaps = find_gap_days(cohort, covered_days(out / POOLED_ARTICLES_FILE))
    per_year = Counter(d.year for d in gaps)
    logger.info("%d gap day(s) across %d windows; per year: %s", len(gaps), len(cohort), dict(sorted(per_year.items())))

    gapfill_dir = Path(args.gapfill_dir)
    shards = [gaps] if args.shards == 1 else shard_days(gaps, args.shards)
    for i, days in enumerate(shards):
        shard_dir = gapfill_dir if args.shards == 1 else gapfill_dir / f"shard_{i}"
        _write_gapfill_dir(shard_dir, cohort, days, set(TARGET_COUNTRIES))
        logger.info(
            "Shard %d (%d days): PIPELINE_COMPLETED_DAYS_PATH=%s PIPELINE_LOCAL_STORAGE_DIR=%s "
            "PIPELINE_RUN_SUMMARY_PATH=%s python run_pipeline.py",
            i, len(days), shard_dir / "completed_days.json", shard_dir / "extracted_articles",
            shard_dir / "run_summary.json",
        )


def cmd_assign(args: argparse.Namespace) -> None:
    from dataset_prep.season_assign import write_assignments
    from pipeline.windows import load_windows

    out = Path(args.out)
    summary = write_assignments(out / POOLED_ARTICLES_FILE, load_windows(out / SEASON_WINDOWS_FILE),
                                TARGET_COUNTRIES, out / "season_assignments.jsonl")
    _write_json(out / "season_assignment_report.json", summary)
    logger.info(
        "Season assignment: %d articles, %d assigned, %d outside all windows, %d in a window but mention no "
        "active country", summary["articles"], summary["assigned"], summary["outside_all_windows"],
        summary["in_window_but_no_active_country_mentioned"],
    )


def cmd_neardup(args: argparse.Namespace) -> None:
    from dataset_prep.near_dup import run_near_dup

    out = Path(args.out)
    report = run_near_dup(out / POOLED_ARTICLES_FILE, out / "near_dup_groups.jsonl")
    _write_json(out / "near_dup_report.json", report)
    logger.info("Near-dup: %d articles -> %d groups (%d articles in %d multi-member groups)",
                report["articles"], report["groups"], report["articles_in_multi_member_groups"],
                report["multi_member_groups"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pooled labeling corpus preparation")
    parser.add_argument("--out", default=POOL_DIR, help=f"Output directory (default: {POOL_DIR})")
    sub = parser.add_subparsers(dest="command", required=True)

    dedup = sub.add_parser("dedup", help="Step 1: exact dedup across dataset files")
    dedup.add_argument("--dataset-dir", default="dataset", help="Folder of <year>/<source>.jsonl files (default: dataset)")
    dedup.set_defaults(func=cmd_dedup)

    win = sub.add_parser("windows", help="Step 2: full-cohort season windows from FluNet, with diagnostics")
    win.add_argument("--start-year", type=int, default=min(STUDY_YEARS))
    win.add_argument("--end-year", type=int, default=max(STUDY_YEARS))
    win.set_defaults(func=cmd_windows)

    gaps = sub.add_parser("gaps", help="Step 2: window days with no pooled articles -> seeded checkpoint for a gap-fill run")
    gaps.add_argument("--gapfill-dir", default="output/gapfill", help="Where target_days.txt and the seeded "
                      "completed_days.json go (default: output/gapfill)")
    gaps.add_argument("--shards", type=int, default=1, help="Split the gap days into this many disjoint shards "
                      "(<gapfill-dir>/shard_<i>/), each run as its own pipeline process (default: 1)")
    gaps.set_defaults(func=cmd_gaps)

    assign = sub.add_parser("assign", help="Step 2: country_seasons / sampling_country for every pooled article")
    assign.set_defaults(func=cmd_assign)

    neardup = sub.add_parser("neardup", help="Step 3: near-duplicate groups (MinHash LSH)")
    neardup.set_defaults(func=cmd_neardup)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
