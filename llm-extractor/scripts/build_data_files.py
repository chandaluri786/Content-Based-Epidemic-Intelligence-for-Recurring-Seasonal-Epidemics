"""One-off converter: copy the labeled sample and the dev/test split into this project as JSON.

The extractor itself reads only files inside this folder (`prompts/` and `data/`).
Run this script when you want to refresh the data files, for example after a label was
corrected. It is the only code that knows where the sampling files live.

    python scripts/build_data_files.py [--sampling-dir PATH] [--with-prompts]
    python scripts/build_data_files.py --labeling-dir PATH --labels-out data/human_labels_<name>.json

Always rewrites (from the repo-sampling worktree):
    sampling/output/sample_1200.jsonl                      -> data/articles.json
    sampling/output/labeling/<Name>_labels.csv, _items.csv,
    sampling/split/dev_test_split.csv                      -> data/human_labels.json
    (all four labelers; each article's answer comes from the labeler who owns it)

With --labeling-dir and --labels-out (a second label set on the same 1,200 articles, such as
Jahnavi's reviewed sheets): writes only that labels file. Each article keeps its split from
dev_test_split.csv but takes `useful` from the given sheets, so the check that the sheet and the
split agree on `useful` is skipped; every other check still runs.

Only with --with-prompts (this OVERWRITES the active prompt files in prompts/):
    prompt_versions/llm_extraction_prompt_v2.0.md          -> prompts/system_prompt_v2.0.txt
    Project Documents /llm_extraction_examples_v2.0.jsonl  -> prompts/examples_v2.0.json
    (the first is in this project; the second is read from --capstone-dir)
"""

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

LABELERS = ("Aditya", "Jahnavi", "Manoj", "Thanya")
SAMPLE_SIZE = 1200
# Round-1 check rows double-label someone else's article. Only the owner's answer is used.
CHECK_ROUND_PREFIX = "1-check"
VALID_KINDS = {"cases", "deaths", "hospitalized", "trend"}
VALID_STATUS = {"", "confirmed", "suspected"}
VALID_TOTAL_OR_NEW = {"", "total", "new"}
# The most errors printed when the sheets do not pass the checks.
MAX_ERRORS_SHOWN = 30

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


# --- Reading the sampling files ----------------------------------------------

# One evidence cell can hold several quotes separated by "||". Jahnavi put the separator on a
# line of its own, others wrote " || ", so any whitespace around it is part of the separator.
EVIDENCE_SEPARATOR = re.compile(r"\s*\|\|\s*")


def read_rows(path: Path) -> list[dict]:
    """Read a CSV sheet. "utf-8-sig" removes the byte-order mark some sheets start with;
    newline="" keeps line breaks inside quoted evidence cells."""
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_sample(jsonl_path: Path) -> dict[str, dict]:
    """Read sample_1200.jsonl into {article_id: record}."""
    with jsonl_path.open(encoding="utf-8") as file:
        records = [json.loads(line) for line in file if line.strip()]
    return {record["record_id"]: record for record in records}


def read_split(split_csv: Path) -> dict[str, dict]:
    """Read dev_test_split.csv into {article_id: row}."""
    return {row["article_id"]: row for row in read_rows(split_csv)}


def convert_item(record: dict) -> dict:
    """One items-sheet row in the model's reply format (empty cells become None)."""
    number = record["number"].strip()
    return {
        "kind": record["kind"].strip(),
        "strain": record["strain"].strip() or None,
        "number": int(number) if number.isdigit() else number or None,  # a non-integer is reported by validate
        "status": record["status"].strip() or None,
        "total_or_new": record["total_or_new"].strip() or None,
        "city": record["city"].strip() or None,
        "state": record["state"].strip() or None,
        "country": record["country"].strip() or None,
        "start_date": record["start_date"].strip() or None,
        "end_date": record["end_date"].strip() or None,
        "words": record["words"].strip() or None,
        "evidence": EVIDENCE_SEPARATOR.split(record["evidence"].strip()),
    }


