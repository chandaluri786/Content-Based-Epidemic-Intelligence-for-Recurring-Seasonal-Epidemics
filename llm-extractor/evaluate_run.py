"""Command-line tool: score a finished run against the gold labels and write the reports.

Example:
    python evaluate_run.py results/run_20261101_150000
Every city, state and country chain is looked up online in OpenStreetMap during the run (about 1
per second, each chain once per run; nothing is saved). Gold duplicate decisions are read from
data/duplicate_adjudication.json when it exists. The files written are listed in
flu_extractor/report.py; report.md is the summary to read first.
"""

import argparse
from pathlib import Path

from flu_extractor import config
from flu_extractor.data_loading import load_articles, load_gold_labels
from flu_extractor.duplicates import load_adjudication
from flu_extractor.evaluation import SCORED, evaluate_run, read_run_records
from flu_extractor.places import PlaceChecker
from flu_extractor.report import write_report


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path, help="run folder created by run_extraction.py")
    parser.add_argument("--offline", action="store_true",
                        help="do not look up place names online; use only the saved answers in "
                             "data/place_lookups.json (chains not saved are compared as written and "
                             "reported as 'could not be checked').")
    args = parser.parse_args()
    run_dir = args.run_dir

    records = read_run_records(run_dir / "raw_results.jsonl")
    articles = load_articles(config.ARTICLES_PATH)
    gold = load_gold_labels(config.GOLD_LABELS_PATH)
    adjudication = load_adjudication(config.ADJUDICATION_PATH)

    # Place names are looked up online during this run, each chain once, and kept in memory only.
    place_checker = PlaceChecker(config.PLACE_CACHE_PATH, offline=args.offline)

    evaluation = evaluate_run(records, articles, gold, place_checker, adjudication)
    write_report(evaluation, run_dir)

    s = evaluation.headline
    e, m = s.counts, s.metrics
    print(f"Scored {len(evaluation.rows_with_status(SCORED))} of {len(evaluation.rows)} articles "
          f"({len(records) - len(evaluation.rows)} in the run have no gold record).")
    print(f"Task 1, useful or not: F1 {fmt(s.usefulness.counts.f1)}, accuracy {fmt(s.usefulness.accuracy)}")
    print(f"Task 2, finding events (mean per article): recall {fmt(m['recall'].mean)}, "
          f"precision {fmt(m['precision'].mean)}, F1 {fmt(m['f1'].mean)}  "
          f"[context: {e.tp} hits, {e.fn} misses, {e.fp} extras]")
    print(f"Task 2, details of hits (mean per article): accuracy {fmt(m['accuracy'].mean)}, "
          f"exact rate {fmt(m['exact_rate'].mean)}")
    print(f"Task 2, articles: {s.all_found} of {s.gold_nonempty} with items fully found; "
          f"{s.both_empty} of {s.gold_empty} without items left empty")
    print(f"Reports written to {run_dir} (start with report.md)")


if __name__ == "__main__":
    main()
