"""
Step 1 of pool preparation: exact dedup across every source file in the
dataset directory.

Two records are the same article if they share a GDELT record ID (the same
scan stored twice, e.g. "2018/upload.jsonl" and "2018/redownload.jsonl") or a normalized URL
(the same page re-scanned by GDELT under a new record ID). Links are
transitive -- A~B by ID and B~C by URL put A, B, C in one cluster -- so
clustering uses union-find over both keys.

Each cluster keeps one canonical record: the earliest scan (the first time
GDELT saw the article, which is what season assignment should key on),
then the longest stored text, then file name for determinism. The
canonical row gains two traceability fields: source_files and
merged_record_ids.

Two streaming passes, so the article text is never all in memory at once:
pass 1 reads only keys, pass 2 rewrites the canonical rows.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

from dataset_prep.load import BadLine, SourceLine, iter_lines, iter_records
from dataset_prep.union_find import UnionFind

logger = logging.getLogger(__name__)

TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAMS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})
DEFAULT_PORTS = (":80", ":443")


@dataclass(frozen=True)
class RecordRef:
    """Just the keys exact dedup needs from one stored line -- no article text."""
    source_file: str
    line_no: int
    record_id: str
    normalized_url: str
    datetime: str
    text_length: int


def _is_tracking_param(name: str) -> bool:
    lowered = name.lower()
    return lowered in TRACKING_PARAMS or lowered.startswith(TRACKING_PARAM_PREFIXES)


def normalize_url(url: str) -> str:
    """Scheme-less, www-less, lowercase-host form with default ports,
    tracking parameters, fragment and trailing slash removed, and the
    remaining query parameters sorted. Path case is kept -- many sites
    treat it as significant."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    for port in DEFAULT_PORTS:
        host = host.removesuffix(port)
    path = parts.path.rstrip("/")
    kept_params = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking_param(k))
    query = urlencode(kept_params)
    return f"{host}{path}?{query}" if query else f"{host}{path}"


def to_ref(line: SourceLine) -> RecordRef:
    record = line.record
    return RecordRef(
        source_file=line.source_file,
        line_no=line.line_no,
        record_id=record["gkg_record_id"],
        normalized_url=normalize_url(record["url"]),
        datetime=record["datetime"],
        text_length=len(record["article"]),
    )


def cluster_duplicates(refs: list[RecordRef]) -> list[list[int]]:
    """Index groups of refs that share a record ID or normalized URL,
    transitively. Singletons are included."""
    uf = UnionFind(len(refs))
    first_seen: dict[tuple[str, str], int] = {}
    for i, ref in enumerate(refs):
        for key in (("id", ref.record_id), ("url", ref.normalized_url)):
            if key in first_seen:
                uf.union(first_seen[key], i)
            else:
                first_seen[key] = i
    return uf.groups()


def choose_canonical(cluster: list[RecordRef]) -> RecordRef:
    """Earliest scan, then longest text, then file and line for determinism."""
    return min(cluster, key=lambda r: (r.datetime, -r.text_length, r.source_file, r.line_no))


@dataclass(frozen=True)
class CanonicalChoice:
    source_files: tuple[str, ...]
    merged_record_ids: tuple[str, ...]


def plan_dedup(refs: list[RecordRef]) -> dict[tuple[str, int], CanonicalChoice]:
    """(source_file, line_no) of each canonical row -> its traceability fields."""
    plan: dict[tuple[str, int], CanonicalChoice] = {}
    for indices in cluster_duplicates(refs):
        members = [refs[i] for i in indices]
        canonical = choose_canonical(members)
        plan[(canonical.source_file, canonical.line_no)] = CanonicalChoice(
            source_files=tuple(sorted({m.source_file for m in members})),
            merged_record_ids=tuple(sorted({m.record_id for m in members})),
        )
    return plan


def _file_pair_overlaps(plan: dict[tuple[str, int], CanonicalChoice]) -> dict[str, int]:
    """How many clusters each pair of source files shares -- shows which
    runs re-stored the same articles."""
    pairs: Counter[str] = Counter()
    for choice in plan.values():
        for a, b in combinations(choice.source_files, 2):
            pairs[f"{a} | {b}"] += 1
    return dict(pairs.most_common())


def build_report(refs: list[RecordRef], plan: dict[tuple[str, int], CanonicalChoice], bad_lines: int) -> dict:
    canonical_keys = set(plan)
    rows_in = Counter(r.source_file for r in refs)
    rows_kept = Counter(r.source_file for r in refs if (r.source_file, r.line_no) in canonical_keys)
    cluster_sizes = Counter(len(c.merged_record_ids) for c in plan.values())
    return {
        "rows_in": len(refs),
        "bad_lines": bad_lines,
        "rows_out": len(plan),
        "duplicates_removed": len(refs) - len(plan),
        "per_file": {
            name: {"rows_in": rows_in[name], "rows_kept": rows_kept[name]} for name in sorted(rows_in)
        },
        "clusters_by_record_id_count": {str(k): v for k, v in sorted(cluster_sizes.items())},
        "file_pair_overlaps": _file_pair_overlaps(plan),
    }


def dedup_dataset(dataset_dir: Path, out_path: Path) -> dict:
    """Runs both passes and writes the pooled JSONL. Returns the report."""
    refs: list[RecordRef] = []
    bad_lines = 0
    for item in iter_lines(dataset_dir):
        if isinstance(item, BadLine):
            bad_lines += 1
        else:
            refs.append(to_ref(item))
    logger.info("Exact dedup pass 1: %d records read, %d bad lines skipped", len(refs), bad_lines)

    plan = plan_dedup(refs)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out_path.open("w", encoding="utf-8") as out:
        for line in iter_records(dataset_dir):
            choice = plan.get((line.source_file, line.line_no))
            if choice is None:
                continue
            row = {
                **line.record,
                "source_files": list(choice.source_files),
                "merged_record_ids": list(choice.merged_record_ids),
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    logger.info("Exact dedup pass 2: %d canonical records written to %s", written, out_path)

    return build_report(refs, plan, bad_lines)