def read_sheets(labeling_dir: Path) -> dict[str, dict]:
    """Every labeler's own answers: {article_id: {"labeler", "useful", "items"}}.

    Items are taken from the owner's items file only, and only for the owner's articles, because a
    file can also hold items for that labeler's check rows.
    """
    answers: dict[str, dict] = {}
    for name in LABELERS:
        own_rows = [row for row in read_rows(labeling_dir / f"{name}_labels.csv")
                    if not row["round"].startswith(CHECK_ROUND_PREFIX)]
        own_ids = {row["article_id"] for row in own_rows}
        items: dict[str, list[dict]] = {}
        for record in read_rows(labeling_dir / f"{name}_items.csv"):
            if record["article_id"] in own_ids:
                items.setdefault(record["article_id"], []).append(convert_item(record))
        for row in own_rows:
            article_id = row["article_id"]
            if article_id in answers:
                raise SystemExit(f"{article_id} is owned by both {answers[article_id]['labeler']} and {name}")
            answers[article_id] = {"labeler": name, "useful": row["useful"].strip().lower(),
                                   "items": items.get(article_id, [])}
    return answers


# --- Checks ------------------------------------------------------------------

def _is_iso_date(value: str | None) -> bool:
    if value is None:
        return True
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def item_problems(item: dict) -> list[str]:
    """What is wrong with one converted item (empty list = nothing)."""
    problems = []
    if item["kind"] not in VALID_KINDS:
        problems.append(f"kind {item['kind']!r}")
    if not (item["number"] is None or isinstance(item["number"], int)):
        problems.append(f"number {item['number']!r} is not a whole number")
    if (item["status"] or "") not in VALID_STATUS:
        problems.append(f"status {item['status']!r}")
    if (item["total_or_new"] or "") not in VALID_TOTAL_OR_NEW:
        problems.append(f"total_or_new {item['total_or_new']!r}")
    if item["country"] is None:
        problems.append("no country")
    for field in ("start_date", "end_date"):
        if not _is_iso_date(item[field]):
            problems.append(f"{field} {item[field]!r} is not YYYY-MM-DD")
    if not all(item["evidence"]):
        problems.append("an evidence quote is empty")
    return problems


def validate(answers: dict[str, dict], sample: dict[str, dict], split: dict[str, dict],
             expected_size: int = SAMPLE_SIZE, check_split_useful: bool = True) -> list[str]:
    """Every reason the sheets, the sample and the split do not fit together.

    check_split_useful=False drops only the "sheet and split agree on useful" check, for a second
    label set that reuses the frozen split's dev/test assignment."""
    errors = []
    for name, ids in (("sheets", answers), ("sample", sample), ("split", split)):
        if len(ids) != expected_size:
            errors.append(f"the {name} hold {len(ids)} articles, not {expected_size}")
    for article_id in sorted(set(answers) | set(sample) | set(split)):
        missing = [name for name, ids in (("sheets", answers), ("sample", sample), ("split", split))
                   if article_id not in ids]
        if missing:
            errors.append(f"{article_id}: not in the {' or the '.join(missing)}")
            continue
        answer = answers[article_id]
        where = f"{article_id} ({answer['labeler']})"
        if answer["useful"] not in ("yes", "no"):
            errors.append(f"{where}: useful is {answer['useful']!r}, not yes or no")
        if check_split_useful and answer["useful"] != split[article_id]["useful"]:
            errors.append(f"{where}: the sheet says useful={answer['useful']}, the split says "
                          f"{split[article_id]['useful']}")
        if answer["useful"] == "yes" and not answer["items"]:
            errors.append(f"{where}: useful is yes but there are no items")
        if answer["useful"] == "no" and answer["items"]:
            errors.append(f"{where}: useful is no but there are {len(answer['items'])} items")
        for number, item in enumerate(answer["items"], start=1):
            errors += [f"{where} item {number}: {problem}" for problem in item_problems(item)]
    return errors


# --- Building the two data files ---------------------------------------------

