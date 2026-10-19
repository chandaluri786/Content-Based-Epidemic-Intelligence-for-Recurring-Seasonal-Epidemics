"""Split the 1,200 labeled articles into a dev set (400) and a test set (800).

Both sets keep the natural mix of useful and not-useful articles. The split is stratified by
useful x bucket x country, copies of the same story always go to the same set, and a final swap
pass makes sure every rule the labels exercise has a few articles in dev, where the prompt's
few-shot examples are picked from. Draw it once, before any prompt tuning, and never redraw it:
the script refuses to overwrite an existing split unless --force is given.

Usage:
    python sampling/make_dev_test_split.py
    python sampling/make_dev_test_split.py --labeling-dir sampling/output/labeling --out-dir sampling/split
"""
import argparse
import csv
import json
import math
import random
import re
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELERS = ["Jahnavi", "Thanya", "Manoj", "Aditya"]
DEV_FRACTION = 1 / 3
SHINGLE_WORDS = 5            # word n-grams compared between articles
SAME_STORY = 0.3             # Jaccard similarity at or above which two articles are one story
BOILERPLATE_SHARE = 0.05     # shingles found in more than this share of articles are ignored
MIN_SHARED_SENTENCE = 40     # shortest evidence sentence (characters) that can tie two articles
MIN_SHARED_FIGURE = 10       # smallest count that ties two articles reporting the same figure
FIGURE_DAYS = 3              # their end dates may differ by this many days
DEV_PER_TAG = 3              # each rule tag wants this many dev articles (or half its total)
SPLIT_COLUMNS = ["article_id", "split", "labeler", "useful", "bucket", "country", "year",
                 "story_group", "tags"]

WEEKDAY = r"\b(?:on|last|this past)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
DATE_WORDING = {
    "date:weekday": WEEKDAY,
    "date:yesterday": r"\byesterday\b",
    "date:last_week": r"\blast week\b",
    "date:past_week": r"\bin the (?:last|past) week\b",
    "date:week_ending": r"\bweek end(?:ing|ed)\b",
    "date:since": r"\bsince\b",
    "date:this_season": r"\bthis (?:flu )?season\b",
    "date:so_far_this_year": r"\bso far this year\b|\byear to date\b",
    "date:week_number": r"\bepi ?week\b|\bweek \d+\b",
    "date:last_month": r"\blast month\b",
}
ANIMAL_STRAIN = r"\bH(?:5|7|9|10)N?\d*\b|bird|avian"
ZERO_WORDS = r"\bno (?:new )?(?:cases|deaths)\b|unaffected|not received|no flu|minimal"
STRAIN_SHARE = r"\d+(?:\.\d+)?\s*(?:%|per ?cent).*\b(?:H\d+N\d+|influenza [AB])\b|dominant|predominant|most circulation"
COMPARISON = r"\bcompared (?:to|with)\b|\bup from\b|\bdown from\b|\bthan (?:last|the same)\b"
TERRITORY_PLACES = {"Hong Kong", "Macau"}
TERRITORY_WORDS = r"\bGuam\b|American Samoa|French Polynesia|New Caledonia"
NOTE_REASONS = {
    "note:forecast": r"forecast",
    "note:no_country": r"no country|worldwide|regional",
    "note:past": r"finished|past season|last year|30 days|months before|old event|undated",
    "note:in_passing": r"in passing|vaccin|research|history|1918|spanish flu",
    "note:animal": r"animal|poultry|birds|herds|dog flu|canine",
}


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_answers(labeling_dir: Path) -> tuple[dict[str, dict], list[dict]]:
    """One answer per article: the owner's label, notes and items. Also the check-row disagreements."""
    answers, checks = {}, []
    items_by_labeler = {}
    for name in LABELERS:
        for row in read_csv(labeling_dir / f"{name}_labels.csv"):
            useful = row["useful"].strip().lower()
            if row["round"].startswith("1-check"):
                checks.append({"article_id": row["article_id"], "checker": name, "useful": useful})
            else:
                answers[row["article_id"]] = {"labeler": name, "useful": useful,
                                              "notes": row.get("notes", ""), "items": []}
        items_by_labeler[name] = read_csv(labeling_dir / f"{name}_items.csv")
    for name, rows in items_by_labeler.items():
        for item in rows:
            answer = answers.get(item["article_id"])
            if answer and answer["labeler"] == name:
                answer["items"].append(item)
    disagreements = [{**c, "owner": answers[c["article_id"]]["labeler"],
                      "owner_useful": answers[c["article_id"]]["useful"]}
                     for c in checks if answers[c["article_id"]]["useful"] != c["useful"]]
    return answers, disagreements


