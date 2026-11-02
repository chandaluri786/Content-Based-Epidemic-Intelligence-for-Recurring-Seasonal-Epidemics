"""Copy the capstone source files into this project as JSON, keyed by article id.

The extractor itself reads only files inside this folder (`prompts/` and `data/`).
Run this script when the sources change, for example after more chain-of-thought records
were written. It is the only code that knows where the capstone files live.

    python scripts/build_gold_files.py [--capstone-dir PATH] [--labeling-dir PATH] [--records-dir PATH]

Reads, for each of the four labeling sets (Jahnavi, Aditya, Manoj, Thanya):
    <labeling-dir>/<Name>_texts.txt                       the articles
    <labeling-dir>/<Name>_labels.csv                      the human `useful` answers
    <records-dir>/<Name>_chain_of_thought_v2.jsonl        the gold records (may be missing or partial;
                                                          default data/chain_of_thought, else
                                                          ../labeled_data_chain_of_thought)
and the prompt document prompt_versions/llm_extraction_prompt_v5.1.md.

Writes:
    data/articles.json           one record per unique article, with `split` and `passes_keyword_gate`
    data/gold_labels.json        one record per article that has a chain-of-thought record
    data/human_labels.json       one record per article: the human `useful` answers
    prompts/system_prompt_v5.1.txt   the v5.1 rules, from "## Task" to the end, word for word
    prompts/examples_v5.1.json       only if it does not exist yet: [] (zero-shot)

Row numbers collide across the four sets (row 41 is four different articles), so everything is
keyed by `article_id`. The copies of an article that appears in two sets must agree. By default
every such article is then removed entirely (80 articles: the 40 double-labelled dev articles and
the 40 dev articles repeated as Thanya rows 1-40); --keep-shared keeps one copy of each instead.
"""

import argparse
import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
LABELERS = ("Jahnavi", "Aditya", "Manoj", "Thanya")
PROMPT_DOCUMENT = PROJECT_DIR / "prompt_versions" / "llm_extraction_prompt_v5.1.md"
SYSTEM_PROMPT_FILE = PROJECT_DIR / "prompts" / "system_prompt_v5.1.txt"
EXAMPLES_FILE = PROJECT_DIR / "prompts" / "examples_v5.1.json"

# The locked test set: Thanya rows 41-320. Rows 1-40 repeat Jahnavi 21-40 and Manoj 1-20.
TEST_LABELER = "Thanya"
FIRST_TEST_ROW = 41


# --- System prompt -----------------------------------------------------------

def extract_system_prompt(prompt_markdown: str) -> str:
    """Everything from '## Task' to the end. The title and the generation note above it are dropped."""
    return prompt_markdown[prompt_markdown.index("## Task"):].strip() + "\n"


# --- Articles ----------------------------------------------------------------

# Articles are separated by a line of 80 "=" followed by a title line ("#12  [1-own]  <article_id>").
# Splitting only there keeps a line of "=" inside an article body from breaking it.
_ARTICLE_START = re.compile(r"^={80}\n(?=#\d+\s)", re.MULTILINE)
_HEADER_BODY_SEPARATOR = "-" * 80
_TITLE_LINE = re.compile(r"^#(\d+)\s+\[([^\]]*)\]\s+(\S+)\s*$", re.MULTILINE)
_SCAN_DATE_LINE = re.compile(r"^scan date:\s*(\S+)\s*$", re.MULTILINE)
_LINK_LINE = re.compile(r"^link:\s*(.*?)\s*$", re.MULTILINE)