def build_records(answers: dict[str, dict], sample: dict[str, dict],
                  split: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """(articles, human labels), one record each per article, ordered by article_id."""
    articles, labels = [], []
    for article_id in sorted(answers):
        answer, source = answers[article_id], sample[article_id]
        shared = {"article_id": article_id, "labeler": answer["labeler"], "split": split[article_id]["split"]}
        articles.append({**shared, "scan_date": source["scan_date"], "link": source["url"],
                         "article": source["text"]})
        labels.append({**shared, "useful": answer["useful"] == "yes", "items": answer["items"]})
    return articles, labels


def load_checked_records(sampling_dir: Path, labeling_dir: Path | None = None) -> tuple[list[dict], list[dict]]:
    """Read the sampling files, stop with a list of problems if they do not fit, else build the records.

    labeling_dir: another set of the four sheets; its `useful` is not checked against the split."""
    output = sampling_dir / "sampling" / "output"
    answers = read_sheets(labeling_dir or output / "labeling")
    sample = read_sample(output / "sample_1200.jsonl")
    split = read_split(sampling_dir / "sampling" / "split" / "dev_test_split.csv")
    errors = validate(answers, sample, split, check_split_useful=labeling_dir is None)
    if errors:
        shown = "\n  ".join(errors[:MAX_ERRORS_SHOWN])
        more = f"\n  ... and {len(errors) - MAX_ERRORS_SHOWN} more" if len(errors) > MAX_ERRORS_SHOWN else ""
        raise SystemExit(f"The sampling files do not pass the checks; nothing was written.\n  {shown}{more}")
    return build_records(answers, sample, split)


# --- Main --------------------------------------------------------------------

def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(PROJECT_DIR)}")


def print_counts(labels: list[dict]) -> None:
    """Articles and useful articles per split, to compare with the split report."""
    for split in ("dev", "test"):
        in_split = [label for label in labels if label["split"] == split]
        useful = sum(label["useful"] for label in in_split)
        print(f"  {split}: {len(in_split)} articles, {useful} useful")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sampling-dir", type=Path, default=PROJECT_DIR.parent.parent / "repo-sampling",
                        help="the repo-sampling worktree (default: ../../repo-sampling)")
    parser.add_argument("--capstone-dir", type=Path, default=PROJECT_DIR.parent.parent,
                        help="folder containing 'Project Documents ', used only with --with-prompts")
    parser.add_argument("--with-prompts", action="store_true",
                        help="also rewrite prompts/system_prompt_v2.0.txt and prompts/examples_v2.0.json from the "
                             "capstone prompt v2.0. This OVERWRITES the active prompt files; by default they are "
                             "left alone because prompts/ is maintained by hand.")
    parser.add_argument("--labeling-dir", type=Path,
                        help="a second set of the four sheets (e.g. Jahnavi's reviewed copy); needs --labels-out")
    parser.add_argument("--labels-out", type=Path,
                        help="where to write that set's labels, e.g. data/human_labels_jahnavi.json")
    args = parser.parse_args()

    if args.labeling_dir:
        if not args.labels_out or args.labels_out.resolve() == (PROJECT_DIR / "data" / "human_labels.json").resolve():
            raise SystemExit("--labeling-dir needs --labels-out with a new file name; data/human_labels.json "
                             "holds the team's labels and is never overwritten by another set.")
        if args.with_prompts:
            raise SystemExit("--with-prompts cannot be combined with --labeling-dir")
        _, labels = load_checked_records(args.sampling_dir, args.labeling_dir)
        write_json(args.labels_out.resolve(), labels)
        print_counts(labels)
        return

    # Check everything before writing anything, so a bad sheet never leaves half-updated files.
    articles, labels = load_checked_records(args.sampling_dir)

    if args.with_prompts:
        # The full prompt document lives in this project (prompt_versions/); only the examples
        # file is still read from the capstone folder.
        documents = args.capstone_dir / "Project Documents "  # the folder name really ends with a space
        system_prompt = extract_system_prompt(
            (PROJECT_DIR / "prompt_versions" / "llm_extraction_prompt_v2.0.md").read_text(encoding="utf-8"))
        (PROJECT_DIR / "prompts").mkdir(exist_ok=True)
        (PROJECT_DIR / "prompts" / "system_prompt_v2.0.txt").write_text(system_prompt, encoding="utf-8")
        print("wrote prompts/system_prompt_v2.0.txt")
        write_json(PROJECT_DIR / "prompts" / "examples_v2.0.json",
                   convert_examples(documents / "llm_extraction_examples_v2.0.jsonl"))

    write_json(PROJECT_DIR / "data" / "articles.json", articles)
    write_json(PROJECT_DIR / "data" / "human_labels.json", labels)
    print_counts(labels)


if __name__ == "__main__":
    main()
