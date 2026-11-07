"""Combine several run folders into one reply per article, e.g. a pool run split over providers.

The run folders are read in the order given; later folders win. For each article:
- a record with an API error is never used (it has no reply);
- within one folder, the last line of an article is its record (as on resume);
- a later folder's reply replaces the current one only when it is valid, or when there is none yet.
  So a rerun fixes an invalid reply, but a rerun that is still invalid keeps the earlier one.

Each output record is the input record plus `source_run` (the folder it came from) and `status`:
valid, invalid_but_kept (a reply with an answer that failed a format check) or no_answer (cut off or
unparseable). The run folders are not changed. With --articles-file, the result must cover exactly
those articles, or nothing is written.

    python scripts/combine_runs.py --out results/pool_combined \\
        --articles-file ../usefulness_filter/output/pool_articles.json \\
        results/run_20261106_202656 results/run_20261106_215942 results/run_20261107_085642 ...
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flu_extractor.checks import record_is_invalid  # noqa: E402

RAW_LOG_NAME = "raw_results.jsonl"
VALID, INVALID_KEPT, NO_ANSWER = "valid", "invalid_but_kept", "no_answer"


def status_of(record: dict) -> str:
    if not record_is_invalid(record):
        return VALID
    return INVALID_KEPT if record.get("parsed") else NO_ANSWER


def latest_replies(run_dir: Path) -> dict[str, dict]:
    """{article_id: last record with a reply} of one run folder."""
    log_path = run_dir / RAW_LOG_NAME
    if not log_path.exists():
        raise FileNotFoundError(f"no {RAW_LOG_NAME} in {run_dir}")
    latest: dict[str, dict] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            latest[record["article_id"]] = record
    return {article_id: record for article_id, record in latest.items() if not record.get("api_error")}


def combine(run_dirs: list[Path]) -> dict[str, dict]:
    """{article_id: chosen record + source_run + status}, following the rules in the module doc."""
    combined: dict[str, dict] = {}
    for run_dir in run_dirs:
        for article_id, record in latest_replies(run_dir).items():
            status = status_of(record)
            if article_id in combined and status != VALID:
                continue
            combined[article_id] = {**record, "source_run": run_dir.name, "status": status}
    return combined


def coverage_problems(combined: dict[str, dict], expected_ids: list[str]) -> list[str]:
    expected = set(expected_ids)
    missing, extra = expected - set(combined), set(combined) - expected
    problems = []
    if missing:
        problems.append(f"{len(missing)} articles have no reply, e.g. {sorted(missing)[:5]}")
    if extra:
        problems.append(f"{len(extra)} replies are for articles not in the articles file, e.g. {sorted(extra)[:5]}")
    return problems


def summarise(combined: dict[str, dict]) -> dict:
    records = combined.values()
    return {"articles": len(combined),
            "by_source_run": dict(Counter(r["source_run"] for r in records)),
            "by_status": dict(Counter(r["status"] for r in records)),
            "useful": sum(bool(r["parsed"] and r["parsed"].get("useful")) for r in records),
            "items": sum(len((r["parsed"] or {}).get("items") or []) for r in records)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dirs", nargs="+", type=Path, help="run folders, lowest priority first")
    parser.add_argument("--out", type=Path, required=True, help="folder to write raw_results.jsonl and summary.json")
    parser.add_argument("--articles-file", type=Path, help="the result must cover exactly these articles")
    args = parser.parse_args()

    combined = combine(args.run_dirs)
    if args.articles_file:
        expected = [a["article_id"] for a in json.loads(args.articles_file.read_text(encoding="utf-8"))]
        problems = coverage_problems(combined, expected)
        if problems:
            print("stopped, nothing written:\n" + "\n".join(problems))
            return 1
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / RAW_LOG_NAME).open("w", encoding="utf-8") as out:
        for article_id in sorted(combined):
            out.write(json.dumps(combined[article_id], ensure_ascii=False) + "\n")
    summary = {**summarise(combined), "run_dirs": [str(d) for d in args.run_dirs],
               "articles_file": str(args.articles_file) if args.articles_file else None}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
