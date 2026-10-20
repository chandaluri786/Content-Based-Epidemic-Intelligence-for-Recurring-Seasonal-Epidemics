"""Command-line tool: run the model over articles and save every reply to a run folder.

Examples (from the llm-extractor folder, with the virtual environment active):
    python run_extraction.py --ids 20161230170000-2179      # one chosen article
    python run_extraction.py --ids @my_ids.txt              # the articles listed in a file
    python run_extraction.py --limit 10                     # first 10 dev articles
    python run_extraction.py                                # all dev articles
    python run_extraction.py --run-dir results/run_X        # resume an interrupted run
    python run_extraction.py --split test --final           # the one-time test run, after tuning

Tuning uses dev only. Test articles run only with --final, and never with a prompt whose examples
include a test article.
"""

import argparse
import json
from collections import Counter
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from flu_extractor import config
from flu_extractor.data_loading import DEV, SPLITS, TEST, Article, load_articles, load_human_labels
from flu_extractor.evaluation import RUN_CONFIG_NAME, default_ids_to_run, read_run_settings, settings_mismatch
from flu_extractor.extractor import extract_article
from flu_extractor.llm_client import create_client
from flu_extractor.pacing import Pacer, RateLimitStop
from flu_extractor.prompt import build_prefix_messages, load_examples, load_system_prompt

RAW_LOG_NAME = "raw_results.jsonl"


def read_id_file(path: Path) -> list[str]:
    """Read article IDs, one per line ('#' starts a comment)."""
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            ids.append(line)
    return ids


def parse_id_spec(spec: str) -> list[str]:
    """Turn 'a,b' into ['a', 'b'], or '@file.txt' into the IDs listed in that file."""
    if spec.startswith("@"):
        return read_id_file(Path(spec[1:]))
    return [part.strip() for part in spec.split(",") if part.strip()]


def ids_already_done(log_path: Path) -> set[str]:
    """Articles in an existing log that got a reply (failed calls are retried on resume)."""
    done = set()
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                if not record["api_error"]:
                    done.add(record["article_id"])
    return done


def check_test_guard(ids: list[str], articles: dict[str, Article], example_ids: frozenset[str],
                     is_final: bool) -> None:
    """Stop unless test articles are run on purpose, with a prompt that has never seen one."""
    test_ids = [i for i in ids if articles[i].split == TEST]
    if not test_ids:
        return
    if not is_final:
        raise SystemExit(f"{len(test_ids)} of the chosen articles are test articles (e.g. {test_ids[0]}). "
                         "Test is run once, after tuning: add --final to do that.")
    examples_in_test = sorted(i for i in example_ids if i in articles and articles[i].split == TEST)
    if examples_in_test:
        raise SystemExit(f"{len(examples_in_test)} of the prompt's examples are test articles "
                         f"(e.g. {examples_in_test[0]}), so a test score would not be fair. "
                         "Use a prompt whose examples come from dev only.")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", help="articles to run: 'id1,id2' or '@file' (one ID per line). "
                                      "Default: every article of --split except the prompt's examples.")
    parser.add_argument("--split", choices=SPLITS, default=DEV,
                        help="which split to run when --ids is not given (default dev).")
    parser.add_argument("--final", action="store_true",
                        help="allow test articles. Use it once, for the final test run after tuning.")
    parser.add_argument("--limit", type=int, help="run only the first N of the selected articles.")
    parser.add_argument("--exclude-file", type=Path,
                        help="text file of extra article IDs to leave out (one per line).")
    parser.add_argument("--calls-per-minute", type=int, default=config.CALLS_PER_MINUTE,
                        help=f"at most this many calls start in any 60 s (default {config.CALLS_PER_MINUTE}, "
                             "or CALLS_PER_MINUTE in .env); it halves by itself after a rate limit")
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

    # Without --ids we run every article of the split except the ones whose answers are the
    # prompt's own examples and any named in --exclude-file.
    example_ids = frozenset(example["article_id"] for example in examples)
    extra_excluded = frozenset(read_id_file(args.exclude_file)) if args.exclude_file else frozenset()
    ids = parse_id_spec(args.ids) if args.ids else default_ids_to_run(labels, args.split, example_ids,
                                                                      extra_excluded)
    unknown = [i for i in ids if i not in articles]
    if unknown:
        raise SystemExit(f"Unknown article IDs: {', '.join(unknown[:10])}")
    check_test_guard(ids, articles, example_ids, args.final)
    if args.limit:
        ids = ids[: args.limit]

    run_dir = args.run_dir or config.RESULTS_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}"
    settings = {"system_prompt": config.SYSTEM_PROMPT_PATH.name, "examples": config.EXAMPLES_PATH.name,
                "labels": config.HUMAN_LABELS_PATH.name}
    mismatch = settings_mismatch(read_run_settings(run_dir), settings)
    if mismatch:
        raise SystemExit(f"{run_dir} was made with other settings, so resuming would mix them:\n  "
                         + "\n  ".join(mismatch) + "\nSet PROMPT_VERSION / HUMAN_LABELS_PATH to match the run.")
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / RAW_LOG_NAME
    done = ids_already_done(log_path)
    ids = [i for i in ids if i not in done]
    (run_dir / RUN_CONFIG_NAME).write_text(json.dumps({
        "model": config.MODEL_ID, **settings, "temperature": config.TEMPERATURE,
        "max_tokens": config.MAX_TOKENS, "started": datetime.now().isoformat(timespec="seconds"),
        "articles_by_split": dict(Counter(articles[i].split for i in ids)),
        "examples_by_split": dict(Counter(articles[i].split for i in example_ids if i in articles)),
        "final": args.final,
        "articles_requested_this_session": len(ids),
    }, indent=2), encoding="utf-8")

    print(f"Run folder: {run_dir}\nArticles to run: {len(ids)}")
    if not ids:
        return

    # The instructions and the examples are the same for every article, so build them once.
    prefix_messages = build_prefix_messages(load_system_prompt(config.SYSTEM_PROMPT_PATH), examples)
    client = create_client()
    pacer = Pacer(args.calls_per_minute)
    print(f"Pacing: at most {args.calls_per_minute} calls start per minute, {args.workers} workers")

    # Replies are written by this (main) thread only, one line each, so the log is never interleaved.
    stopped = None
    with ThreadPoolExecutor(max_workers=args.workers) as pool, \
            log_path.open("a", encoding="utf-8") as log_file:
        futures = [pool.submit(extract_article, client, prefix_messages, articles[i], pacer) for i in ids]
        for number, future in enumerate(as_completed(futures), start=1):
            try:
                record = future.result()
            except RateLimitStop as error:
                stopped = stopped or error
                pool.shutdown(wait=False, cancel_futures=True)  # articles not started are not logged
                continue
            except CancelledError:
                continue
            log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            log_file.flush()  # keep finished work on disk even if the run is interrupted
            outcome = record["api_error"] or record["parse_error"] or \
                f"useful={record['parsed']['useful']}"
            print(f"[{number}/{len(ids)}] {record['article_id']}: {outcome} ({record['seconds']}s)")

    if stopped:
        print(f"STOPPED: {stopped}. Finished replies are saved. Resume later with:\n"
              f"  python run_extraction.py --run-dir {run_dir}")
        raise SystemExit(2)
    print(f"Done. Now run: python evaluate_run.py {run_dir}")


if __name__ == "__main__":
    main()
