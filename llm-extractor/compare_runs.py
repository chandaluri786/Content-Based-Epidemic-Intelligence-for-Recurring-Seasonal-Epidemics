"""Command-line tool: put the headline scores of several evaluated runs side by side.

Used to compare settings (for example example-set sizes k = 4, 8, 12) and to summarise repeated runs of one setting (mean and range). With exactly two runs it also gives a
paired bootstrap interval for the difference (second minus first), resampling the articles both
runs scored, with the same seed as evaluate_run.py.

Example:
    python compare_runs.py results/run_A results/run_B

Each folder must have been scored with evaluate_run.py (it reads evaluation_summary.json and
article_metrics.csv).
"""

import argparse
import csv
import json
from pathlib import Path

from flu_extractor.evaluation import HEADLINE, POPULATIONS
from flu_extractor.metrics import bootstrap_indexes, interval

COLUMNS = (("useful_f1", "useful F1"), ("recall", "mean recall"), ("precision", "mean precision"), ("f1", "mean F1"),
           ("accuracy", "mean accuracy"), ("exact_rate", "mean exact rate"))


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def value(summary: dict, key: str) -> float | None:
    if key == "useful_f1":
        return summary["useful"]["f1"]
    return summary["metrics"][key]["mean"]


def read_articles(run_dir: Path) -> dict[str, dict]:
    with (run_dir / "article_metrics.csv").open(encoding="utf-8") as file:
        return {row["article_id"]: row for row in csv.DictReader(file)
                if row["status"] == "scored"}


def paired_difference(first: Path, second: Path) -> None:
    a, b = read_articles(first), read_articles(second)
    shared = sorted(set(a) & set(b))
    if not shared:
        print("\nNo scored articles in common; no paired comparison.")
        return

    def mean_f1(rows, indexes):
        values = [float(rows[shared[i]]["f1"]) for i in indexes if rows[shared[i]]["f1"] != ""]
        return sum(values) / len(values) if values else None

    samples = bootstrap_indexes(len(shared))
    everything = list(range(len(shared)))
    print(f"\nPaired comparison on {len(shared)} articles both runs scored ({second.name} minus {first.name}):")
    for name, statistic in (("mean F1", mean_f1),):
        def difference(indexes, statistic=statistic):
            x, y = statistic(a, indexes), statistic(b, indexes)
            return None if x is None or y is None else y - x
        ci = interval(difference, len(shared), samples)
        print(f"  {name}: {fmt(difference(everything))} (95% interval "
              f"{'n/a' if ci is None else f'{fmt(ci[0])} to {fmt(ci[1])}'})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dirs", type=Path, nargs="+", help="evaluated run folders")
    parser.add_argument("--population", default=HEADLINE, choices=tuple(POPULATIONS),
                        help=f"which articles to compare (default: {HEADLINE}, every scored article)")
    args = parser.parse_args()

    rows = []
    for run_dir in args.run_dirs:
        summary = json.loads((run_dir / "evaluation_summary.json").read_text(encoding="utf-8"))
        rows.append((run_dir.name, summary["settings"], summary["populations"][args.population]))

    print(f"| Run | k | Examples hash | Articles | {' | '.join(label for _, label in COLUMNS)} |")
    print("|---|---|---|---|" + "---|" * len(COLUMNS))
    for name, settings, summary in rows:
        print(f"| {name} | {settings.get('example_count')} | {(settings.get('examples_sha256') or '')[:8]} | "
              f"{summary['articles']} | " + " | ".join(fmt(value(summary, key)) for key, _ in COLUMNS) + " |")

    if len(rows) > 1:
        print()
        for key, label in COLUMNS:
            values = [v for *_, summary in rows if (v := value(summary, key)) is not None]
            if values:
                print(f"{label}: mean {fmt(sum(values) / len(values))}, range {fmt(min(values))} to {fmt(max(values))}")
    if len(rows) == 2:
        paired_difference(args.run_dirs[0], args.run_dirs[1])


if __name__ == "__main__":
    main()
