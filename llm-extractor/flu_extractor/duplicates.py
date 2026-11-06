"""Find items in one list that may be the same event told twice, without deleting anything.

Candidate groups (duplicates_v1), within one article and one side (gold or model):
  - exact: identical on every applicable field after normalization (evidence not compared);
  - near: the same kind, place (city, state, country), strain and value (the number for counts,
    with the same status and count type; the trend word for trends), with overlapping periods,
    but not identical (in practice: other dates). Items for different places, or a total and its
    parts, are separate items under G5 and 9.7, so they are never near duplicates, even when
    they quote the same sentence.

A candidate is not a confirmed duplicate: two people admitted to two hospitals in the same
country on the same day can give two identical items, and both are real. So:
  - model side: an unmatched model item that is in a group with a matched model item is a
    `duplicate extra`. If it also shares an evidence quote with that item it is a `repeat` (the
    same sentence extracted twice); otherwise it stays a `possible duplicate` for review.
    Raw counts always include these items; duplicate-adjusted figures are reported separately.
  - gold side: candidate groups are listed for review. A decision file
    (data/duplicate_adjudication.json) records each review as distinct, duplicate or unresolved.
    `duplicate` groups are reduced to their first item in the adjudicated reference; the raw gold
    stays unchanged. Articles with unreviewed or unresolved gold groups are reference-uncertain.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from flu_extractor.normalization import applicable_fields, normalize_item

DUPLICATES_VERSION = "duplicates_v1"
EXACT, NEAR = "exact", "near"
REPEAT, POSSIBLE = "repeat", "possible duplicate"
DISTINCT, DUPLICATE, UNRESOLVED = "distinct", "duplicate", "unresolved"


@dataclass(frozen=True)
class DuplicateGroup:
    indexes: tuple[int, ...]   # positions in the item list
    category: str              # EXACT or NEAR


def _period(item: dict) -> tuple[str, str] | None:
    end = item["end_date"]
    if not isinstance(end, str):
        return None
    start = item["start_date"] if isinstance(item["start_date"], str) else end
    return start, end


def _overlap(first: dict, second: dict) -> bool:
    a, b = _period(first), _period(second)
    if a is None or b is None:
        return a == b
    return a[0] <= b[1] and b[0] <= a[1]


def _related(raw_a: dict, raw_b: dict) -> str | None:
    a, b = normalize_item(raw_a), normalize_item(raw_b)
    if all(a[name] == b[name] for name in applicable_fields(a["kind"])):
        return EXACT
    keys = ("kind", "strain", "city", "state", "country",
            *(("words",) if a["kind"] == "trend" else ("number", "status", "count_type")))
    if all(a[name] == b[name] for name in keys) and _overlap(a, b):
        return NEAR
    return None


def find_groups(items: list[dict]) -> list[DuplicateGroup]:
    """Connected groups of related items. A group is EXACT only if all its links are exact."""
    parent = list(range(len(items)))
    kinds: dict[tuple[int, int], str] = {}

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            category = _related(items[i], items[j])
            if category:
                kinds[(i, j)] = category
                parent[root(i)] = root(j)
    members: dict[int, list[int]] = {}
    for i in range(len(items)):
        members.setdefault(root(i), []).append(i)
    groups = []
    for indexes in members.values():
        if len(indexes) < 2:
            continue
        links = [c for (i, j), c in kinds.items() if i in indexes and j in indexes]
        groups.append(DuplicateGroup(tuple(sorted(indexes)), EXACT if all(c == EXACT for c in links) else NEAR))
    return sorted(groups, key=lambda g: g.indexes)


def shares_a_quote(first: dict, second: dict) -> bool:
    quotes = lambda item: {" ".join(str(q).split()).lower() for q in item.get("evidence") or []}  # noqa: E731
    return bool(quotes(first) & quotes(second))


def classify_model_extras(model_items: list[dict], matched: set[int], unmatched: list[int]) -> dict[int, str]:
    """For each unmatched model item that duplicates another model item: REPEAT or POSSIBLE."""
    labels = {}
    for group in find_groups(model_items):
        kept = [i for i in group.indexes if i in matched] or [group.indexes[0]]
        for i in group.indexes:
            if i in unmatched and i not in kept:
                partner = kept[0]
                labels[i] = REPEAT if shares_a_quote(model_items[i], model_items[partner]) else POSSIBLE
    return labels


# --- Gold adjudication -------------------------------------------------------

def load_adjudication(path: Path) -> dict[tuple[str, tuple[int, ...]], dict]:
    """Read the review decisions: {(article_id, item indexes): {"decision": ..., "reason": ...}}."""
    if not path.exists():
        return {}
    records = json.loads(path.read_text(encoding="utf-8"))
    return {(r["article_id"], tuple(r["item_indexes"])): r for r in records}


def adjudicated_gold(article_id: str, items: list[dict],
                     decisions: dict[tuple[str, tuple[int, ...]], dict]) -> tuple[list[dict], list[dict]]:
    """The gold list to score against, and one review row per candidate group.

    Each review row says the group, its category and the decision (or `not reviewed`). Only groups
    decided as DUPLICATE change the list: their items after the first are left out.
    """
    drop, reviews = set(), []
    for group in find_groups(items):
        decision = decisions.get((article_id, group.indexes), {})
        status = decision.get("decision", "not reviewed")
        if status == DUPLICATE:
            drop.update(group.indexes[1:])
        reviews.append({"article_id": article_id, "item_indexes": list(group.indexes),
                        "category": group.category, "decision": status, "reason": decision.get("reason", "")})
    return [item for i, item in enumerate(items) if i not in drop], reviews
