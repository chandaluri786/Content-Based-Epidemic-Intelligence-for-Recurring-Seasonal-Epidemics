"""Command-line tool: run the model over articles and save every reply to a run folder.

Examples (from the llm-extractor folder, with the virtual environment active):
    python run_extraction.py --ids Jahnavi:192                   # one article, by its set and row
    python run_extraction.py --ids 20161230170000-2179         # one article, by its id
    python run_extraction.py --ids-file my_ids.txt             # the articles listed in a file
    python run_extraction.py --limit 10                        # the first 10 articles
    python run_extraction.py                                   # every labelled article except the examples
    python run_extraction.py --run-dir results/run_X           # resume an interrupted run
"""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

from flu_extractor import config
from flu_extractor.checks import find_format_errors
from flu_extractor.data_checks import check_input_files
from flu_extractor.data_loading import load_articles, load_gold_labels, resolve_article_id
from flu_extractor.evaluation import default_articles_to_run
from flu_extractor.extractor import extract_article
from flu_extractor.llm_client import create_client
from flu_extractor.prompt import build_prefix_messages, load_examples, load_system_prompt

RAW_LOG_NAME = "raw_results.jsonl"
# Articles sent alone before the workers start, so the prompt prefix is cached first.
WARM_UP_ARTICLES = 1


def read_id_file(path: Path) -> list[str]:
    """Read article ids or set positions (one per line, '#' starts a comment)."""
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
    if record["parse_error"] or record.get("invalid"):
        return True
    return bool(record["parsed"]) and bool(find_format_errors(record["parsed"]))  # logs written before `invalid`


