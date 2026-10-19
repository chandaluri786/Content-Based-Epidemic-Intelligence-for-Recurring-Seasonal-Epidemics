"""Command-line tool: show one article's human answer and model reply side by side, field by field.

Use it to see exactly why an item matched or did not. Nothing is abbreviated.

Examples (from the llm-extractor folder, with the virtual environment active):
    python inspect_row.py results/run_20261018_165443 6
    python inspect_row.py results/run_20261018_165443 6 --article    # also print the article text
    python inspect_row.py results/run_20261018_165443 6 --offline     # do not look up places online
"""

import argparse
from pathlib import Path

from flu_extractor import config
from flu_extractor.data_loading import load_articles, load_human_labels
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


def print_item_pair(title: str, human: dict | None, model: dict | None) -> None:
    """Print all item fields, human and model next to each other, with a same/DIFFERENT flag."""
    print(f"\n  {title}")
    different = set(differing_fields(human, model)) if human and model else set()
    for name in EXACT_KEY_FIELDS:
        flag = ""
        if human and model:
            flag = "DIFFERENT" if name in different else "same"
        human_text = show(human[name]) if human else "-"
        model_text = show(model[name]) if model else "-"
        print(f"      {name:<13} {flag:<10} human: {human_text:<32} model: {model_text}")
    print_evidence("human", human)
    print_evidence("model", model)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path, help="run folder created by run_extraction.py")
    parser.add_argument("row", type=int, help="row number of the article")
    parser.add_argument("--article", action="store_true", help="also print the article text")
    parser.add_argument("--offline", action="store_true", help="do not look up place names online")
    args = parser.parse_args()

    records = read_run_records(args.run_dir / "raw_results.jsonl")
    if args.row not in records:
        raise SystemExit(f"Row {args.row} is not in {args.run_dir}. Rows there: {sorted(records)[:20]}")
    articles = load_articles(config.ARTICLES_PATH)
    labels = load_human_labels(config.HUMAN_LABELS_PATH)

    place_checker = PlaceChecker(config.PLACE_CACHE_PATH, offline=args.offline)
    evaluation = evaluate_run({args.row: records[args.row]}, articles, labels, place_checker)
    if not evaluation.rows:
        raise SystemExit(f"Row {args.row} has no human label, so there is nothing to compare with.")
    result, article, record = evaluation.rows[0], articles[args.row], records[args.row]

    print(f"ROW {article.row}   article_id {article.article_id}   scan_date {article.scan_date}")
    print(f"link: {article.link}")
    if args.article:
        print(f"\n--- article text ---\n{article.text}\n--- end of article ---")

    print(f"\nCALL: finish_reason={record['finish_reason']}  prompt_tokens={record['prompt_tokens']}  "
          f"completion_tokens={record['completion_tokens']}  seconds={record['seconds']}")
    print(f"STATUS: {result.status}")
    if result.status != SCORED:
        print("Not scored, because:", *result.problems, sep="\n  ")
        print(f"\nraw reply (first 1500 characters):\n{(record['raw_reply'] or '')[:1500]}")
        return

    print(f"\nUSEFULNESS   human: {result.human_useful}   model: {result.model_useful}   "
          f"-> {'CORRECT' if result.human_useful == result.model_useful else 'WRONG'}")
    print(f"  model reason: {result.model_reason}   (borderline: {result.borderline})")

    print("\nHOW ITEMS ARE MATCHED")
    print("  A model item is an EXACT match for a human item when all of these fields agree:")
    print("    " + ", ".join(EXACT_KEY_FIELDS))
    print("  Upper/lower case and repeated spaces are ignored; null equals null; evidence is not compared.")
    print("  Each human item can be matched once. Leftovers are then paired by kind, strain and place")
    print("  only to show which fields differ.")

    exact, near = result.exact_match, result.near_match
    print(f"\nITEMS   human: {len(result.human_items)}   model: {len(result.model_items)}   "
          f"exact matches: {len(exact.matched)}   missing from model: {len(near.missed)}   "
          f"extra from model: {len(near.extra)}   same kind/place but not exact: {len(near.matched)}")
    for number, (human, model) in enumerate(exact.matched, start=1):
        print_item_pair(f"EXACT MATCH #{number}", human, model)
    for number, (human, model) in enumerate(near.matched, start=1):
        print_item_pair(f"NOT EXACT #{number} (same kind and place; differs in: "
                        f"{', '.join(differing_fields(human, model))})", human, model)
    for number, human in enumerate(near.missed, start=1):
        print_item_pair(f"MISSING FROM MODEL #{number} (human wrote it; no model item pairs with it)", human, None)
    for number, model in enumerate(near.extra, start=1):
        print_item_pair(f"EXTRA FROM MODEL #{number} (model wrote it; no human item pairs with it)", None, model)
    print(f"\nITEM SET OUTCOME: {classify_item_set(exact)}")

    print("\nRULE CHECKS (evidence copied from the article, places real, dates in order, ...)")
    print("  " + ("none violated" if not result.violations else "\n  ".join(result.violations)))


if __name__ == "__main__":
    main()
