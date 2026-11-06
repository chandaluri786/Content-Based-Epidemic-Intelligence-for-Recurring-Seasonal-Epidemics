"""Charts of the per-article task 2 results, written as PNG files into the run folder.

  plot_article_counts.png    hits, misses and extras of every article that has items on either side
  plot_article_metrics.png   how the per-article recall, precision, F1, accuracy and exact rate spread
  plot_field_accuracy.png    mean per-article accuracy of each field (which detail goes wrong)
  plot_article_buckets.png   how many articles fall in each outcome bucket

The values behind every chart are in article_metrics.csv (one row per article), so nothing is shown
by colour alone. Colours: the first three slots of the validated categorical palette (checked for
colour-vision deficiency on all pairs); single-series charts use slot 1 only.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # files only, no window
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

SURFACE, TEXT, TEXT_SECONDARY, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
HITS, MISSES, EXTRAS = "#2a78d6", "#eb6834", "#1baf7a"   # categorical slots 1-3
SINGLE = HITS
METRICS = (("recall", "Recall"), ("precision", "Precision"), ("f1", "F1"),
           ("accuracy", "Accuracy"), ("exact_rate", "Exact rate"))


def _style(ax, grid_axis: str = "y") -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    (ax.yaxis if grid_axis == "y" else ax.xaxis).set_major_locator(MaxNLocator(integer=True))


def _figure(width: float, height: float, *grid):
    fig, axes = plt.subplots(*grid, figsize=(width, height)) if grid else plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(SURFACE)
    return fig, axes


def _save(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_article_counts(outcomes: list, path: Path) -> None:
    """Stacked bars, one per article with items on either side: hits, misses, extras."""
    data = sorted(((o.tp, o.fn, o.fp, len(o.gold_items)) for o in outcomes if o.gold_items or o.model_items),
                  key=lambda row: (-row[3], -row[0], row[1] + row[2]))
    fig, ax = _figure(max(6.0, min(16.0, 0.12 * len(data) + 4)), 4.2)
    _style(ax)
    x = range(len(data))
    hits, misses, extras = ([row[i] for row in data] for i in range(3))
    gap = 0.6 if len(data) <= 80 else 0.0   # a thin surface gap between segments when bars are wide enough
    ax.bar(x, hits, color=HITS, label="Hits", edgecolor=SURFACE, linewidth=gap)
    ax.bar(x, misses, bottom=hits, color=MISSES, label="Misses", edgecolor=SURFACE, linewidth=gap)
    ax.bar(x, extras, bottom=[h + m for h, m in zip(hits, misses)], color=EXTRAS, label="Extras",
           edgecolor=SURFACE, linewidth=gap)
    ax.set_xticks([])
    ax.set_xlabel(f"Articles with items on either side ({len(data)}), most gold items first", color=TEXT_SECONDARY)
    ax.set_ylabel("Items", color=TEXT_SECONDARY)
    ax.set_title("Hits, misses and extras per article", color=TEXT, loc="left", fontsize=11)
    ax.legend(frameon=False, labelcolor=TEXT, fontsize=9, loc="upper right")
    _save(fig, path)


def plot_article_metrics(summary, outcomes: list, path: Path) -> None:
    """One histogram per metric: how many articles have each value, with the mean marked."""
    from flu_extractor.evaluation import ARTICLE_METRICS  # here, to avoid a circular import
    fig, axes = _figure(15.0, 3.2, 1, len(METRICS))
    bins = [i / 20 for i in range(21)]
    for ax, (name, title) in zip(axes, METRICS):
        _style(ax)
        values = [v for v in (ARTICLE_METRICS[name](o) for o in outcomes) if v is not None]
        d = summary.metrics[name]
        if values:
            ax.hist(values, bins=bins, color=SINGLE, edgecolor=SURFACE, linewidth=0.6)
            ax.axvline(d.mean, color=TEXT_SECONDARY, linestyle="--", linewidth=1)
        ax.set_xlim(0, 1.0)
        ax.set_title(f"{title}\nmean {_pct(d.mean)}, at 1: {_pct(d.share_one)}, n = {d.articles}",
                     color=TEXT, loc="left", fontsize=10)
        ax.set_xlabel("Per-article value", color=TEXT_SECONDARY, fontsize=9)
    axes[0].set_ylabel("Articles", color=TEXT_SECONDARY)
    _save(fig, path)


def plot_field_accuracy(summary, path: Path) -> None:
    """Horizontal bars: mean per-article accuracy of each field, lowest first."""
    fields = sorted(((name, d) for name, d in summary.fields.items() if d.articles), key=lambda nd: nd[1].mean)
    fig, ax = _figure(7.0, 0.38 * len(fields) + 1.2)
    _style(ax, grid_axis="x")
    names = [name for name, _ in fields]
    means = [d.mean for _, d in fields]
    ax.barh(names, means, color=SINGLE, height=0.6)
    for y, (mean, (_, d)) in enumerate(zip(means, fields)):
        ax.text(min(mean, 1.0) + 0.01, y, f"{_pct(mean)}  (n = {d.articles})", va="center", color=TEXT, fontsize=8)
    ax.set_xlim(0, 1.25)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.tick_params(axis="y", colors=TEXT)
    ax.set_xlabel("Mean per-article field accuracy (articles with a hit)", color=TEXT_SECONDARY)
    ax.set_title("Which detail goes wrong", color=TEXT, loc="left", fontsize=11)
    _save(fig, path)


def plot_article_buckets(summary, path: Path) -> None:
    """Horizontal bars: number of articles in each outcome bucket."""
    buckets = [
        ("Gold has items: all found, no extras", summary.all_found, summary.gold_nonempty),
        ("Gold has items: some found", summary.some_found, summary.gold_nonempty),
        ("Gold has items: nothing found", summary.none_found, summary.gold_nonempty),
        ("Gold has no items: left empty", summary.both_empty, summary.gold_empty),
        ("Gold has no items: false items", summary.false_items_on_empty, summary.gold_empty),
    ]
    fig, ax = _figure(8.0, 3.2)
    _style(ax, grid_axis="x")
    labels = [label for label, _, _ in buckets][::-1]
    counts = [count for _, count, _ in buckets][::-1]
    totals = [total for _, _, total in buckets][::-1]
    ax.barh(labels, counts, color=SINGLE, height=0.6)
    top = max(counts) if any(counts) else 1
    for y, (count, total) in enumerate(zip(counts, totals)):
        share = f" ({_pct(count / total)})" if total else ""
        ax.text(count + top * 0.01, y, f"{count}{share}", va="center", color=TEXT, fontsize=8)
    ax.set_xlim(0, top * 1.3)
    ax.tick_params(axis="y", colors=TEXT)
    ax.set_xlabel("Articles", color=TEXT_SECONDARY)
    ax.set_title("Article outcomes (each article in one bucket)", color=TEXT, loc="left", fontsize=11)
    _save(fig, path)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def write_plots(summary, outcomes: list, run_dir: Path) -> None:
    """Write the four charts for one set of articles (the headline set) into the run folder."""
    plot_article_counts(outcomes, run_dir / "plot_article_counts.png")
    plot_article_metrics(summary, outcomes, run_dir / "plot_article_metrics.png")
    plot_field_accuracy(summary, run_dir / "plot_field_accuracy.png")
    plot_article_buckets(summary, run_dir / "plot_article_buckets.png")
