"""Choose few-shot example candidates from the chain-of-thought v2 records.

    python scripts/select_examples.py [--k 8] [--records-dir DIR] [--hard-runs RUN_DIR ...]

Steps:
  1. Read the chain-of-thought v2 record files in data/chain_of_thought/. They form one pool.
  2. Build the candidate pool: leave out every article labelled in more than one set (the 40
     double-labelled articles and the Thanya 1-40 repeats), articles that never mention flu (Rule 1 only),
     articles over 6,000 characters (10,000 for a `hard_case` record), replies over 5,000
     characters, garbled text, and inactive-only records except for the food-link slot.
  3. Tag each record with the slots below (SLOTS), from its `rules_used` and its items, and give
     it a hardness: +2 for a `hard_case` note (a judgement call the labeler recorded), plus the
     share of earlier runs (--hard-runs) in which the model got the article wrong (wrong `useful`,
     or per-article partial-credit F1 under 50%).
  4. Pick 12 examples greedily, nested (the first 4 inside the first 8, inside all 12): each pick
     adds the most new slots, then hardness, rarely used rules, new countries and new kinds, minus
     a length penalty. Every stage keeps the labelers balanced and about a third of examples not
     useful.

Writes the one example set the prompt uses, prompts/examples_<PROMPT_VERSION>.json (the first k
picks, default 8), and few_shot_selection.md (the review sheet: all 12 picks in order, coverage at
k = 4, 8, 12, and up to 3 alternates per slot). The set is checked with flu_extractor/data_checks.py
(reply format, exact evidence, "How to work" steps) before it is written.
"""

import argparse
import collections
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flu_extractor import config
from flu_extractor.data_loading import read_label_records  # noqa: E402
from flu_extractor.data_checks import check_examples  # noqa: E402

LABELERS = ("Jahnavi", "Aditya", "Manoj", "Thanya")  # the labeling sets; those without a record file are skipped
MAX_ARTICLE_CHARS, MAX_REPLY_CHARS = 6000, 5000
MAX_HARD_CASE_ARTICLE_CHARS = 10000  # a hard_case record may be longer: it is favoured on purpose
# Weight of hardness in a pick (one new slot is worth 10). A hard_case (hardness 2) is worth more
# than one new slot; an article the model got wrong in every earlier run (hardness 1) a little less.
HARDNESS_WEIGHT = 6
GARBLED_MARKERS = ("â€", "Ã", "�")
COUNT_KINDS = {"cases", "hospitalized", "deaths"}
SLOTS = {
    1: ("Flu named, but no current activity", "1.2, 9.5"),
    2: ("Flu in animals only", "1.3"),
    3: ("Past or forecast", "4.1, 4.7, 9.3.8"),
    4: ("Food link fallback", "1.3, 9.7"),
    5: ("Stages for one person", "2.4, 4.3"),
    6: ("Overlapping counts", "G4, G5"),
    7: ("Count and trend together", "2.3, 9.3"),
    8: ("Fallback present, per place", "9.3.5, 9.7"),
    9: ("Trend with a strain", "9.6"),
    10: ("Place from context", "5.3.6, 5.4, 5.5"),
    11: ("Relative dates", "4.3-4.6"),
    12: ("Subset vs region, suspected", "6.3, 7.2"),
}
# (k, most examples from one labeler, (fewest, most) not-useful examples) at each nested stage.
STAGES = ((4, 2, (1, 2)), (8, 3, (3, 3)), (12, 4, (4, 4)))


def answer(record: dict) -> dict:
    """The assistant turn: the record's reply in the key order the prompt asks for ("Your reply")."""
    output = record["output"]
    return {"summary": record["summary"], "reasoning": record["reasoning"], "useful": output["useful"],
            "reason": output["reason"], "items": output["items"]}


