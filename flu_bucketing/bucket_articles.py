"""Sort labeling text files into flu related and non flu related files.

Input : <Name>_texts.txt files (the labeling packets). Each article block looks like
            ================================================================================
            #12  [2]  20161209003000-994
            scan date: 2016-12-09
            (optional extra header lines, e.g. tagged country, places mentioned)
            link: http://...
            --------------------------------------------------------------------------------
            <article text>
Output: <Name>_texts_flu.txt and <Name>_texts_nonflu.txt (same block format, blocks copied unchanged,
        original #numbers kept), plus bucket_audit.csv (one row per article and the terms that matched).

Only the article BODY is searched (not the header, not the link). See flu_keywords.py for the rules.

Usage
    python bucket_articles.py INPUT_DIR [--out OUTPUT_DIR] [--dry-run]
        INPUT_DIR   folder holding the *_texts.txt files
        --out       where to write the new files (default: INPUT_DIR)
        --dry-run   print the counts and write nothing
"""
import argparse
import csv
import re
import sys
from pathlib import Path

from flu_keywords import flu_hits

RULE = "=" * 80
BLOCK_START = re.compile(r"(?m)^(?=={80}\n#\d+ )")
HEADER = re.compile(r"=+\n#(\d+)\s+\[([^\]]*)\]\s+(\S+)\n(?:[^\n]*\n)*?-{80}\n")  # any header lines (date, link, places ...) up to the dashed line


def split_blocks(text):
    """Split a texts file into article blocks. Joining the blocks gives back the file exactly."""
    blocks = [b for b in BLOCK_START.split(text) if b != ""]
    if not blocks or not blocks[0].startswith(RULE):  # text before the first block (normally none)
        raise ValueError("file does not start with an article block")
    if "".join(blocks) != text:
        raise ValueError("splitting changed the text")
    return blocks


def parse_block(block):
    m = HEADER.match(block)
    if not m:
        raise ValueError("cannot read block header: " + block[:120])
    return m.group(1), m.group(2), m.group(3), block[m.end():]


def sort_file(path):
    blocks = split_blocks(path.read_text(encoding="utf-8"))
    flu, nonflu, audit = [], [], []
    for block in blocks:
        num, tag, rec_id, body = parse_block(block)
        hits = flu_hits(body)
        bucket = "flu" if hits else "nonflu"
        (flu if hits else nonflu).append(block)
        terms = sorted({w for _, _, w in hits})
        audit.append({
            "file": path.name, "row": num, "tag": tag, "record_id": rec_id, "bucket": bucket,
            "n_hits": len(hits), "n_distinct_terms": len(terms),
            "sources": "+".join(sorted({s for _, s, _ in hits})),
            "terms": "; ".join(terms[:15]), "body_chars": len(body),
        })
    return flu, nonflu, audit


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_dir")
    ap.add_argument("--out")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    src = Path(a.input_dir)
    out = Path(a.out) if a.out else src
    files = sorted(p for p in src.glob("*_texts.txt"))
    if not files:
        sys.exit("no *_texts.txt files in " + str(src))
    all_audit = []
    for p in files:
        flu, nonflu, audit = sort_file(p)
        total = len(flu) + len(nonflu)
        print(f"{p.name}: {total} articles -> {len(flu)} flu, {len(nonflu)} non flu")
        all_audit += audit
        if not a.dry_run:
            out.mkdir(parents=True, exist_ok=True)
            stem = p.name[: -len(".txt")]
            (out / f"{stem}_flu.txt").write_text("".join(flu), encoding="utf-8")
            (out / f"{stem}_nonflu.txt").write_text("".join(nonflu), encoding="utf-8")
    if not a.dry_run:
        with open(out / "bucket_audit.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(all_audit[0]))
            w.writeheader()
            w.writerows(all_audit)
        print("wrote", len(files) * 2, "files and bucket_audit.csv to", out)
    else:
        print("dry run: nothing written")


if __name__ == "__main__":
    main()
