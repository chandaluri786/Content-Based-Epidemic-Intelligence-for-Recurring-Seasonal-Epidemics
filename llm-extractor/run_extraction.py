"""Command-line tool: run the model over articles and save every reply to a run folder.

Examples (from the llm-extractor folder, with the virtual environment active):
    python run_extraction.py --ids Jahnavi:6                   # one article, by its set and row
    python run_extraction.py --ids 20161230170000-2179         # one article, by its id
    python run_extraction.py --ids-file data/dev_sample_200.txt  # the development sample D
    python run_extraction.py --limit 10                        # first 10 dev articles
    python run_extraction.py                                   # every labelled article except the examples
    python run_extraction.py --run-dir results/run_X           # resume an interrupted run
"""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from flu_extractor import config
from flu_extractor.checks import find_shape_errors
from flu_extractor.data_loading import ALL, DEV, TEST, load_articles, load_gold_labels, resolve_article_id
from flu_extractor.evaluation import default_articles_to_run
from flu_extractor.extractor import extract_article
from flu_extractor.llm_client import create_client
from flu_extractor.prompt import build_prefix_messages, load_examples, load_system_prompt

RAW_LOG_NAME = "raw_results.jsonl"


def read_id_file(path: Path) -> list[str]:
    """Read article ids or set positions (one per line, '#' starts a comment), e.g. the dev sample."""
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            ids.append(line)
    return ids


def ids_already_done(log_path: Path, retry_invalid: bool = False) -> set[str]:
    """Articles in an existing log that got a reply (failed calls are retried on resume).

    With retry_invalid, articles whose last reply was still invalid are run again as well. A later
    line replaces an earlier one, so the latest record of each article decides.
    """
    latest = {}
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                latest[record["article_id"]] = record
    return {article_id for article_id, record in latest.items()
            if not record["api_error"] and not (retry_invalid and _still_invalid(record))}


def _still_invalid(record: dict) -> bool:
    """The record's last reply was cut off, unparseable or malformed after all its retries."""
    if record.get("gated"):
        return False
    if record["parse_error"] or record.get("invalid"):
        return True
    return bool(record["parsed"]) and bool(find_shape_errors(record["parsed"]))  # logs written before `invalid`


