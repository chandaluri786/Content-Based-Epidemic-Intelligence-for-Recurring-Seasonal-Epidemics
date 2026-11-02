"""Draw the fixed development sample D, used to compare few-shot example sets.

    python scripts/make_dev_sample.py [--size 200] [--seed 20261101]

Takes dev articles that have a gold record, stratified by labeler and by gold `useful`, so the
sample keeps the dev mix (about 28 percent useful). Writes one article id per line to
data/dev_sample_200.txt. Run it once and keep the file: D must stay identical across runs.
Articles in D are never used as few-shot examples.
"""

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flu_extractor import config  # noqa: E402
from flu_extractor.data_loading import DEV, load_articles, load_gold_labels  # noqa: E402


def allocate(sizes: dict, total: int) -> dict:
    """Split `total` across strata in proportion to their sizes (largest remainder)."""
    population = sum(sizes.values())
    exact = {key: total * size / population for key, size in sizes.items()}
    shares = {key: int(value) for key, value in exact.items()}
    by_remainder = sorted(exact, key=lambda key: exact[key] - shares[key], reverse=True)
    for key in by_remainder[: total - sum(shares.values())]:
        shares[key] += 1
    return shares


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261101)
    parser.add_argument("--out", type=Path, default=config.DEV_SAMPLE_PATH)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"{args.out} already exists. D must stay fixed; delete it only on purpose.")

    articles = load_articles(config.ARTICLES_PATH)
    gold = load_gold_labels(config.GOLD_LABELS_PATH)
    strata = defaultdict(list)
    for article_id, article in sorted(articles.items()):
        if article.split == DEV and article_id in gold:
            labeler = article.sources[0].split(":")[0]  # the set the article was first drawn for
            strata[(labeler, gold[article_id].useful)].append(article_id)

    generator = random.Random(args.seed)
    sample = []
    for key, size in sorted(allocate({k: len(v) for k, v in strata.items()}, args.size).items()):
        sample += generator.sample(strata[key], size)
        print(f"{key[0]:<8} useful={key[1]!s:<5} {size} of {len(strata[key])}")

    args.out.write_text(
        f"# Development sample D: {len(sample)} dev articles, seed {args.seed}. Do not edit.\n"
        + "\n".join(sorted(sample)) + "\n", encoding="utf-8")
    useful = sum(gold[a].useful for a in sample)
    print(f"wrote {args.out}: {len(sample)} articles, {useful} useful ({useful / len(sample):.0%})")


if __name__ == "__main__":
    main()
