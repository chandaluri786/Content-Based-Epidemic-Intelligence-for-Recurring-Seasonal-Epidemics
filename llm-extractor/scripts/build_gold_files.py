"""Build data/articles.json and data/gold_labels.json from the label records.

The extractor itself reads only files inside this folder (`prompts/` and `data/`). Run this
script when the records change. It is the only code that knows where the capstone files live.

    python scripts/build_gold_files.py [--capstone-dir PATH] [--labeling-dir PATH] [--records-dir PATH]

Reads:
    <records-dir>/<Name><RECORDS_SUFFIX>              the gold records (config.py; default
                                                    data/chain_of_thought/<Name>_labels_v5.2.jsonl),
                                                    for every <Name> that has such a file, in either
                                                    layout read by data_loading.read_label_records
    <labeling-dir>/<Name>_texts.txt                  the article texts of all four labeling sets
                                                    (the records hold no article text)
    prompt_versions/llm_extraction_prompt_<PROMPT_VERSION>.md   the prompt document (config.py)

Writes:
    data/articles.json             one record per article that has a gold record: id, scan_date, link,
                                   sources (set and row) and the article text
    data/gold_labels.json          one record per article: useful, items, labelers
    prompts/system_prompt_<PROMPT_VERSION>.txt  the rules, from "## Task" to the end, word for word

No human labels are read. Row numbers collide across the labeling sets (row 41 is four different
articles), so everything is keyed by `article_id`. An article that appears in more than one
labeling set (double-labelled articles, and the Thanya rows 1-40 that repeat Jahnavi and Manoj
articles) is removed entirely: every copy, its article text and its gold record.
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
from flu_extractor import config  # noqa: E402
from flu_extractor.data_checks import check_articles, check_gold  # noqa: E402
from flu_extractor.data_loading import read_label_records  # noqa: E402

# The labeling sets whose article texts are read. All four are read, so that an article repeated in
# another set (Thanya rows 1-40) is found and removed, even though only some sets have gold records.
LABELERS = ("Jahnavi", "Aditya", "Manoj", "Thanya")
RECORDS_SUFFIX = config.RECORDS_SUFFIX
PROMPT_DOCUMENT = PROJECT_DIR / "prompt_versions" / f"llm_extraction_prompt_{config.PROMPT_VERSION}.md"
SYSTEM_PROMPT_FILE = config.SYSTEM_PROMPT_PATH
DATA_DIR = config.DATA_DIR


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


# --- Build -------------------------------------------------------------------

def build(labeling_dir: Path, records_dir: Path) -> tuple[list[dict], list[dict], dict]:
    """Return (articles, gold labels, counts). Both lists hold only unshared articles with gold."""
    texts: dict[str, dict] = {}
    for name in LABELERS:
        path = labeling_dir / f"{name}_texts.txt"
        if not path.exists():
            raise FileNotFoundError(f"article texts not found: {path}")
        for article in convert_articles(path):
            entry = texts.setdefault(article["article_id"], {**article, "sources": []})
            if entry["article"] != article["article"] or entry["scan_date"] != article["scan_date"]:
                raise ValueError(f"{article['article_id']}: the copy in {name} row {article['row']} "
                                 f"differs from {entry['sources']}")
            entry["sources"].append(f"{name}:{article['row']}")
    shared = {article_id for article_id, entry in texts.items() if len(entry["sources"]) > 1}

    record_files = sorted(records_dir.glob(f"*{RECORDS_SUFFIX}"))
    if not record_files:
        raise FileNotFoundError(f"no *{RECORDS_SUFFIX} files in {records_dir}")
    gold: dict[str, dict] = {}
    record_count = 0
    for path in record_files:
        for record in read_label_records(path):
            record_count += 1
            article_id, output = record["article_id"], record["output"]
            if article_id not in texts:
                raise ValueError(f"{path.name}: gold record {article_id} has no article in the texts files")
            if output["useful"] != bool(output["items"]):
                raise ValueError(f"{path.name}: {article_id} has useful={output['useful']} "
                                 f"with {len(output['items'])} items")
            labelers = [source["labeler"] for source in record["source_rows"]]
            new = {"article_id": article_id, "useful": output["useful"], "items": output["items"],
                   "labelers": labelers}
            old = gold.setdefault(article_id, new)
            if (old["useful"], old["items"]) != (new["useful"], new["items"]):
                raise ValueError(f"{article_id}: the gold records in {old['labelers']} and {labelers} disagree")
            old["labelers"] = sorted(set(old["labelers"]) | set(labelers))

    kept = sorted(article_id for article_id in gold if article_id not in shared)
    missing_quotes = 0
    for article_id in kept:
        text = " ".join(texts[article_id]["article"].split())
        for item in gold[article_id]["items"]:
            missing_quotes += sum(" ".join(q.split()) not in text for q in item["evidence"])
    articles = [{key: texts[a][key] for key in ("article_id", "scan_date", "link", "sources", "article")}
                for a in kept]
    labels = [{key: gold[a][key] for key in ("article_id", "useful", "labelers", "items")} for a in kept]
    counts = {"record_files": [p.name for p in record_files], "records": record_count,
              "unique_gold_articles": len(gold), "removed_shared": len(set(gold) & shared),
              "kept": len(kept), "useful": sum(g["useful"] for g in labels),
              "items": sum(len(g["items"]) for g in labels), "evidence_not_found": missing_quotes}
    return articles, labels, counts


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(PROJECT_DIR)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capstone-dir", type=Path, default=PROJECT_DIR.parent.parent,
                        help="folder that contains labeling/labeling/ (default: two levels up)")
    parser.add_argument("--labeling-dir", type=Path,
                        help="folder with the *_texts.txt files (default: <capstone-dir>/labeling/labeling)")
    parser.add_argument("--records-dir", type=Path, default=config.RECORDS_DIR,
                        help=f"folder with the *{RECORDS_SUFFIX} files (default: data/chain_of_thought)")
    args = parser.parse_args()
    labeling_dir = args.labeling_dir or args.capstone_dir / "labeling" / "labeling"

    articles, labels, counts = build(labeling_dir, args.records_dir)
    problems = check_articles(articles) + check_gold(labels, articles)
    if problems:
        print(f"Not written: {len(problems)} problems with the {config.PROMPT_VERSION} format or the evidence, e.g.:", file=sys.stderr)
        print("\n".join(problems[:20]), file=sys.stderr)
        raise SystemExit(1)
    write_json(DATA_DIR / "articles.json", articles)
    write_json(DATA_DIR / "gold_labels.json", labels)
    SYSTEM_PROMPT_FILE.write_text(extract_system_prompt(PROMPT_DOCUMENT.read_text(encoding="utf-8")),
                                  encoding="utf-8")
    print(f"wrote {SYSTEM_PROMPT_FILE.relative_to(PROJECT_DIR)}")

    print(f"records: {counts['records']} in {', '.join(counts['record_files'])}; "
          f"{counts['unique_gold_articles']} unique articles")
    print(f"removed {counts['removed_shared']} articles that appear in more than one labeling set")
    print(f"kept {counts['kept']} articles: {counts['useful']} useful, {counts['kept'] - counts['useful']} "
          f"not useful, {counts['items']} gold items")
    if counts["evidence_not_found"]:
        print(f"warning: {counts['evidence_not_found']} gold evidence quotes are not in their article text",
              file=sys.stderr)


if __name__ == "__main__":
    main()
