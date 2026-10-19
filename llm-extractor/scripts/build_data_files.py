"""One-off converter: copy the capstone source files into this project as JSON.

The extractor itself reads only files inside this folder (`prompts/` and `data/`).
Run this script when you want to refresh the data files from the capstone sources, for
example after more labels were added. It is the only code that knows where the
capstone files live.

    python scripts/build_data_files.py [--capstone-dir PATH] [--with-prompts]

Always rewrites (from the capstone folder):
    labeling/labeling/Jahnavi_texts.txt                    -> data/articles.json
    labeling/labeling/Jahnavi_labels.csv, Jahnavi_items.csv,
    labeling/labeling/need_to_relook.csv                   -> data/human_labels.json

Only with --with-prompts (this OVERWRITES the active prompt files in prompts/):
    prompt_versions/llm_extraction_prompt_v2.0.md          -> prompts/system_prompt_v2.0.txt
    Project Documents /llm_extraction_examples_v2.0.jsonl  -> prompts/examples_v2.0.json
    (the first is in this project; the second is read from the capstone folder)
"""

import argparse
import csv
import json
import re
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

# --- System prompt and examples ----------------------------------------------

def extract_system_prompt(prompt_markdown: str) -> str:
    """Return the text inside the code fence under '## 1. Instructions'."""
    section = prompt_markdown[prompt_markdown.index("## 1. Instructions"):]
    # (.*?) is non-greedy: it stops at the first closing fence on a line of its own.
    fenced = re.search(r"```\n(.*?)\n```", section, flags=re.DOTALL)
    if fenced is None:
        raise ValueError("No code fence found under '## 1. Instructions'")
    return fenced.group(1).strip() + "\n"


def convert_examples(jsonl_path: Path) -> list[dict]:
    """Read the solved examples (one JSON object per line) into a list."""
    with jsonl_path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


# --- Articles ----------------------------------------------------------------

# A line of 80 "=" separates articles; a line of 80 "-" separates an article's header from its body.
_ARTICLE_SEPARATOR = re.compile(r"^={80}$", re.MULTILINE)
_HEADER_BODY_SEPARATOR = re.compile(r"^-{80}$", re.MULTILINE)
_TITLE_LINE = re.compile(r"^#(\d+)\s+\[([^\]]+)\]\s+(\S+)\s*$", re.MULTILINE)
_SCAN_DATE_LINE = re.compile(r"^scan date:\s*(\S+)\s*$", re.MULTILINE)
_LINK_LINE = re.compile(r"^link:\s*(\S+)\s*$", re.MULTILINE)


def convert_articles(texts_path: Path) -> list[dict]:
    """Parse Jahnavi_texts.txt into one record per article."""
    articles = []
    for block in _ARTICLE_SEPARATOR.split(texts_path.read_text(encoding="utf-8")):
        if not block.strip():
            continue  # the file starts with a separator, so the first block is empty
        # Split only at the first dashed line: the body itself may contain more of them.
        header, body = (_HEADER_BODY_SEPARATOR.split(block, maxsplit=1) + [""])[:2]
        title = _TITLE_LINE.search(header)
        scan_date = _SCAN_DATE_LINE.search(header)
        link = _LINK_LINE.search(header)
        if not (title and scan_date and link):
            raise ValueError(f"Cannot read the article header:\n{header[:300]}")
        articles.append({
            "row": int(title.group(1)),
            "article_id": title.group(3),
            "scan_date": scan_date.group(1),
            "link": link.group(1),
            "article": body.strip(),
        })
    return articles


# --- Human labels ------------------------------------------------------------

# In the items sheet one evidence cell holds all quotes of an item, each separated from
# the next by a line that contains only "||". We split them into a list, the same shape
# the model returns.
EVIDENCE_SEPARATOR = "\n||\n"

def convert_human_labels(labels_csv: Path, items_csv: Path, relook_csv: Path) -> list[dict]:
    """Combine usefulness labels, items and the 'need to relook' flag into one record per article."""
    def read_rows(path: Path) -> list[dict]:
        # "utf-8-sig" removes the invisible byte-order mark that Excel puts at the file start.
        with path.open(encoding="utf-8-sig", newline="") as file:
            return list(csv.DictReader(file))

    items_by_article: dict[str, list[dict]] = {}
    for record in read_rows(items_csv):
        items_by_article.setdefault(record["article_id"], []).append({
            "kind": record["kind"],
            "strain": record["strain"] or None,
            "number": int(record["number"]) if record["number"] else None,
            "status": record["status"] or None,
            "total_or_new": record["total_or_new"] or None,
            "city": record["city"] or None,
            "state": record["state"] or None,
            "country": record["country"] or None,
            "start_date": record["start_date"] or None,
            "end_date": record["end_date"] or None,
            "words": record["words"] or None,
            "evidence": record["evidence"].split(EVIDENCE_SEPARATOR),
        })

    relook_rows = {int(record["row"]) for record in read_rows(relook_csv)}
    labels = []
    for record in read_rows(labels_csv):
        row = int(record["row"])
        answer = record["useful"].strip().lower()
        labels.append({
            "row": row,
            "article_id": record["article_id"],
            "useful": {"yes": True, "no": False}.get(answer),  # None = no human label
            "needs_relook": row in relook_rows,
            "items": items_by_article.get(record["article_id"], []),
        })
    return labels


# --- Main --------------------------------------------------------------------

def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(PROJECT_DIR)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capstone-dir", type=Path, default=PROJECT_DIR.parent.parent,
                        help="folder containing 'Project Documents ' and 'labeling' (default: two levels up)")
    parser.add_argument("--with-prompts", action="store_true",
                        help="also rewrite prompts/system_prompt_v2.0.txt and prompts/examples_v2.0.json from the "
                             "capstone prompt v2.0. This OVERWRITES the active prompt files; by default they are "
                             "left alone because prompts/ is maintained by hand.")
    args = parser.parse_args()
    capstone = args.capstone_dir
    documents = capstone / "Project Documents "  # the folder name really ends with a space
    labeling = capstone / "labeling" / "labeling"

    if args.with_prompts:
        # The full prompt document lives in this project (prompt_versions/); only the examples
        # file is still read from the capstone folder.
        system_prompt = extract_system_prompt(
            (PROJECT_DIR / "prompt_versions" / "llm_extraction_prompt_v2.0.md").read_text(encoding="utf-8"))
        (PROJECT_DIR / "prompts").mkdir(exist_ok=True)
        (PROJECT_DIR / "prompts" / "system_prompt_v2.0.txt").write_text(system_prompt, encoding="utf-8")
        print("wrote prompts/system_prompt_v2.0.txt")
        write_json(PROJECT_DIR / "prompts" / "examples_v2.0.json",
                   convert_examples(documents / "llm_extraction_examples_v2.0.jsonl"))

    write_json(PROJECT_DIR / "data" / "articles.json",
               convert_articles(labeling / "Jahnavi_texts.txt"))
    write_json(PROJECT_DIR / "data" / "human_labels.json",
               convert_human_labels(labeling / "Jahnavi_labels.csv", labeling / "Jahnavi_items.csv",
                                    labeling / "need_to_relook.csv"))


if __name__ == "__main__":
    main()