def sha256(path: Path) -> str:
    """Fingerprint of a file, so a run can be traced to the exact prompt text it used."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe_outcome(record: dict) -> str:
    """One line on how an article went, for the progress output."""
    outcome = (record["api_error"] or record["parse_error"]
               or (f"STILL INVALID, {record['invalid']}" if record.get("invalid") else None)
               or f"useful={record['parsed'].get('useful')}")
    outcome += f" (finish={record['finish_reason']}, {record['seconds']}s"
    outcome += f", {record['attempts']} requests" if (record["attempts"] or 1) > 1 else ""
    outcome += ", JSON repaired" if record.get("repaired") else ""
    outcome += f", re-asked {record['validation_retries']}x" if record.get("validation_retries") else ""
    if record.get("cache_hit_tokens") is not None:
        outcome += f", cache hit {record['cache_hit_tokens']}"
    return outcome + ")"


def run_articles(ids: list[str], run_one: Callable[[str], dict], log_file: TextIO,
                 workers: int) -> tuple[list[dict], bool]:
    """Run every article and append each record to the log. Returns (records, stopped early).

    Warm-up: the first WARM_UP_ARTICLES are sent alone, so the shared prefix (rules and examples) is
    in the API's prompt cache before the workers send the rest at once; otherwise every request in the
    first wave would miss the cache. Records are written by this (main) thread only, one line each,
    so the log is never interleaved.
    """
    records: list[dict] = []
    consecutive_api_errors = 0

    def keep(record: dict) -> bool:
        """Log one record; True when the run must stop (many API failures in a row)."""
        nonlocal consecutive_api_errors
        records.append(record)
        log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        log_file.flush()  # keep finished work on disk even if the run is interrupted
        print(f"[{len(records)}/{len(ids)}] {record['article_id']}: {describe_outcome(record)}")
        consecutive_api_errors = consecutive_api_errors + 1 if record["api_error"] else 0
        return consecutive_api_errors >= config.STOP_AFTER_CONSECUTIVE_API_ERRORS

    warm_up, rest = ids[:WARM_UP_ARTICLES], ids[WARM_UP_ARTICLES:]
    for article_id in warm_up:
        if keep(run_one(article_id)):
            return records, True
    if not rest:
        return records, False
    print(f"Warm-up done; sending the other {len(rest)} articles with {workers} workers.")

    # Many API failures in a row usually mean the daily quota is used up: stop instead of failing
    # every remaining article. Finished work is kept; the run can be resumed with --run-dir.
    stopped = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, article_id) for article_id in rest]
        for future in as_completed(futures):
            if future.cancelled():
                continue
            if keep(future.result()) and not stopped:
                stopped = True
                for pending in futures:
                    pending.cancel()
                print(f"Stopping: {consecutive_api_errors} API errors in a row "
                      f"(last: {records[-1]['api_error'][:200]}).")
    return records, stopped


def token_totals(records: list[dict]) -> dict:
    """Prompt-cache, output and thinking tokens added over the records of this session."""
    def total(field: str) -> int:
        return sum(record.get(field) or 0 for record in records)

    return {
        "cache_hit_tokens": total("cache_hit_tokens"),
        "cache_miss_tokens": total("cache_miss_tokens"),
        "completion_tokens": total("completion_tokens"),
        "reasoning_tokens": total("reasoning_tokens"),
        "cache_reported": any(record.get("cache_hit_tokens") is not None for record in records),
    }


def format_token_totals(totals: dict) -> str:
    """The end-of-run token line: did the prompt cache work, and was thinking really off?"""
    line = f"Tokens: output {totals['completion_tokens']:,}, thinking {totals['reasoning_tokens']:,}"
    if not totals["cache_reported"]:
        return line + "; the API reported no cache tokens (only DeepSeek's own API does)."
    prompt = totals["cache_hit_tokens"] + totals["cache_miss_tokens"]
    share = totals["cache_hit_tokens"] / prompt if prompt else 0.0
    return (line + f"; prompt {prompt:,}, of which cache hits {totals['cache_hit_tokens']:,} ({share:.1%})"
                   f" and misses {totals['cache_miss_tokens']:,}.")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", help="articles to run, comma separated: article ids or set positions "
                                      "such as Jahnavi:192. Bypasses the exclusions.")
    parser.add_argument("--ids-file", type=Path,
                        help="text file of articles to run, one per line ('#' starts a comment). "
                             "Example articles are still left out.")
    parser.add_argument("--limit", type=int, help="run only the first N of the selected articles.")
    parser.add_argument("--exclude-file", type=Path,
                        help="text file of extra articles to leave out (one per line).")
    parser.add_argument("--workers", type=int, default=16,
                        help="requests waiting for a reply at the same time (default 16). Replies take minutes, "
                             "so several are needed in flight; the 40-per-minute limit holds for any value.")
    parser.add_argument("--run-dir", type=Path,
                        help="existing run folder to resume; default is a new timestamped folder.")
    parser.add_argument("--retry-invalid", action="store_true",
                        help="when resuming, also rerun articles whose reply was still invalid after the retries.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()

    # Stop before any API call if the input files are not in the format the pipeline and the prompt need.
    problems = check_input_files(config.ARTICLES_PATH, config.GOLD_LABELS_PATH, config.EXAMPLES_PATH)
    if problems:
        raise SystemExit(f"The input files have {len(problems)} problems, e.g.:\n" + "\n".join(problems[:20]))
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
        ids = default_articles_to_run(articles, gold, example_ids, excluded)
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
        "example_count": len(examples), "temperature": config.TEMPERATURE, "top_p": config.TOP_P,
        "max_tokens": config.MAX_TOKENS,
        "extra_body": config.EXTRA_BODY, "seed": config.SEED, "max_validation_retries": config.MAX_VALIDATION_RETRIES,
        "requests_per_minute": config.REQUESTS_PER_MINUTE,
        "selection": "ids" if args.ids else ("ids_file" if args.ids_file else "all labelled articles except the examples"),
        "ids_file": str(args.ids_file) if args.ids_file else None,
        "started": datetime.now().isoformat(timespec="seconds"), "articles_requested_this_session": len(ids),
    }, indent=2), encoding="utf-8")

    print(f"Run folder: {run_dir}\nModel: {config.MODEL_ID}\nArticles to run: {len(ids)} "
          f"(left out as few-shot examples: {len(example_ids)})\n"
          f"Rate limit: {config.REQUESTS_PER_MINUTE} requests per minute, so {len(ids)} calls take at least "
          f"{len(ids) / config.REQUESTS_PER_MINUTE:.1f} minutes")
    if not ids:
        return

    # The instructions and the examples are the same for every article, so build them once.
    fewshot_guide = load_system_prompt(config.FEWSHOT_GUIDE_PATH) if use_guide else ""
    prefix_messages = build_prefix_messages(load_system_prompt(config.SYSTEM_PROMPT_PATH), examples, fewshot_guide)
    client = create_client()

    def run_one(article_id: str) -> dict:
        return extract_article(client, prefix_messages, articles[article_id])

    with log_path.open("a", encoding="utf-8") as log_file:
        records, stopped = run_articles(ids, run_one, log_file, args.workers)
    print(format_token_totals(token_totals(records)))
    if stopped:
        print(f"Resume with: python run_extraction.py --run-dir {run_dir} (same options)")
    else:
        print(f"Done. Now run: python evaluate_run.py {run_dir}")


if __name__ == "__main__":
    main()