def convert_articles(texts_path: Path) -> list[dict]:
    """Parse one <Name>_texts.txt into records with row, article_id, scan_date, link and article.

    Only the text after the first dashed line is the article. The header lines above it (GDELT
    tags, places mentioned) are never sent to the model: the prompt forbids using them (5.6).
    """
    articles = []
    for block in _ARTICLE_START.split(texts_path.read_text(encoding="utf-8")):
        if _HEADER_BODY_SEPARATOR not in block:
            continue  # text before the first article
        header, body = block.split(_HEADER_BODY_SEPARATOR, 1)
        title, scan_date, link = (_TITLE_LINE.search(header), _SCAN_DATE_LINE.search(header),
                                  _LINK_LINE.search(header))
        if not (title and scan_date and link):
            raise ValueError(f"{texts_path.name}: cannot read the article header:\n{header[:300]}")
        articles.append({
            "row": int(title.group(1)),
            "article_id": title.group(3),
            "scan_date": scan_date.group(1),
            "link": link.group(1),
            "article": body.strip(),
        })
    return articles


def load_keyword_gate(capstone_project_dir: Path):
    """Import is_flu_related from flu_bucketing/flu_keywords.py, the project's Rule 1 keyword list."""
    path = capstone_project_dir / "flu_bucketing" / "flu_keywords.py"
    spec = importlib.util.spec_from_file_location("flu_keywords", path)
    if spec is None or not path.exists():
        raise FileNotFoundError(f"Keyword list not found: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.is_flu_related


# --- Labels ------------------------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    # "utf-8-sig" removes the invisible byte-order mark that Excel puts at the file start.
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_records(path: Path) -> list[dict]:
    """Read a chain-of-thought file (one JSON record per line). A missing file gives []."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def human_useful(answer: str) -> bool | None:
    """The sheet's yes/no answer as true/false; None when the cell is blank or unclear."""
    return {"yes": True, "no": False}.get(answer.strip().lower())


# --- Build -------------------------------------------------------------------

def build(labeling_dir: Path, records_dir: Path, is_flu_related) -> tuple[list, list, list]:
    """Return (articles, gold labels, human labels), each a list sorted by article id."""
    articles: dict[str, dict] = {}
    gold: dict[str, dict] = {}
    human: dict[str, dict] = {}

    for name in LABELERS:
        for article in convert_articles(labeling_dir / f"{name}_texts.txt"):
            article_id, row = article["article_id"], article["row"]
            split = "test" if name == TEST_LABELER and row >= FIRST_TEST_ROW else "dev"
            entry = articles.setdefault(article_id, {
                "article_id": article_id, "scan_date": article["scan_date"], "link": article["link"],
                "article": article["article"], "split": split, "sources": [],
            })
            if entry["article"] != article["article"] or entry["scan_date"] != article["scan_date"]:
                raise ValueError(f"{article_id}: the copy in {name} row {row} differs from {entry['sources']}")
            if entry["split"] != split:
                raise ValueError(f"{article_id} is in both the dev and the test split ({entry['sources']}, "
                                 f"{name}:{row}); the test set must be unseen")
            entry["sources"].append(f"{name}:{row}")

        for label in read_csv(labeling_dir / f"{name}_labels.csv"):
            entry = human.setdefault(label["article_id"], {"article_id": label["article_id"], "by_labeler": {}})
            entry["by_labeler"][name] = human_useful(label["useful"])

        for record in read_records(records_dir / f"{name}_chain_of_thought_v2.jsonl"):
            output = record["output"]
            labelers = [source["labeler"] for source in record["source_rows"]]
            new = {"article_id": record["article_id"], "useful": output["useful"],
                   "items": output["items"], "labelers": labelers}
            old = gold.setdefault(record["article_id"], new)
            if (old["useful"], old["items"]) != (new["useful"], new["items"]):
                raise ValueError(f"{record['article_id']}: the gold records in {old['labelers']} and "
                                 f"{labelers} disagree")
            old["labelers"] = sorted(set(old["labelers"]) | set(labelers))

    for entry in articles.values():
        entry["passes_keyword_gate"] = bool(is_flu_related(entry["article"]))
    for article_id, entry in gold.items():
        if article_id not in articles:
            raise ValueError(f"gold record {article_id} has no article in the texts files")
        entry["split"] = articles[article_id]["split"]
    for entry in human.values():
        # Two people labelled the overlap articles. Their answer is used only where they agree.
        answers = {value for value in entry["by_labeler"].values() if value is not None}
        entry["useful"] = answers.pop() if len(answers) == 1 else None

    def ordered(records: dict, keys: tuple[str, ...]) -> list[dict]:
        return [{key: records[article_id][key] for key in keys} for article_id in sorted(records)]

    return (
        ordered(articles, ("article_id", "scan_date", "link", "split", "passes_keyword_gate",
                           "sources", "article")),
        ordered(gold, ("article_id", "split", "useful", "labelers", "items")),
        ordered(human, ("article_id", "useful", "by_labeler")),
    )


def drop_shared(articles: list, gold: list, human: list) -> tuple[list, list, list, int]:
    """Remove every article that appears in more than one labeling set, from all three lists.

    These are the 40 double-labelled dev articles (Jahnavi/Aditya, Aditya/Manoj) and the 40 dev
    articles repeated as Thanya rows 1-40. Returns the three lists and how many articles were removed.
    """
    shared = {a["article_id"] for a in articles if len(a["sources"]) > 1}
    keep = lambda records: [r for r in records if r["article_id"] not in shared]  # noqa: E731
    return keep(articles), keep(gold), keep(human), len(shared)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(PROJECT_DIR)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capstone-dir", type=Path, default=PROJECT_DIR.parent.parent,
                        help="folder that contains labeling/labeling/ (default: two levels up)")
    parser.add_argument("--labeling-dir", type=Path,
                        help="folder with the *_texts.txt and *_labels.csv files "
                             "(default: <capstone-dir>/labeling/labeling)")
    default_records = PROJECT_DIR / "data" / "chain_of_thought"
    if not default_records.exists():
        default_records = PROJECT_DIR.parent / "labeled_data_chain_of_thought"
    parser.add_argument("--records-dir", type=Path, default=default_records,
                        help="folder with the *_chain_of_thought_v2.jsonl files (default: data/chain_of_thought, "
                             "else ../labeled_data_chain_of_thought)")
    parser.add_argument("--keep-shared", action="store_true",
                        help="keep articles that appear in more than one labeling set (default: remove them all)")
    args = parser.parse_args()
    labeling_dir = args.labeling_dir or args.capstone_dir / "labeling" / "labeling"

    articles, gold, human = build(labeling_dir, args.records_dir, load_keyword_gate(PROJECT_DIR.parent))
    if not args.keep_shared:
        articles, gold, human, removed = drop_shared(articles, gold, human)
        print(f"removed {removed} articles that appear in more than one labeling set")
    write_json(PROJECT_DIR / "data" / "articles.json", articles)
    write_json(PROJECT_DIR / "data" / "gold_labels.json", gold)
    write_json(PROJECT_DIR / "data" / "human_labels.json", human)

    SYSTEM_PROMPT_FILE.write_text(extract_system_prompt(PROMPT_DOCUMENT.read_text(encoding="utf-8")),
                                  encoding="utf-8")
    print(f"wrote {SYSTEM_PROMPT_FILE.relative_to(PROJECT_DIR)}")
    if not EXAMPLES_FILE.exists():
        write_json(EXAMPLES_FILE, [])  # zero-shot until the few-shot examples are chosen and frozen

    for split in ("dev", "test"):
        in_split = [a for a in articles if a["split"] == split]
        labelled = [g for g in gold if g["split"] == split]
        print(f"{split}: {len(in_split)} articles, {sum(not a['passes_keyword_gate'] for a in in_split)} fail "
              f"the keyword gate, {len(labelled)} with gold ({sum(g['useful'] for g in labelled)} useful)")
    if len(gold) < len(articles):
        print(f"note: {len(articles) - len(gold)} articles have no gold record yet and cannot be scored",
              file=sys.stderr)


if __name__ == "__main__":
    main()