def sha256(path: Path) -> str:
    """Fingerprint of a file, so a run can be traced to the exact prompt text it used."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", help="articles to run, comma separated: article ids or set positions "
                                      "such as Jahnavi:6. Bypasses the split and the exclusions.")
    parser.add_argument("--ids-file", type=Path,
                        help="text file of articles to run, one per line (e.g. data/dev_sample_200.txt). "
                             "Example articles are still left out.")
    parser.add_argument("--split", choices=(ALL, DEV, TEST), default=ALL,
                        help="articles to run when no ids are given (default: all, one set of every labelled "
                             "article). dev or test runs only that part.")
    parser.add_argument("--limit", type=int, help="run only the first N of the selected articles.")
    parser.add_argument("--exclude-file", type=Path,
                        help="text file of extra articles to leave out (one per line).")
    parser.add_argument("--workers", type=int, default=3,
                        help="parallel requests (default 3). Lower it if you hit rate limits.")
    parser.add_argument("--run-dir", type=Path,
                        help="existing run folder to resume; default is a new timestamped folder.")
    parser.add_argument("--retry-invalid", action="store_true",
                        help="when resuming, also rerun articles whose reply was still invalid after the retries.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()

    articles = load_articles(config.ARTICLES_PATH)
    gold = load_gold_labels(config.GOLD_LABELS_PATH)
    examples = load_examples(config.EXAMPLES_PATH)

    # The examples' answers are in the prompt, so those articles are never scored.
    example_ids = frozenset(example["article_id"] for example in examples)
    excluded = frozenset(resolve_article_id(s, articles) for s in read_id_file(args.exclude_file)) \
        if args.exclude_file else frozenset()
    if args.ids:
        ids = [resolve_article_id(s.strip(), articles) for s in args.ids.split(",") if s.strip()]
    elif args.ids_file:
        ids = [a for a in (resolve_article_id(s, articles) for s in read_id_file(args.ids_file))
               if a not in example_ids | excluded]
    else:
        ids = default_articles_to_run(articles, gold, args.split, example_ids, excluded)
    if args.limit:
        ids = ids[: args.limit]

    run_dir = args.run_dir or config.RESULTS_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / RAW_LOG_NAME
    done = ids_already_done(log_path, args.retry_invalid)
    ids = [a for a in ids if a not in done]
    # The guide is sent only with examples, so a zero-shot run records none.
    use_guide = bool(examples) and config.FEWSHOT_GUIDE_PATH.exists()
    (run_dir / "run_config.json").write_text(json.dumps({
        "model": config.MODEL_ID, "base_url": config.BASE_URL,
        "system_prompt": config.SYSTEM_PROMPT_PATH.name, "system_prompt_sha256": sha256(config.SYSTEM_PROMPT_PATH),
        "examples": config.EXAMPLES_PATH.name, "examples_sha256": sha256(config.EXAMPLES_PATH),
        "fewshot_guide": config.FEWSHOT_GUIDE_PATH.name if use_guide else None,
        "fewshot_guide_sha256": sha256(config.FEWSHOT_GUIDE_PATH) if use_guide else None,
        "example_count": len(examples), "temperature": config.TEMPERATURE, "max_tokens": config.MAX_TOKENS,
        "extra_body": config.EXTRA_BODY, "seed": config.SEED, "max_validation_retries": config.MAX_VALIDATION_RETRIES,
        "requests_per_minute": config.REQUESTS_PER_MINUTE, "split": None if (args.ids or args.ids_file) else args.split,
        "ids_file": str(args.ids_file) if args.ids_file else None,
        "started": datetime.now().isoformat(timespec="seconds"), "articles_requested_this_session": len(ids),
    }, indent=2), encoding="utf-8")

    gated = sum(not articles[a].passes_keyword_gate for a in ids)
    calls = len(ids) - gated
    print(f"Run folder: {run_dir}\nArticles to run: {len(ids)} ({gated} fail the keyword gate: no API call)\n"
          f"Rate limit: {config.REQUESTS_PER_MINUTE} requests per minute, so {calls} calls take at least "
          f"{calls / config.REQUESTS_PER_MINUTE:.1f} minutes")
    if not ids:
        return

    # The instructions and the examples are the same for every article, so build them once.
    fewshot_guide = load_system_prompt(config.FEWSHOT_GUIDE_PATH) if use_guide else ""
    prefix_messages = build_prefix_messages(load_system_prompt(config.SYSTEM_PROMPT_PATH), examples, fewshot_guide)
    client = create_client()

    # Replies are written by this (main) thread only, one line each, so the log is never interleaved.
    consecutive_api_errors, stopped = 0, False
    with ThreadPoolExecutor(max_workers=args.workers) as pool, \
            log_path.open("a", encoding="utf-8") as log_file:
        futures = [pool.submit(extract_article, client, prefix_messages, articles[a]) for a in ids]
        for number, future in enumerate(as_completed(futures), start=1):
            if future.cancelled():
                continue
            record = future.result()
            log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            log_file.flush()  # keep finished work on disk even if the run is interrupted
            if record["gated"]:
                outcome = "fails the keyword gate, Rule 1 reply written by code"
            else:
                outcome = (record["api_error"] or record["parse_error"]
                           or (f"STILL INVALID, {record['invalid']}" if record.get("invalid") else None)
                           or f"useful={record['parsed'].get('useful')}")
                outcome += f" (finish={record['finish_reason']}, {record['seconds']}s"
                outcome += f", {record['attempts']} requests" if (record["attempts"] or 1) > 1 else ""
                outcome += ", JSON repaired" if record.get("repaired") else ""
                outcome += f", re-asked {record['validation_retries']}x" if record.get("validation_retries") else ""
                outcome += ")"
            print(f"[{number}/{len(ids)}] {record['article_id']}: {outcome}")

            # Many API failures in a row usually mean the daily quota is used up: stop instead of
            # failing every remaining article. Finished work is kept; resume later with --run-dir.
            consecutive_api_errors = consecutive_api_errors + 1 if record["api_error"] else 0
            if consecutive_api_errors >= config.STOP_AFTER_CONSECUTIVE_API_ERRORS and not stopped:
                stopped = True
                for pending in futures:
                    pending.cancel()
                print(f"Stopping: {consecutive_api_errors} API errors in a row (last: {record['api_error'][:200]}). "
                      f"Resume with: python run_extraction.py --run-dir {run_dir} (same options)")

    if not stopped:
        print(f"Done. Now run: python evaluate_run.py {run_dir}")


if __name__ == "__main__":
    main()
