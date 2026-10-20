"""Build the two active prompt files for one prompt version.

    python scripts/build_prompt_files.py v2.1
    python scripts/build_prompt_files.py v4.1 --labels data/human_labels_jahnavi.json

Reads
    prompt_versions/llm_extraction_prompt_<version>.md   the instructions (the code fence under "## 1. Instructions")
    prompt_versions/examples_<version>_selection.json    which dev articles are the examples, and why
    data/articles.json, data/human_labels.json           the article texts and the human answers
                                                          (--labels: another label set's answers)
Writes
    prompts/system_prompt_<version>.txt
    prompts/examples_<version>.json

Each example's answer is copied from data/human_labels.json, so it always equals the human label.
The selection file only adds what the labels do not have: `teaches` (a note for people), `reason`
(one sentence, sent to the model), optionally `borderline` (default false) and `keep_lines` (the
line numbers to keep when an article is trimmed; "[article trimmed]" is added at the end).
Nothing is written if a check fails.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from build_data_files import extract_system_prompt

PROJECT_DIR = Path(__file__).resolve().parent.parent
TRIM_MARK = "[article trimmed]"
# Examples must be about half useful and half not useful (the agreed mix).
MAX_MIX_GAP = 2
# Rough size estimate: about 4 characters per token for English text.
CHARS_PER_TOKEN = 4


def trim_article(text: str, keep_lines: list[int] | None) -> str:
    """The article, or only the chosen lines of it followed by the trim mark."""
    if not keep_lines:
        return text
    lines = text.split("\n")
    return "\n".join([lines[n] for n in keep_lines] + [TRIM_MARK])


def build_example(number: int, entry: dict, article: dict, label: dict) -> dict:
    """One example in the shape prompt.py sends: the article block and the answer as JSON."""
    return {
        "example": number,
        "article_id": entry["article_id"],
        "teaches": entry["teaches"],
        "scan_date": article["scan_date"],
        "link": article["link"],
        "article": trim_article(article["article"], entry.get("keep_lines")),
        "answer": {
            "useful": label["useful"],
            "borderline": entry.get("borderline", False),
            "reason": entry["reason"],
            "items": label["items"],
        },
    }


def _squash(text: str) -> str:
    return " ".join(text.split())


def example_problems(selection: list[dict], examples: list[dict], splits: dict[str, str]) -> list[str]:
    """Every reason the examples cannot be used (empty list = they can)."""
    problems = []
    repeated = [i for i, n in Counter(e["article_id"] for e in selection).items() if n > 1]
    problems += [f"{i} is chosen more than once" for i in repeated]
    for entry, example in zip(selection, examples):
        article_id = entry["article_id"]
        if splits[article_id] != "dev":
            problems.append(f"{article_id} is a {splits[article_id]} article; examples must come from dev")
        if not entry.get("teaches") or not entry.get("reason"):
            problems.append(f"{article_id} needs both 'teaches' and 'reason'")
        text = _squash(example["article"])
        for item in example["answer"]["items"]:
            problems += [f"{article_id}: evidence not in the (trimmed) article: {quote[:60]!r}"
                         for quote in item["evidence"] if _squash(quote) not in text]
    useful = sum(e["answer"]["useful"] for e in examples)
    if abs(useful - (len(examples) - useful)) > MAX_MIX_GAP:
        problems.append(f"{useful} useful and {len(examples) - useful} not useful; keep them about even")
    return problems


DEFAULT_LABELS = PROJECT_DIR / "data" / "human_labels.json"


def load_examples(version: str, labels_path: Path = DEFAULT_LABELS) -> list[dict]:
    """Build the examples of one version from its selection file; stop with a list if any check fails.

    Each answer is copied from labels_path, so a second label set gives its own answers."""
    selection = json.loads((PROJECT_DIR / "prompt_versions" / f"examples_{version}_selection.json")
                           .read_text(encoding="utf-8"))
    articles = {a["article_id"]: a for a in json.loads((PROJECT_DIR / "data" / "articles.json")
                                                       .read_text(encoding="utf-8"))}
    labels = {a["article_id"]: a for a in json.loads(labels_path.read_text(encoding="utf-8"))}
    unknown = [e["article_id"] for e in selection if e["article_id"] not in articles]
    if unknown:
        raise SystemExit(f"Not in data/articles.json: {', '.join(unknown)}")
    examples = [build_example(n, entry, articles[entry["article_id"]], labels[entry["article_id"]])
                for n, entry in enumerate(selection, start=1)]
    problems = example_problems(selection, examples, {i: a["split"] for i, a in articles.items()})
    if problems:
        raise SystemExit("The examples do not pass the checks; nothing was written.\n  " + "\n  ".join(problems))
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", help="the prompt version, e.g. v2.1")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS,
                        help="labels file the example answers come from (default: data/human_labels.json)")
    args = parser.parse_args()
    version = args.version

    system_prompt = extract_system_prompt(
        (PROJECT_DIR / "prompt_versions" / f"llm_extraction_prompt_{version}.md").read_text(encoding="utf-8"))
    examples = load_examples(version, args.labels.resolve())

    prompts = PROJECT_DIR / "prompts"
    (prompts / f"system_prompt_{version}.txt").write_text(system_prompt, encoding="utf-8")
    examples_text = json.dumps(examples, indent=2, ensure_ascii=False) + "\n"
    (prompts / f"examples_{version}.json").write_text(examples_text, encoding="utf-8")

    useful = sum(e["answer"]["useful"] for e in examples)
    sent = len(system_prompt) + sum(len(e["article"]) + len(json.dumps(e["answer"], ensure_ascii=False))
                                    for e in examples)
    print(f"wrote prompts/system_prompt_{version}.txt and prompts/examples_{version}.json")
    print(f"  answers from {args.labels.name}")
    print(f"  {len(examples)} examples: {useful} useful, {len(examples) - useful} not useful, all from dev")
    print(f"  about {sent // CHARS_PER_TOKEN:,} tokens sent before each article")


if __name__ == "__main__":
    main()
