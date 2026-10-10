"""Split the 1,200-article sample into one labeling packet per team member.

Every bucket is dealt across the four labelers, so each gets the same mix of likely-useful
and likely-not-useful articles (300 each) and nobody gets all the slow, extraction-heavy ones.

Round 1 for each labeler is 20 of their own articles (10 likely useful, 10 not, spread over
the buckets) plus a blind re-label of the next labeler's 20, so 80 articles are labeled twice
for the agreement check. Bucket names are left out of the packets so they can't steer a label;
they are kept in assignment_key.csv for the coordinator.

Usage:
    python sampling/make_label_packets.py
    python sampling/make_label_packets.py --sample sampling/output/sample_1200.jsonl --out-dir sampling/output/labeling
"""
import argparse
import csv
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTRUCTIONS = HERE / "HOW_TO_LABEL.md"

# Labeling order: each labeler blind re-labels the next one's round-1 articles (last wraps to first).
LABELERS = ["Jahnavi", "Thanya", "Manoj", "Aditya"]
PILOT_PER_SIDE = 10  # round 1 = 10 likely useful + 10 likely not useful
OWN_ROUND, MAIN_ROUND = "1-own", "2"
LABEL_COLUMNS = ["row", "round", "article_id", "link", "scan_date", "useful",
                 "disease", "strain", "causes", "symptoms", "labeler", "notes"]
ITEM_COLUMNS = ["article_id", "kind", "number", "status", "total_or_new", "city", "state",
                "country", "start_date", "end_date", "words", "evidence"]
KEY_COLUMNS = ["article_id", "owner", "pilot", "checked_by", "bucket"]


def likely_useful(bucket: str) -> bool:
    return bucket[0] in "PZ"


def checker_of(labeler: str) -> str:
    """Who blind re-labels this labeler's round-1 articles."""
    return LABELERS[LABELERS.index(labeler) - 1]


def partner_of(labeler: str) -> str:
    """Whose round-1 articles this labeler blind re-labels."""
    return LABELERS[(LABELERS.index(labeler) + 1) % len(LABELERS)]


def deal(rows: list[dict], rng: random.Random) -> dict[str, list[dict]]:
    """Deal every bucket across the labelers, largest bucket first, smallest packet first."""
    by_bucket = defaultdict(list)
    for r in rows:
        by_bucket[r["bucket"]].append(r)
    packets = {name: [] for name in LABELERS}
    for bucket in sorted(by_bucket, key=lambda b: (-len(by_bucket[b]), b)):
        members = sorted(by_bucket[bucket], key=lambda r: r["record_id"])
        rng.shuffle(members)
        order = sorted(LABELERS, key=lambda name: (len(packets[name]), LABELERS.index(name)))
        for i, r in enumerate(members):
            packets[order[i % len(order)]].append(r)
    return packets


def pick_pilot(packet: list[dict], rng: random.Random) -> list[dict]:
    """Round 1: 10 likely-useful and 10 likely-not-useful articles, one bucket at a time, shuffled."""
    pilot = []
    for want_useful in (True, False):
        by_bucket = defaultdict(list)
        for r in packet:
            if likely_useful(r["bucket"]) == want_useful:
                by_bucket[r["bucket"]].append(r)
        buckets = sorted(by_bucket, key=lambda b: (-len(by_bucket[b]), b))
        queues = {b: list(by_bucket[b]) for b in buckets}
        taken, i = [], 0
        while len(taken) < PILOT_PER_SIDE and any(queues.values()):
            b = buckets[i % len(buckets)]
            if queues[b]:
                taken.append(queues[b].pop(0))
            i += 1
        pilot.extend(taken)
    rng.shuffle(pilot)
    return pilot


def packet_rows(name: str, packets: dict, pilots: dict) -> list[tuple[str, dict]]:
    """(round, article) pairs in sheet order: own round 1, partner's round 1, then the rest."""
    partner = partner_of(name)
    pilot_ids = {r["record_id"] for r in pilots[name]}
    rest = [r for r in packets[name] if r["record_id"] not in pilot_ids]
    return ([(OWN_ROUND, r) for r in pilots[name]]
            + [(f"1-check-{partner}", r) for r in pilots[partner]]
            + [(MAIN_ROUND, r) for r in rest])


def write_packet(out_dir: Path, name: str, rows: list[tuple[str, dict]]) -> None:
    with open(out_dir / f"{name}_labels.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        for n, (rnd, r) in enumerate(rows, 1):
            w.writerow({"row": n, "round": rnd, "article_id": r["record_id"], "link": r["url"],
                        "scan_date": r["scan_date"], "labeler": name})
    with open(out_dir / f"{name}_items.csv", "w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=ITEM_COLUMNS).writeheader()
    with open(out_dir / f"{name}_texts.txt", "w", encoding="utf-8") as f:
        for n, (rnd, r) in enumerate(rows, 1):
            f.write(f"{'=' * 80}\n#{n}  [{rnd}]  {r['record_id']}\n"
                    f"scan date: {r['scan_date']}\nlink: {r['url']}\n{'-' * 80}\n"
                    f"{r['text'].strip()}\n\n")


def assignment_key(packets: dict, pilots: dict) -> list[dict]:
    key = []
    for name in LABELERS:
        pilot_ids = {r["record_id"] for r in pilots[name]}
        key += [{"article_id": r["record_id"], "owner": name, "pilot": r["record_id"] in pilot_ids,
                 "checked_by": checker_of(name) if r["record_id"] in pilot_ids else "",
                 "bucket": r["bucket"]} for r in packets[name]]
    return key


def make_packets(rows: list[dict], seed: int) -> tuple[dict, dict]:
    """Return (packets, pilots), each keyed by labeler name."""
    rng = random.Random(seed)
    packets = deal(rows, rng)
    pilots = {name: pick_pilot(packets[name], rng) for name in LABELERS}
    return packets, pilots


def main() -> None:
    p = argparse.ArgumentParser(description="Split the labeling sample into one packet per labeler.")
    p.add_argument("--sample", type=Path, default=HERE / "output" / "sample_1200.jsonl",
                   help="sample_1200.jsonl written by run_sampling.py")
    p.add_argument("--out-dir", type=Path, default=HERE / "output" / "labeling")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    with open(args.sample, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    packets, pilots = make_packets(rows, args.seed)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name in LABELERS:
        write_packet(args.out_dir, name, packet_rows(name, packets, pilots))
        n_useful = sum(likely_useful(r["bucket"]) for r in packets[name])
        print(f"{name}: {len(packets[name])} articles ({n_useful} likely useful), "
              f"round 1 checked by {checker_of(name)}")
    with open(args.out_dir / "assignment_key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KEY_COLUMNS)
        w.writeheader()
        w.writerows(assignment_key(packets, pilots))
    shutil.copy(INSTRUCTIONS, args.out_dir / INSTRUCTIONS.name)
    print(f"saved to {args.out_dir} (keep assignment_key.csv to yourself: it shows the buckets)")


if __name__ == "__main__":
    main()