def slots_of(record: dict) -> set[int]:
    """The slots (see SLOTS) that a record demonstrates, from its rules and items."""
    rules, items, useful = set(record["rules_used"]), record["output"]["items"], record["output"]["useful"]
    counts = [i for i in items if i["kind"] in COUNT_KINDS]
    trends = [i for i in items if i["kind"] == "trend"]
    place = lambda i: (i["city"], i["state"], i["country"])  # noqa: E731
    found = set()
    if not useful and "1.2" in rules and "1.3" not in rules: found.add(1)
    if not useful and "1.3" in rules: found.add(2)
    if not useful and rules & {"4.7", "4.1", "9.3.8"}: found.add(3)
    if items and all(i["words"] == "inactive" for i in items) and "1.3" in rules: found.add(4)
    if "2.4" in rules and len({i["kind"] for i in counts}) >= 2: found.add(5)
    if rules & {"G4", "G5"} and len(counts) >= 2: found.add(6)
    if counts and any(i["words"] not in (None, "inactive") for i in trends): found.add(7)
    if "9.7" in rules and len({place(i) for i in trends if i["words"] == "present"}) >= 2: found.add(8)
    if "9.6" in rules and any(i["strain"] for i in trends): found.add(9)
    if useful and rules & {"5.3.2", "5.3.3", "5.3.4", "5.3.5", "5.3.6", "5.4"}: found.add(10)
    if useful and rules & {"4.4", "4.5", "4.6", "4.3.3", "4.3.4"}: found.add(11)
    if any(i["count_type"] == "cumulative_subset" or i["status"] == "suspected" for i in counts): found.add(12)
    return found


def model_misses(run_dirs: list[Path]) -> dict[str, list[str]]:
    """Articles the model got wrong in earlier evaluated runs: {article_id: ["run: why", ...]}."""
    misses: dict[str, list[str]] = collections.defaultdict(list)
    for run_dir in run_dirs:
        with (run_dir / "article_metrics.csv").open(encoding="utf-8") as file:   # written by evaluate_run.py
            for row in csv.DictReader(file):
                if row["status"] != "scored":
                    continue
                useful_wrong = row["gold_useful"] != row["model_useful"]
                score = row.get("f1")
                if useful_wrong:
                    misses[row["article_id"]].append(f"{run_dir.name}: useful wrong")
                elif score and float(score) < 0.5:
                    misses[row["article_id"]].append(f"{run_dir.name}: items under 50%")
    return misses


def build_pool(records_dir: Path, hard_runs: list[Path] = ()) -> tuple[list[dict], collections.Counter]:
    articles = {a["article_id"]: a for a in json.loads(config.ARTICLES_PATH.read_text(encoding="utf-8"))}
    misses = model_misses(list(hard_runs))
    records, copies = {}, collections.Counter()
    for name in LABELERS:
        path = records_dir / f"{name}{config.RECORDS_SUFFIX}"
        if not path.exists():
            continue
        for record in read_label_records(path):
            copies[record["article_id"]] += 1
            records.setdefault(record["article_id"], (name, record))  # one copy per article

    pool, excluded = [], collections.Counter()
    for article_id, (name, record) in records.items():
        if article_id not in articles:  # removed from data/ for being in more than one labeling set
            excluded["in more than one labeling set"] += 1
            continue
        article, reply = articles[article_id], answer(record)
        text, items = article["article"], record["output"]["items"]
        slots = slots_of(record)
        hard_case = bool(record.get("hard_case"))
        max_chars = MAX_HARD_CASE_ARTICLE_CHARS if hard_case else MAX_ARTICLE_CHARS
        reasons = [reason for reason, applies in (
            # Never an article labelled in more than one set: the 40 double-labelled dev articles,
            # and the dev articles repeated as Thanya rows 1-40.
            ("in more than one labeling set", copies[article_id] > 1 or len(article["sources"]) > 1),
            ("never mentions flu (Rule 1 only)", record.get("rules_used") == ["Rule 1"]),
            (f"article over {MAX_ARTICLE_CHARS} characters ({MAX_HARD_CASE_ARTICLE_CHARS} for hard_case)",
             len(text) > max_chars),
            (f"reply over {MAX_REPLY_CHARS} characters",
             len(json.dumps(reply, ensure_ascii=False)) > MAX_REPLY_CHARS),
            ("garbled text", sum(text.count(m) for m in GARBLED_MARKERS) >= 3),
            ("inactive-only outside the food slot",
             bool(items) and all(i["words"] == "inactive" for i in items) and 4 not in slots),
        ) if applies]
        if reasons:
            excluded[reasons[0]] += 1
            continue
        pool.append({
            "article_id": article_id, "source": f"{name}:{record['source_rows'][0]['row']}", "labeler": name,
            "useful": record["output"]["useful"], "slots": sorted(slots), "rules": record["rules_used"],
            "kinds": sorted({i["kind"] for i in items}), "countries": sorted({i["country"] for i in items}),
            "chars": len(text) + len(json.dumps(reply, ensure_ascii=False)),
            "hardness": 2 * hard_case + (len(misses[article_id]) / len(hard_runs) if hard_runs else 0.0),
            "hard_reasons": (["hard_case: " + record["hard_case"][:80]] if hard_case else []) + misses[article_id],
            "example": {"article_id": article_id, "source": f"{name}:{record['source_rows'][0]['row']}",
                        "slots": sorted(slots), "scan_date": article["scan_date"], "link": article["link"],
                        "article": text, "answer": reply},
        })
    return pool, excluded