def shingles(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(" ".join(words[i:i + SHINGLE_WORDS]) for i in range(len(words) - SHINGLE_WORDS + 1))


def evidence_sentences(answer: dict) -> set[str]:
    parts = (p for item in answer["items"] for p in re.split(r"\s*\|\|\s*", item["evidence"]))
    return {re.sub(r"\s+", " ", p).strip().lower() for p in parts if len(p.strip()) >= MIN_SHARED_SENTENCE}


def story_groups(texts: dict[str, str], answers: dict[str, dict]) -> dict[str, str]:
    """Map each article to its story group id (the smallest article id in the group)."""
    parent = {a: a for a in texts}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    sets = {a: shingles(t) for a, t in texts.items()}
    holders = defaultdict(list)
    for a, s in sets.items():
        for sh in s:
            holders[sh].append(a)
    limit = max(2, int(len(texts) * BOILERPLATE_SHARE))
    shared = Counter()
    for members in holders.values():
        if 1 < len(members) <= limit:
            members = sorted(members)
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    shared[(a, b)] += 1
    for (a, b), n in shared.items():
        if n / (len(sets[a]) + len(sets[b]) - n) >= SAME_STORY:
            union(a, b)

    by_sentence, by_figure = defaultdict(list), defaultdict(list)
    for a in sorted(texts):
        answer = answers.get(a, {"items": []})
        for sentence in evidence_sentences(answer):
            by_sentence[sentence].append(a)
        for key, end in reported_figures(answer):
            by_figure[key].append((end, a))
    for members in by_sentence.values():
        for b in members[1:]:
            union(members[0], b)
    for reports in by_figure.values():
        for (end_a, a), (end_b, b) in combinations(sorted(reports), 2):
            if abs((end_a - end_b).days) <= FIGURE_DAYS:
                union(a, b)
    return {a: find(a) for a in texts}


def reported_figures(answer: dict) -> list[tuple[tuple, date]]:
    """(kind, number, country, state) and end date of each sizeable count, to spot one event told twice."""
    figures = []
    for i in answer["items"]:
        if i["kind"] != "trend" and i["number"].isdigit() and int(i["number"]) >= MIN_SHARED_FIGURE and i["end_date"]:
            key = (i["kind"], int(i["number"]), i["country"], i["state"])
            figures.append((key, date.fromisoformat(i["end_date"])))
    return figures


def item_tags(items: list[dict]) -> set[str]:
    tags = {f"kind:{i['kind']}" for i in items}
    counts = [i for i in items if i["kind"] != "trend"]
    trends = [i for i in items if i["kind"] == "trend"]
    if any(i["status"] == "suspected" for i in items):
        tags.add("status:suspected")
    if {"new", "total"} <= {i["total_or_new"] for i in counts}:
        tags.add("count:new_and_total")
    if any(i["total_or_new"] == "total" and i["start_date"] and i["start_date"] != i["end_date"] for i in counts):
        tags.add("count:period_total")
    if any(i["total_or_new"] == "total" and not i["start_date"] and i["end_date"] for i in counts):
        tags.add("count:open_total")
    if any(re.search(ZERO_WORDS, i["words"], re.I) for i in trends):
        tags.add("trend:zero_or_low")
    if any(re.search(STRAIN_SHARE, f"{i['words']} {i['evidence']}", re.I) for i in trends):
        tags.add("trend:strain_share")
    if any(re.search(r"%|per ?cent", i["words"], re.I) for i in trends):
        tags.add("trend:percentage")
    if any(i["city"] in TERRITORY_PLACES or re.search(TERRITORY_WORDS, i["evidence"]) for i in items):
        tags.add("place:territory")
    if len({i["country"] for i in items}) > 1:
        tags.add("place:several_countries")
    if any(re.search(ANIMAL_STRAIN, i["strain"], re.I) for i in items):
        tags.add("strain:animal_flu_in_people")
    if any(not i["start_date"] and not i["end_date"] for i in items):
        tags.add("date:none_stated")
    evidence = " ".join(i["evidence"] for i in items)
    tags.update(tag for tag, pattern in DATE_WORDING.items() if re.search(pattern, evidence, re.I))
    if re.search(COMPARISON, evidence, re.I):
        tags.add("count:comparison_nearby")
    return tags


def article_tags(answer: dict, bucket: str) -> frozenset[str]:
    """The rules an article exercises, from its items, its bucket and the harmonising notes."""
    tags = item_tags(answer["items"])
    if answer["useful"] == "no":
        tags.add(f"no:{bucket}")
        if bucket[0] in "PZ":
            tags.add("no:word_rules_said_useful")
    elif bucket[0] in "NX":
        tags.add("yes:word_rules_said_not_useful")
    notes = answer.get("notes", "")
    tags.update(tag for tag, pattern in NOTE_REASONS.items() if re.search(pattern, notes, re.I))
    return frozenset(tags)


def largest_remainder(sizes: dict, total: int) -> dict:
    """Integer shares of `total` proportional to `sizes`, ties broken by key order."""
    whole = sum(sizes.values())
    exact = {k: n * total / whole for k, n in sizes.items()} if whole else {k: 0 for k in sizes}
    shares = {k: math.floor(v) for k, v in exact.items()}
    for k in sorted(exact, key=lambda k: (-(exact[k] - shares[k]), k))[:total - sum(shares.values())]:
        shares[k] += 1
    return shares


def nested_quotas(sizes: dict[tuple, int], total: int, level: int = 0) -> dict[tuple, int]:
    """Split `total` level by level over the stratum key, so every level's margins stay exact."""
    if level == len(next(iter(sizes))):
        return {next(iter(sizes)): total}
    by_value = defaultdict(dict)
    for key, n in sizes.items():
        by_value[key[level]][key] = n
    shares = largest_remainder({v: sum(s.values()) for v, s in by_value.items()}, total)
    quotas = {}
    for value, sub in by_value.items():
        quotas.update(nested_quotas(sub, shares[value], level + 1))
    return quotas


def dev_targets(stratum_of: dict[str, tuple]) -> dict[tuple, int]:
    """Dev quota per stratum (useful, bucket, labeler, country), one third of each level in turn."""
    sizes = Counter(stratum_of.values())
    return nested_quotas(dict(sizes), round(sum(sizes.values()) * DEV_FRACTION))


def allocate(groups: list[tuple[str, ...]], stratum_of: dict[str, tuple], rng: random.Random) -> set[str]:
    """Put whole story groups into dev until each stratum reaches its quota; the rest is test."""
    targets = dev_targets(stratum_of)
    order = sorted(groups)
    rng.shuffle(order)
    order.sort(key=lambda g: len(g) == 1)  # multi-article stories first, single articles fill the gaps
    taken, dev = Counter(), set()
    for group in order:
        need = Counter(stratum_of[a] for a in group)
        if all(taken[s] + n <= targets[s] for s, n in need.items()):
            dev.update(group)
            taken.update(need)
    return dev


def tag_minimums(tags_of: dict[str, frozenset]) -> dict[str, int]:
    totals = Counter(t for tags in tags_of.values() for t in tags)
    return {t: min(DEV_PER_TAG, math.ceil(n / 2)) for t, n in totals.items()}


def cover_tags(groups: list[tuple[str, ...]], dev: set[str], stratum_of: dict, tags_of: dict,
               rng: random.Random) -> tuple[set[str], list[dict], list[str]]:
    """Swap matched story groups so every tag reaches its dev minimum. Returns (dev, swaps, unmet)."""
    dev = set(dev)
    minimum = tag_minimums(tags_of)
    group_tags = {g: Counter(t for a in g for t in tags_of[a]) for g in groups}
    strict = {g: tuple(sorted(Counter(stratum_of[a] for a in g).items())) for g in groups}
    loose = {g: tuple(sorted(Counter(stratum_of[a][0] for a in g).items())) for g in groups}
    swaps, unmet = [], []
    totals = Counter(t for tags in tags_of.values() for t in tags)
    for tag in sorted(minimum, key=lambda t: (totals[t], t)):
        while True:
            have = Counter(t for a in dev for t in tags_of[a])
            if have[tag] >= minimum[tag]:
                break
            incoming = [g for g in sorted(groups) if g[0] not in dev and group_tags[g][tag]]
            rng.shuffle(incoming)
            swap = None
            # same stratum first; if none, any group with the same useful/not-useful make-up
            for signature in (strict, loose):
                for g_in in incoming:
                    outgoing = [g for g in sorted(groups) if g[0] in dev and not group_tags[g][tag]
                                and signature[g] == signature[g_in]]
                    rng.shuffle(outgoing)
                    for g_out in outgoing:
                        after = have.copy()
                        after.subtract(group_tags[g_out])
                        after.update(group_tags[g_in])
                        if all(after[t] >= minimum[t] for t in minimum if have[t] >= minimum[t]):
                            swap = (g_in, g_out)
                            break
                    if swap:
                        break
                if swap:
                    break
            if not swap:
                unmet.append(tag)
                break
            g_in, g_out = swap
            dev.difference_update(g_out)
            dev.update(g_in)
            swaps.append({"tag": tag, "to_dev": g_in, "to_test": g_out})
    return dev, swaps, unmet


def make_split(sample: list[dict], answers: dict[str, dict], seed: int) -> dict:
    """Return the split and everything the report needs."""
    rng = random.Random(seed)
    rows = {r["record_id"]: r for r in sample}
    stratum_of = {a: (answers[a]["useful"], rows[a]["bucket"], answers[a]["labeler"], rows[a]["country"])
                  for a in rows}
    tags_of = {a: article_tags(answers[a], rows[a]["bucket"]) for a in rows}
    group_of = story_groups({a: rows[a].get("text", "") for a in rows}, answers)
    members = defaultdict(list)
    for a, g in group_of.items():
        members[g].append(a)
    groups = [tuple(sorted(m)) for m in members.values()]
    dev = allocate(groups, stratum_of, rng)
    dev, swaps, unmet = cover_tags(groups, dev, stratum_of, tags_of, rng)
    return {"split": {a: "dev" if a in dev else "test" for a in rows}, "group_of": group_of,
            "tags_of": tags_of, "swaps": swaps, "unmet": unmet, "minimum": tag_minimums(tags_of)}


def write_split(path: Path, sample: list[dict], answers: dict, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SPLIT_COLUMNS)
        w.writeheader()
        for r in sorted(sample, key=lambda r: r["record_id"]):
            a = r["record_id"]
            w.writerow({"article_id": a, "split": result["split"][a], "labeler": answers[a]["labeler"],
                        "useful": answers[a]["useful"], "bucket": r["bucket"], "country": r["country"],
                        "year": r["year"], "story_group": result["group_of"][a],
                        "tags": "; ".join(sorted(result["tags_of"][a]))})


def _table(title: str, counts: dict) -> list[str]:
    lines = [f"| {title} | dev useful | dev total | test useful | test total |", "|---|---|---|---|---|"]
    for key in sorted(counts):
        c = counts[key]
        lines.append(f"| {key} | {c['dev', 'yes']} | {c['dev', 'yes'] + c['dev', 'no']} | "
                     f"{c['test', 'yes']} | {c['test', 'yes'] + c['test', 'no']} |")
    return lines + [""]


def write_report(path: Path, sample: list[dict], answers: dict, result: dict, disagreements: list[dict],
                 seed: int) -> None:
    split, tags_of = result["split"], result["tags_of"]
    by = defaultdict(lambda: defaultdict(Counter))
    for r in sample:
        a = r["record_id"]
        key = (split[a], answers[a]["useful"])
        for name, value in (("labeler", answers[a]["labeler"]), ("country", r["country"]),
                            ("bucket", r["bucket"]), ("year", r["year"]), ("all", "all")):
            by[name][value][key] += 1
    groups = Counter(result["group_of"].values())
    multi = {g: n for g, n in groups.items() if n > 1}
    lines = [
        "# Dev/test split", "",
        f"Written for: the team. Made by `sampling/make_dev_test_split.py` with seed {seed}. "
        "Do not redraw it once prompt tuning has started.", "",
        "Dev and test keep the natural share of useful articles. Few-shot examples come from dev only.", "",
        *_table("set", by["all"]), *_table("labeler", by["labeler"]), *_table("country", by["country"]),
        *_table("year", by["year"]), *_table("bucket", by["bucket"]),
        "## Same-story groups", "",
        f"{len(multi)} groups hold {sum(multi.values())} articles that tell the same story; "
        "each group sits in one set.", "",
        "| group | articles | set |", "|---|---|---|",
        *[f"| {g} | {n} | {split[g]} |" for g, n in sorted(multi.items())], "",
        "## Rule tags", "",
        "Each tag needs min(3, half its total) dev articles. "
        f"{len(result['swaps'])} swaps between matched groups were made to get there.", "",
        "| tag | dev | test | dev minimum |", "|---|---|---|---|",
    ]
    totals = Counter((t, split[a]) for a, tags in tags_of.items() for t in tags)
    for tag in sorted(result["minimum"]):
        lines.append(f"| {tag} | {totals[tag, 'dev']} | {totals[tag, 'test']} | {result['minimum'][tag]} |")
    lines += ["", "Tags that could not reach their minimum: "
              + (", ".join(result["unmet"]) if result["unmet"] else "none") + ".", "",
              "## Check rows that still disagree with the owner", ""]
    if disagreements:
        lines += ["| article | owner | owner says | checker | checker says |", "|---|---|---|---|---|"]
        lines += [f"| {d['article_id']} | {d['owner']} | {d['owner_useful']} | {d['checker']} | {d['useful']} |"
                  for d in disagreements]
        lines += ["", "The owner's label is used. Settle these with the team."]
    else:
        lines.append("None.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Split the labeled sample into dev (1/3) and test (2/3).")
    p.add_argument("--sample", type=Path, default=HERE / "output" / "sample_1200.jsonl")
    p.add_argument("--labeling-dir", type=Path, default=HERE / "output" / "labeling")
    p.add_argument("--out-dir", type=Path, default=HERE / "split")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--force", action="store_true", help="overwrite an existing split")
    args = p.parse_args()

    out = args.out_dir / "dev_test_split.csv"
    if out.exists() and not args.force:
        raise SystemExit(f"{out} exists; the split is frozen. Use --force only before prompt tuning starts.")
    with open(args.sample, encoding="utf-8") as f:
        sample = [json.loads(line) for line in f]
    answers, disagreements = load_answers(args.labeling_dir)
    missing = [r["record_id"] for r in sample if r["record_id"] not in answers]
    if missing:
        raise SystemExit(f"{len(missing)} sample articles have no label, e.g. {missing[:3]}")
    result = make_split(sample, answers, args.seed)
    write_split(out, sample, answers, result)
    write_report(args.out_dir / "split_report.md", sample, answers, result, disagreements, args.seed)
    counts = Counter((result["split"][a], answers[a]["useful"]) for a in result["split"])
    for name in ("dev", "test"):
        total = counts[name, "yes"] + counts[name, "no"]
        print(f"{name}: {total} articles, {counts[name, 'yes']} useful ({counts[name, 'yes'] / total:.0%})")
    print(f"unmet tags: {', '.join(result['unmet']) or 'none'}; saved to {args.out_dir}")


if __name__ == "__main__":
    main()
