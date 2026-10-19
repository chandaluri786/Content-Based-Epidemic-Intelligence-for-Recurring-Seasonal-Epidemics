"""Command-line tool: run the model over articles and save every reply to a run folder.

Examples (from the llm-extractor folder, with the virtual environment active):
    python run_extraction.py --rows 1,3,47           # three chosen rows
    python run_extraction.py --limit 10              # first 10 development rows
    python run_extraction.py                         # all development rows
    python run_extraction.py --run-dir results/run_X # resume an interrupted run
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from flu_extractor import config
from flu_extractor.data_loading import load_articles, load_human_labels
from flu_extractor.evaluation import default_rows_to_run
from flu_extractor.extractor import extract_article
from flu_extractor.llm_client import create_client
from flu_extractor.prompt import build_prefix_messages, load_examples, load_system_prompt

RAW_LOG_NAME = "raw_results.jsonl"


def parse_row_spec(spec: str) -> list[int]:
    """Turn '1-3,47' into [1, 2, 3, 47]."""
    rows: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            low, high = part.split("-")
            rows.extend(range(int(low), int(high) + 1))
        elif part:
            rows.append(int(part))
    return rows


def read_row_numbers(path: Path) -> frozenset[int]:
    """Read row numbers (one per line, '#' starts a comment), e.g. the locked test-set list."""
    numbers = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            numbers.add(int(line))
    return frozenset(numbers)


def rows_already_done(log_path: Path) -> set[int]:
    """Rows in an existing log that got a reply (failed calls are retried on resume)."""
    done = set()
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                if not record["api_error"]:
                    done.add(record["row"])
    return done


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", help="rows to run, e.g. '1-20,47'. Default: all development rows.")
    parser.add_argument("--limit", type=int, help="run only the first N of the selected rows.")
    parser.add_argument("--exclude-file", type=Path,
                        help="text file of extra row numbers to leave out (one per line).")
    parser.add_argument("--workers", type=int, default=3,
                        help="parallel requests (default 3). Lower it if you hit rate limits.")
    parser.add_argument("--run-dir", type=Path,
                        help="existing run folder to resume; default is a new timestamped folder.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()

    articles = load_articles(config.ARTICLES_PATH)
    labels = load_human_labels(config.HUMAN_LABELS_PATH)
    examples = load_examples(config.EXAMPLES_PATH)

    # Without --rows we run every row except: unlabeled, needs_relook, the rows whose answers
    # are the prompt's own examples, and any rows named in --exclude-file.
    example_rows = frozenset(example["source_row"] for example in examples)
    extra_excluded = read_row_numbers(args.exclude_file) if args.exclude_file else frozenset()
    rows = parse_row_spec(args.rows) if args.rows else default_rows_to_run(labels, example_rows, extra_excluded)
    if args.limit:
        rows = rows[: args.limit]

    run_dir = args.run_dir or config.RESULTS_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / RAW_LOG_NAME
    rows = [row for row in rows if row not in rows_already_done(log_path)]
    (run_dir / "run_config.json").write_text(json.dumps({
        "model": config.MODEL_ID, "system_prompt": config.SYSTEM_PROMPT_PATH.name,
        "examples": config.EXAMPLES_PATH.name, "temperature": config.TEMPERATURE,
        "max_tokens": config.MAX_TOKENS, "started": datetime.now().isoformat(timespec="seconds"),
        "rows_requested_this_session": len(rows),
    }, indent=2), encoding="utf-8")

    print(f"Run folder: {run_dir}\nArticles to run: {len(rows)}")
    if not rows:
        return

    # The instructions and the examples are the same for every article, so build them once.
    prefix_messages = build_prefix_messages(load_system_prompt(config.SYSTEM_PROMPT_PATH), examples)
    client = create_client()

    # Replies are written by this (main) thread only, one line each, so the log is never interleaved.
    with ThreadPoolExecutor(max_workers=args.workers) as pool, \
            log_path.open("a", encoding="utf-8") as log_file:
        futures = [pool.submit(extract_article, client, prefix_messages, articles[row]) for row in rows]
        for number, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            log_file.flush()  # keep finished work on disk even if the run is interrupted
            outcome = record["api_error"] or record["parse_error"] or \
                f"useful={record['parsed']['useful']}"
            print(f"[{number}/{len(rows)}] row {record['row']}: {outcome} ({record['seconds']}s)")

    print(f"Done. Now run: python evaluate_run.py {run_dir}")


if __name__ == "__main__":
    main()
