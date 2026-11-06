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
from flu_extractor.data_loading import load_articles, load_gold_labels, resolve_article_id
from flu_extractor.evaluation import SCORED, evaluate_run, read_run_records
from flu_extractor.duplicates import load_adjudication
from flu_extractor.field_scoring import score_pair
from flu_extractor.matching import MATCH_THRESHOLD, MATCHING_VERSION
from flu_extractor.normalization import ALL_FIELDS, applicable_fields, show
from flu_extractor.places import PlaceChecker


def print_evidence(label: str, item: dict | None) -> None:
    """Print every evidence quote of an item in full. Evidence is shown but never compared."""
    if item is None:
        return
    print(f"      {label} evidence ({len(item.get('evidence') or [])} quote(s), not compared):")
    for quote in item.get("evidence") or []:
        print(f"        - {quote!r}")


def print_item_pair(title: str, gold: dict | None, model: dict | None) -> None:
    """Print the item fields, gold and model next to each other, with the result of each field."""
    print(f"\n  {title}")
    results = {f.name: f.result for f in score_pair(gold, model).fields} if gold and model else {}
    fields = applicable_fields((gold or model).get("kind"))
    for name in ALL_FIELDS:
        if name not in fields:
            continue
        gold_text = show(gold.get(name)) if gold else "-"
        model_text = show(model.get(name)) if model else "-"
        print(f"      {name:<12} {results.get(name, ''):<8} gold: {gold_text:<32} model: {model_text}")
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
    parser.add_argument("--offline", action="store_true", help="do not look up place names online; use only the saved answers")
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
    evaluation = evaluate_run({article_id: records[article_id]}, articles, gold, place_checker,
                              load_adjudication(config.ADJUDICATION_PATH))
    result, article, record = evaluation.rows[0], articles[article_id], records[article_id]

    print(f"ARTICLE {article_id}   in {', '.join(article.sources)}   "
          f"scan_date {article.scan_date}")
    print(f"link: {article.link}")
    if args.show_article:
        print(f"\n--- article text ---\n{article.text}\n--- end of article ---")

    print(f"\nCALL: finish_reason={record['finish_reason']}  prompt_tokens={record['prompt_tokens']}  "
          f"completion_tokens={record['completion_tokens']}  seconds={record['seconds']}")
    print(f"STATUS: {result.status}")
    if result.status != SCORED:
        print("Not scored, because:", *result.problems, sep="\n  ")
        print(f"\nraw reply (first 1500 characters):\n{(record['raw_reply'] or '')[:1500]}")
        return

    print(f"\nUSEFULNESS   gold: {result.gold_useful}   model: {result.model_useful}   "
          f"-> {'CORRECT' if result.gold_useful == result.model_useful else 'WRONG'}")
    print(f"  model reason: {result.model_reason}")
    if args.reasoning:
        parsed = record["parsed"]
        print(f"\n  model summary: {parsed['summary']}")
        for step in parsed["reasoning"]:
            print(f"    {step}")

    print(f"\nHOW ITEMS ARE MATCHED ({MATCHING_VERSION})")
    print("  Places are first put in their agreed form (5.1: the English name in OpenStreetMap). Candidate pairs")
    print("  are in the same country and the same kind (or two count kinds with the same number).")
    print(f"  Similarity = share of the gold kind's fields that agree (= the hit's accuracy); pairs below {MATCH_THRESHOLD}")
    print("  are not allowed. Best partners first: the highest pair still available is locked, both items used up. Each field:")
    print("  match, wrong, missing (gold has a value, the model null) or extra (gold null, the model has a value).")

    o = result.outcome
    print(f"\nITEMS   gold: {len(result.gold_items)} (as annotated: {len(result.raw_gold_items)})   "
          f"model: {len(result.model_items)}   hits: {o.tp}   misses: {o.fn}   extras: {o.fp}   "
          f"exact: {o.exact_items}")
    for number, ((g, m, similarity), pair) in enumerate(zip(o.match.pairs, o.pair_scores), start=1):
        label = "EXACT" if pair.exact else f"MATCHED, wrong in: {', '.join(pair.wrong_fields)}"
        print_item_pair(f"HIT #{number} (similarity {similarity:.2f}): {label}", o.gold_items[g], o.model_items[m])
    rejected = {g: (m, s) for g, m, s in o.match.rejected}
    for g in o.match.unmatched_gold:
        note = ""
        if g in rejected:
            m, score = rejected[g]
            note = f"; closest model item #{m + 1} at {score:.2f} ({'below the threshold' if score < MATCH_THRESHOLD else 'taken by another gold item'})"
        print_item_pair(f"MISS (gold item #{g + 1}, no model counterpart{note})", o.gold_items[g], None)
    for m in o.match.unmatched_model:
        label = o.duplicate_extras.get(m)
        print_item_pair(f"EXTRA (model item #{m + 1}{', ' + label if label else ''})", None, o.model_items[m])
    if result.gold_reviews:
        print("\nGOLD DUPLICATE CANDIDATES")
        for review in result.gold_reviews:
            print(f"  items {review['item_indexes']} ({review['category']}): {review['decision']} {review['reason']}")
    print(f"\nARTICLE SCORES   recall {o.recall}   precision {o.precision}   F1 {o.f1}   accuracy {o.attribute_accuracy}   "
          f"exact rate {o.exact_rate}")

    print("\nRULE CHECKS (evidence copied from the article, places real, dates recent, fields by kind, ...)")
    print("  " + ("none violated" if not result.violations else "\n  ".join(result.violations)))


if __name__ == "__main__":
    main()
