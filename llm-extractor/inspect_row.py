"""Command-line tool: show one article's gold answer and model reply side by side, field by field.

Use it to see exactly why an item matched or did not. Nothing is abbreviated.

Examples (from the llm-extractor folder, with the virtual environment active):
    python inspect_row.py results/run_20261101_165443 Jahnavi:6
    python inspect_row.py results/run_20261101_165443 20161230170000-2179 --article   # also print the text
    python inspect_row.py results/run_20261101_165443 Jahnavi:6 --reasoning           # also print the steps
    python inspect_row.py results/run_20261101_165443 Jahnavi:6 --offline             # no place lookups
"""

import argparse
import sys
from pathlib import Path

from flu_extractor import config
from flu_extractor.data_loading import load_articles, load_gold_labels, load_human_useful, resolve_article_id
from flu_extractor.evaluation import SCORED, evaluate_run, read_run_records
from flu_extractor.metrics import EXACT_KEY_FIELDS, classify_item_set, differing_fields
from flu_extractor.places import PlaceChecker


def show(value) -> str:
    """How a field value is printed: null shows as (null) so it is not confused with the word None."""
    return "(null)" if value is None else str(value)


def print_evidence(label: str, item: dict | None) -> None:
    """Print every evidence quote of an item in full. Evidence is shown but never compared."""
    if item is None:
        return
    print(f"      {label} evidence ({len(item['evidence'])} quote(s), not compared):")
    for quote in item["evidence"]:
        print(f"        - {quote!r}")


def print_item_pair(title: str, gold: dict | None, model: dict | None) -> None:
    """Print all item fields, gold and model next to each other, with a same/DIFFERENT flag."""
    print(f"\n  {title}")
    different = set(differing_fields(gold, model)) if gold and model else set()
    for name in EXACT_KEY_FIELDS:
        flag = ""
        if gold and model:
            flag = "DIFFERENT" if name in different else "same"
        gold_text = show(gold[name]) if gold else "-"
        model_text = show(model[name]) if model else "-"
        print(f"      {name:<13} {flag:<10} gold: {gold_text:<32} model: {model_text}")
    print_evidence("gold", gold)
    print_evidence("model", model)


def main() -> None:
    # Article and model text can hold characters a Windows console cannot show ("→", curly quotes);
    # show a placeholder for those instead of crashing.
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path, help="run folder created by run_extraction.py")
    parser.add_argument("article", help="article id, or a set position such as Jahnavi:6")
    parser.add_argument("--article", dest="show_article", action="store_true", help="also print the article text")
    parser.add_argument("--reasoning", action="store_true", help="also print the model's summary and reasoning steps")
    parser.add_argument("--offline", action="store_true", help="do not look up place names online")
    args = parser.parse_args()

    articles = load_articles(config.ARTICLES_PATH)
    article_id = resolve_article_id(args.article, articles)
    records = read_run_records(args.run_dir / "raw_results.jsonl")
    if article_id not in records:
        raise SystemExit(f"{article_id} is not in {args.run_dir}. Articles there: {sorted(records)[:20]}")
    gold = load_gold_labels(config.GOLD_LABELS_PATH)
    if article_id not in gold:
        raise SystemExit(f"{article_id} has no gold record, so there is nothing to compare with.")

    place_checker = PlaceChecker(config.PLACE_CACHE_PATH, offline=args.offline)
    evaluation = evaluate_run({article_id: records[article_id]}, articles, gold,
                              load_human_useful(config.HUMAN_LABELS_PATH), place_checker)
    result, article, record = evaluation.rows[0], articles[article_id], records[article_id]

    print(f"ARTICLE {article_id}   in {', '.join(article.sources)}   split {article.split}   "
          f"scan_date {article.scan_date}")
    print(f"link: {article.link}")
    if args.show_article:
        print(f"\n--- article text ---\n{article.text}\n--- end of article ---")

    if result.gated:
        print("\nCALL: none - the article fails the keyword gate, so the Rule 1 reply was written by code")
    else:
        print(f"\nCALL: finish_reason={record['finish_reason']}  prompt_tokens={record['prompt_tokens']}  "
              f"completion_tokens={record['completion_tokens']}  seconds={record['seconds']}")
    print(f"STATUS: {result.status}")
    if result.status != SCORED:
        print("Not scored, because:", *result.problems, sep="\n  ")
        print(f"\nraw reply (first 1500 characters):\n{(record['raw_reply'] or '')[:1500]}")
        return

    print(f"\nUSEFULNESS   gold: {result.gold_useful}   model: {result.model_useful}   "
          f"-> {'CORRECT' if result.gold_useful == result.model_useful else 'WRONG'}   "
          f"(human label: {show(result.human_useful)})")
    print(f"  model reason: {result.model_reason}")
    if args.reasoning:
        parsed = record["parsed"]
        print(f"\n  model summary: {parsed['summary']}")
        for step in parsed["reasoning"]:
            print(f"    {step}")

    print("\nHOW ITEMS ARE MATCHED")
    print("  A model item is an EXACT match for a gold item when all of these fields agree:")
    print("    " + ", ".join(EXACT_KEY_FIELDS))
    print("  Upper/lower case and repeated spaces are ignored; null equals null; evidence is not compared.")
    print("  Each gold item can be matched once. Leftovers are then paired by kind, strain and place")
    print("  only to show which fields differ.")

    exact, near = result.exact_match, result.near_match
    print(f"\nITEMS   gold: {len(result.gold_items)}   model: {len(result.model_items)}   "
          f"exact matches: {len(exact.matched)}   missing from model: {len(near.missed)}   "
          f"extra from model: {len(near.extra)}   same kind/place but not exact: {len(near.matched)}")
    for number, (gold_item, model_item) in enumerate(exact.matched, start=1):
        print_item_pair(f"EXACT MATCH #{number}", gold_item, model_item)
    for number, (gold_item, model_item) in enumerate(near.matched, start=1):
        print_item_pair(f"NOT EXACT #{number} (same kind and place; differs in: "
                        f"{', '.join(differing_fields(gold_item, model_item))})", gold_item, model_item)
    for number, gold_item in enumerate(near.missed, start=1):
        print_item_pair(f"MISSING FROM MODEL #{number} (in gold; no model item pairs with it)", gold_item, None)
    for number, model_item in enumerate(near.extra, start=1):
        print_item_pair(f"EXTRA FROM MODEL #{number} (model wrote it; no gold item pairs with it)", None, model_item)
    print(f"\nITEM SET OUTCOME: {classify_item_set(exact)}")

    print("\nRULE CHECKS (evidence copied from the article, places real, dates recent, fields by kind, ...)")
    print("  " + ("none violated" if not result.violations else "\n  ".join(result.violations)))


if __name__ == "__main__":
    main()
