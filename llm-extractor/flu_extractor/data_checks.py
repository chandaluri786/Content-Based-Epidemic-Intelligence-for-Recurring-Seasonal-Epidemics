"""Check that the input files are in the format the pipeline and prompt need.

    data/articles.json        list of {article_id, scan_date, link, sources, article}
    data/gold_labels.json     list of {article_id, useful, labelers, items}, one per article in articles.json
    prompts/examples_*.json   list of {article_id, source, slots, scan_date, link, article, answer}

The gold items and the example answers are checked with the same code as the model's replies
(checks.py): the reply format with every fixed value, and every evidence quote copied exactly
from its article. A few-shot example teaches the model, so its answer must also follow "How to
work" (Step 0, then Step 1 citing Rule 1), and its article must be the same text as in
articles.json.

scripts/build_gold_files.py stops if its output fails these checks, and run_extraction.py stops
before any API call if the files it would send fail them.
"""

import json
from pathlib import Path

from flu_extractor.checks import is_iso_date, find_evidence_errors, find_format_errors

ARTICLE_KEYS = ("article_id", "scan_date", "link", "sources", "article")
GOLD_KEYS = ("article_id", "useful", "labelers", "items")
EXAMPLE_KEYS = ("article_id", "scan_date", "link", "article", "answer")


def check_articles(articles: list) -> list[str]:
    problems = []
    if not isinstance(articles, list) or not articles:
        return ["articles.json must be a non-empty list"]
    seen = set()
    for record in articles:
        missing = [key for key in ARTICLE_KEYS if key not in record]
        name = record.get("article_id", "?")
        if missing:
            problems.append(f"article {name}: missing {', '.join(missing)}")
            continue
        if name in seen:
            problems.append(f"article {name}: appears twice (every article must be unique)")
        seen.add(name)
        if not is_iso_date(record["scan_date"]):
            problems.append(f"article {name}: scan_date {record['scan_date']!r} is not YYYY-MM-DD")
        if not (isinstance(record["article"], str) and record["article"].strip()):
            problems.append(f"article {name}: the article text is empty")
        if not (isinstance(record["link"], str) and isinstance(record["sources"], list)):
            problems.append(f"article {name}: link must be text and sources a list")
    return problems


def check_gold(gold: list, articles: list) -> list[str]:
    texts = {a["article_id"]: a["article"] for a in articles}
    problems = []
    seen = set()
    for record in gold:
        missing = [key for key in GOLD_KEYS if key not in record]
        name = record.get("article_id", "?")
        if missing:
            problems.append(f"gold {name}: missing {', '.join(missing)}")
            continue
        if name in seen:
            problems.append(f"gold {name}: appears twice")
        seen.add(name)
        if name not in texts:
            problems.append(f"gold {name}: has no article in articles.json")
            continue
        as_reply = {"summary": "gold", "reasoning": ["Step 0 (summary): gold"], "useful": record["useful"],
                    "reason": "gold", "items": record["items"]}
        errors = find_format_errors(as_reply)
        if not errors:
            errors = find_evidence_errors(as_reply, texts[name])
        problems += [f"gold {name}: {error}" for error in errors]
    return problems


def check_examples(examples: list, articles: list) -> list[str]:
    texts = {a["article_id"]: a["article"] for a in articles}
    problems = []
    if not isinstance(examples, list):
        return ["the examples file must be a list"]
    for example in examples:
        missing = [key for key in EXAMPLE_KEYS if key not in example]
        name = example.get("source") or example.get("article_id", "?")
        if missing:
            problems.append(f"example {name}: missing {', '.join(missing)}")
            continue
        answer = example["answer"]
        errors = find_format_errors(answer)
        if not errors:
            errors = find_evidence_errors(answer, example["article"])
            steps = answer["reasoning"]
            if not (steps[0].startswith("Step 0") and len(steps) > 1 and steps[1].startswith("Step 1 (Rule 1)")):
                errors.append("reasoning must begin with Step 0 and a Step 1 citing Rule 1 (How to work)")
        if example["article_id"] in texts and texts[example["article_id"]] != example["article"]:
            errors.append("its article text differs from the same article in articles.json")
        problems += [f"example {name}: {error}" for error in errors]
    return problems


def check_input_files(articles_path: Path, gold_path: Path | None, examples_path: Path) -> list[str]:
    """All problems with the input files; an empty list means they are ready to use.

    gold_path is None for articles that have no gold labels (a run on the pool): then only the
    articles and the examples are checked."""
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))  # noqa: E731
    articles = read(articles_path)
    problems = check_articles(articles)
    if problems:
        return problems
    gold_problems = check_gold(read(gold_path), articles) if gold_path is not None else []
    return gold_problems + check_examples(read(examples_path), articles)
