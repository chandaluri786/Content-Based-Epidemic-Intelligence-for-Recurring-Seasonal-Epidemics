"""Command-line tool: put the headline scores of several evaluated runs side by side.

Used to compare example-set sizes (k = 0, 4, 8, 12) on the development sample D, and to
summarise the three runs on the test set (mean and range).

Example:
    python compare_runs.py results/run_A results/run_B results/run_C

Each folder must have been scored with evaluate_run.py (it reads scores.json and run_config.json).
"""

import argparse
import json
from pathlib import Path

# Per-article scores (averaged over articles) first: they are the headline. The pooled item F1
# (all items of all articles together) follows for reference.
COLUMNS = ("useful_precision", "useful_recall", "useful_f1", "article_exact_f1", "article_soft_f1",
           "exact_item_f1", "weekly_item_f1")


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dirs", type=Path, nargs="+", help="evaluated run folders")
    parser.add_argument("--variant", default="reached_model",
                        choices=("reached_model", "all_articles", "without_inactive"),
                        help="which set of scores to compare (default: articles that reached the model)")
    args = parser.parse_args()

    rows = []
    for run_dir in args.run_dirs:
        scores = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))[args.variant]
        run_config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
        rows.append((run_dir.name, run_config.get("example_count"), run_config.get("examples_sha256", "")[:8],
                     scores))

    print(f"| Run | k | Examples hash | Articles | {' | '.join(COLUMNS)} |")
    print("|---|---|---|---|" + "---|" * len(COLUMNS))
    for name, k, digest, scores in rows:
        print(f"| {name} | {k} | {digest} | {scores['articles']} | "
              + " | ".join(_fmt(scores.get(column)) for column in COLUMNS) + " |")

    if len(rows) > 1:
        print()
        for column in COLUMNS:
            values = [scores.get(column) for *_, scores in rows if scores.get(column) is not None]
            if values:
                print(f"{column}: mean {_fmt(sum(values) / len(values))}, "
                      f"range {_fmt(min(values))} to {_fmt(max(values))}")


if __name__ == "__main__":
    main()
