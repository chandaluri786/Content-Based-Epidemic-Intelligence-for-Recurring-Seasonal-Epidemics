"""
Step 3 of pool preparation: group syndicated near-copies of the same story,
so the labeling sample takes at most one article per group. Wire
copies share no record ID or URL, so exact dedup can't see them; text similarity can.

Method: lowercase word 5-shingles -> MinHash (128 permutations) -> LSH at
Jaccard >= NEAR_DUP_JACCARD. Every LSH candidate pair is re-checked against
the MinHash Jaccard estimate before linking (LSH alone lets false positives
through, and union-find would chain them), then linked pairs are merged
transitively with union-find.

Texts shorter than MIN_WORDS can't be compared reliably and stay in their
own group. A group's ID is its smallest gkg_record_id, so IDs are stable
across re-runs as long as the group's membership doesn't change.

Watch the report's largest groups: a big group from a single domain more
likely means shared extraction boilerplate (navigation/sidebar text) than
syndication, and is worth spot-checking.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from datasketch import LeanMinHash, MinHash, MinHashLSH

from dataset_prep.union_find import UnionFind

logger = logging.getLogger(__name__)

SHINGLE_WORDS = 5
MIN_WORDS = 50
NUM_PERM = 128
NEAR_DUP_JACCARD = 0.8
LARGEST_GROUPS_REPORTED = 20
SAMPLE_URLS_PER_GROUP = 5

_WORD = re.compile(r"\w+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def shingles(text: str) -> set[bytes]:
    words = _words(text)
    return {" ".join(words[i:i + SHINGLE_WORDS]).encode("utf-8") for i in range(len(words) - SHINGLE_WORDS + 1)}


def signature(text: str) -> LeanMinHash | None:
    """None when the text is too short to compare."""
    if len(_words(text)) < MIN_WORDS:
        return None
    m = MinHash(num_perm=NUM_PERM)
    m.update_batch(list(shingles(text)))
    return LeanMinHash(m)


def group_near_duplicates(signatures: list[LeanMinHash | None]) -> list[list[int]]:
    """Index groups, singletons included, ordered by smallest member."""
    lsh = MinHashLSH(threshold=NEAR_DUP_JACCARD, num_perm=NUM_PERM)
    uf = UnionFind(len(signatures))
    for i, sig in enumerate(signatures):
        if sig is None:
            continue
        for j in lsh.query(sig):
            if sig.jaccard(signatures[j]) >= NEAR_DUP_JACCARD:
                uf.union(i, j)
        lsh.insert(i, sig)
    return uf.groups()


def _domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _load(pool_path: Path) -> tuple[list[str], list[str], list[LeanMinHash | None]]:
    record_ids: list[str] = []
    urls: list[str] = []
    signatures: list[LeanMinHash | None] = []
    with pool_path.open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            record_ids.append(record["gkg_record_id"])
            urls.append(record["url"])
            signatures.append(signature(record["article"]))
    return record_ids, urls, signatures


def _report(groups: list[list[int]], record_ids: list[str], urls: list[str],
            signatures: list[LeanMinHash | None]) -> dict:
    multi = [g for g in groups if len(g) > 1]
    largest = sorted(multi, key=len, reverse=True)[:LARGEST_GROUPS_REPORTED]
    return {
        "articles": len(record_ids),
        "too_short_to_compare": sum(s is None for s in signatures),
        "groups": len(groups),
        "multi_member_groups": len(multi),
        "articles_in_multi_member_groups": sum(len(g) for g in multi),
        "group_size_histogram": {str(k): v for k, v in sorted(Counter(len(g) for g in groups).items())},
        "largest_groups": [
            {
                "near_dup_group": min(record_ids[i] for i in g),
                "size": len(g),
                "distinct_domains": len({_domain(urls[i]) for i in g}),
                "sample_urls": [urls[i] for i in g[:SAMPLE_URLS_PER_GROUP]],
            }
            for g in largest
        ],
    }


def run_near_dup(pool_path: Path, out_path: Path) -> dict:
    """Writes {gkg_record_id, near_dup_group, group_size} per pooled article; returns the report."""
    record_ids, urls, signatures = _load(pool_path)
    logger.info("Near-dup: %d signatures computed (%d too short to compare)",
                len(signatures), sum(s is None for s in signatures))

    groups = group_near_duplicates(signatures)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out:
        for g in groups:
            group_id = min(record_ids[i] for i in g)
            for i in g:
                out.write(json.dumps({"gkg_record_id": record_ids[i], "near_dup_group": group_id,
                                      "group_size": len(g)}) + "\n")
    return _report(groups, record_ids, urls, signatures)