def select(pool: list[dict]) -> list[dict]:
    """Greedy nested selection; see the module docstring."""
    frequency = collections.Counter(rule for c in pool for rule in c["rules"])
    chosen, slots, rules, countries, kinds = [], set(), set(), set(), set()

    def gain(c: dict) -> float:
        value = 10 * len(set(c["slots"]) - slots) + HARDNESS_WEIGHT * c["hardness"]
        value += sum(1 / math.sqrt(frequency[r]) for r in set(c["rules"]) - rules)
        value += 0.5 * len(set(c["countries"]) - countries) + 0.5 * len(set(c["kinds"]) - kinds)
        return value - c["chars"] / 4 / 1000  # about 1 point per 1,000 tokens

    for k, cap, (fewest, most) in STAGES:
        while len(chosen) < k:
            left = k - len(chosen)
            not_useful = sum(not c["useful"] for c in chosen)
            per_labeler = collections.Counter(c["labeler"] for c in chosen)
            # Every stage spans all the sets in the pool: once the picks left are only enough for
            # the labelers still missing, the next pick must come from one of them.
            missing = [n for n in sorted({c["labeler"] for c in pool}) if not per_labeler[n]]

            def allowed(c: dict) -> bool:
                after = not_useful + (not c["useful"])
                return (c not in chosen and per_labeler[c["labeler"]] < cap
                        and (len(missing) < left or c["labeler"] in missing)
                        and after <= most and after + left - 1 >= fewest)

            best = max((c for c in pool if allowed(c)), key=gain)
            chosen.append(best)
            slots |= set(best["slots"]); rules |= set(best["rules"])
            countries |= set(best["countries"]); kinds |= set(best["kinds"])
    return chosen


def prompt_order(examples: list[dict]) -> list[dict]:
    """Spread the not-useful examples through the list and end on one, so the last turn does not push
    the model toward items."""
    not_useful = [e for e in examples if not e["useful"]]
    useful = [e for e in examples if e["useful"]]
    n, m = len(examples), len(not_useful)
    slots_for_not_useful = {round((i + 1) * n / m) - 1 for i in range(m)} if m else set()
    return [not_useful.pop(0) if position in slots_for_not_useful else useful.pop(0) for position in range(n)]


