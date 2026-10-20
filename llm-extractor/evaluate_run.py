"""Command-line tool: score a finished run against the human labels and write the reports.

Example:
    python evaluate_run.py results/run_20261018_150000
    python evaluate_run.py results/run_X --labels data/human_labels_jahnavi.json   # against another label set
The run is scored against the labels file it was made with (HUMAN_LABELS_PATH); scoring it against
another one needs --labels, so that never happens by accident. With --labels the reports are written
into a sub-folder named after that labels file, and the run's own reports are left alone.
City, state and country values are looked up online the first time (about 1 per second) and
remembered in data/place_lookups.json. Writes report.md, row_results.csv and item_comparison.csv into that folder.
"""

import argparse
from pathlib import Path

from flu_extractor import config
from flu_extractor.data_loading import load_articles, load_human_labels
from flu_extractor.evaluation import evaluate_run, read_run_records, read_run_settings, settings_mismatch
from flu_extractor.places import PlaceChecker
from flu_extractor.report import write_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path, help="run folder created by run_extraction.py")
    parser.add_argument("--offline", action="store_true",
                        help="do not look up place names online; use only the saved answers "
                             "(names never looked up before are reported as 'could not be checked').")
    parser.add_argument("--labels", type=Path,
                        help="score against this labels file instead of the run's own "
                             "(e.g. data/human_labels_jahnavi.json); reports go to a sub-folder")
    args = parser.parse_args()
    run_dir = args.run_dir

    saved = read_run_settings(run_dir) or {}
    if args.labels:
        labels_path, out_dir = args.labels.resolve(), run_dir / f"vs_{args.labels.stem}"
        out_dir.mkdir(exist_ok=True)
    else:
        labels_path, out_dir = config.HUMAN_LABELS_PATH, run_dir
        mismatch = settings_mismatch(saved or None, {"labels": labels_path.name}, names=("labels",))
        if mismatch:
            raise SystemExit(f"{run_dir}: {mismatch[0]}. Set HUMAN_LABELS_PATH to the run's labels, "
                             "or use --labels to score against another set on purpose.")
    run_info = {"system_prompt": saved.get("system_prompt", config.SYSTEM_PROMPT_PATH.name),
                "examples": saved.get("examples", config.EXAMPLES_PATH.name), "labels": labels_path.name}

    records = read_run_records(run_dir / "raw_results.jsonl")
    articles = load_articles(config.ARTICLES_PATH)
    labels = load_human_labels(labels_path)

    # Place names are looked up online once and remembered in data/place_lookups.json.
    place_checker = PlaceChecker(config.PLACE_CACHE_PATH, offline=args.offline)

    evaluation = evaluate_run(records, articles, labels, place_checker)
    write_report(evaluation, out_dir, run_info)

    counts = evaluation.usefulness.counts
    print(f"Scored {len(evaluation.rows_with_status('scored'))} of {len(evaluation.rows)} articles.")
    print(f"Usefulness: precision={counts.precision}, recall={counts.recall}, f1={counts.f1}")
    print(f"Reports written to {out_dir}")


if __name__ == "__main__":
    main()
