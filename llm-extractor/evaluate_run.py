"""Command-line tool: score a finished run against the gold labels and write the reports.

Example:
    python evaluate_run.py results/run_20261101_150000
City, state and country values are looked up online the first time (about 1 per second) and
remembered in data/place_lookups.json. Writes report.md, scores.json, row_results.csv and
item_comparison.csv into that folder.
"""

import argparse
from pathlib import Path

from flu_extractor import config
from flu_extractor.data_loading import load_articles, load_gold_labels, load_human_useful
from flu_extractor.evaluation import SCORED, evaluate_run, read_run_records
from flu_extractor.places import PlaceChecker
from flu_extractor.report import write_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path, help="run folder created by run_extraction.py")
    parser.add_argument("--offline", action="store_true",
                        help="do not look up place names online; use only the saved answers "
                             "(names never looked up before are reported as 'could not be checked').")
    args = parser.parse_args()
    run_dir = args.run_dir

    records = read_run_records(run_dir / "raw_results.jsonl")
    articles = load_articles(config.ARTICLES_PATH)
    gold = load_gold_labels(config.GOLD_LABELS_PATH)
    human = load_human_useful(config.HUMAN_LABELS_PATH)

    # Place names are looked up online once and remembered in data/place_lookups.json.
    place_checker = PlaceChecker(config.PLACE_CACHE_PATH, offline=args.offline)

    evaluation = evaluate_run(records, articles, gold, human, place_checker)
    write_report(evaluation, run_dir)

    counts = evaluation.usefulness.counts
    exact = evaluation.model_articles.exact_items.overall()
    print(f"Scored {len(evaluation.rows_with_status(SCORED))} of {len(evaluation.rows)} articles "
          f"({len(records) - len(evaluation.rows)} in the run have no gold record).")
    print(f"Usefulness (reached the model): precision={counts.precision}, recall={counts.recall}, f1={counts.f1}")
    print(f"Exact item F1 (reached the model): {exact.f1}")
    print(f"Reports written to {run_dir}")


if __name__ == "__main__":
    main()