def review_sheet(chosen: list[dict], pool: list[dict], excluded: collections.Counter) -> str:
    frequency = collections.Counter(rule for c in pool for rule in c["rules"])
    lines = [
        f"# Few-shot example candidates (prompt {config.PROMPT_VERSION})",
        "",
        "Written by `scripts/select_examples.py`. "
        f"The chosen set is the active `prompts/examples_{config.PROMPT_VERSION}.json`. "
        "Picks favour hard cases: a `hard_case` note and articles the model got wrong in earlier runs.",
        "",
        f"Pool: {len(pool)} labelled records after exclusions "
        f"({', '.join(f'{reason}: {count}' for reason, count in excluded.most_common())}).",
        "",
        "## Coverage by size",
        "",
        "| k | Slots covered | Rules covered | Not useful | Labelers | Approx. extra tokens per call |",
        "|---|---|---|---|---|---|",
    ]
    for k, _, _ in STAGES:
        part = chosen[:k]
        slots = set().union(*(set(c["slots"]) for c in part))
        rules = set().union(*(set(c["rules"]) for c in part))
        labelers = collections.Counter(c["labeler"] for c in part)
        lines.append(f"| {k} | {len(slots)} of 12 | {len(rules)} of {len(frequency)} | "
                     f"{sum(not c['useful'] for c in part)} | "
                     f"{', '.join(f'{n} {labelers[n]}' for n in LABELERS)} | "
                     f"~{sum(c['chars'] for c in part) // 4:,} |")
    lines += ["", "## The 12 candidates, in selection order (the first 4 are k=4, the first 8 are k=8)", "",
              "| # | Source | Article id | Useful | Slots | Kinds | Countries | Characters | Hardness | Why hard |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for number, c in enumerate(chosen, 1):
        lines.append(f"| {number} | {c['source']} | {c['article_id']} | {'yes' if c['useful'] else 'no'} | "
                     f"{', '.join(map(str, c['slots'])) or '-'} | {', '.join(c['kinds']) or '-'} | "
                     f"{', '.join(c['countries']) or '-'} | {c['chars']:,} | {c['hardness']:.1f} | "
                     f"{'; '.join(c['hard_reasons']) or '-'} |")
    covered = set().union(*(set(c["rules"]) for c in chosen))
    lines += ["", f"Rules used in the pool but in none of the 12: "
              f"{', '.join(sorted(set(frequency) - covered, key=lambda r: -frequency[r])) or 'none'}.", "",
              "## Alternates per slot (up to 3, shortest first)", "",
              "| Slot | Rules | Chosen | Alternates |", "|---|---|---|---|"]
    for slot, (name, rule_ids) in SLOTS.items():
        picked = [c["source"] for c in chosen if slot in c["slots"]]
        others = sorted((c for c in pool if slot in c["slots"] and c not in chosen), key=lambda c: c["chars"])[:3]
        lines.append(f"| {slot}. {name} | {rule_ids} | {', '.join(picked) or '-'} | "
                     f"{', '.join(c['source'] for c in others) or '-'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_records = config.RECORDS_DIR
    parser.add_argument("--records-dir", type=Path, default=default_records,
                        help=f"folder with the *{config.RECORDS_SUFFIX} files (default: {default_records})")
    parser.add_argument("--hard-runs", type=Path, nargs="*", default=[],
                        help="evaluated run folders whose mistakes mark articles as hard (their article_metrics.csv)")
    parser.add_argument("--k", type=int, choices=[k for k, _, _ in STAGES], default=8,
                        help="how many examples the prompt gets (default 8)")
    args = parser.parse_args()

    pool, excluded = build_pool(args.records_dir, args.hard_runs)
    print(f"hardness from {len(args.hard_runs)} earlier runs: {', '.join(d.name for d in args.hard_runs) or 'none'}")
    chosen = select(pool)
    path = config.EXAMPLES_PATH
    examples = [c["example"] for c in prompt_order(chosen[:args.k])]
    problems = check_examples(examples, json.loads(config.ARTICLES_PATH.read_text(encoding="utf-8")))
    if problems:
        raise SystemExit(f"k={args.k}: the chosen examples fail the {config.PROMPT_VERSION} checks:\n" + "\n".join(problems[:10]))
    path.write_text(json.dumps(examples, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.name} (k = {args.k}): {', '.join(e['source'] for e in examples)}")
    sheet = config.PROJECT_DIR / "few_shot_selection.md"
    sheet.write_text(review_sheet(chosen, pool, excluded), encoding="utf-8")
    print(f"wrote {sheet.relative_to(config.PROJECT_DIR)}")


if __name__ == "__main__":
    main()
