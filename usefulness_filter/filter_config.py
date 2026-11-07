"""Paths and settings of the keyword filter.

The inputs live in the other worktrees of the capstone folder (README "Inputs"), so the paths
are built from this file's place: capstone-project/repo-llm-v2/usefulness_filter/.
"""

from pathlib import Path

FILTER_DIR = Path(__file__).resolve().parent
REPO_DIR = FILTER_DIR.parent                 # repo-llm-v2
CAPSTONE_DIR = REPO_DIR.parent               # the folder that holds the worktrees

# The gold set: 1,120 articles labelled by Claude Opus with prompt v5.2. They are not sent again.
GOLD_LABELS_PATH = REPO_DIR / "llm-extractor" / "data" / "gold_labels.json"

# Read only. The sampling output is gitignored and comes from Drive (repo-sampling/data_links.md).
POOL_BUCKETS_PATH = CAPSTONE_DIR / "repo-sampling" / "sampling" / "output" / "all_articles_buckets.csv"
POOL_TEXTS_SOURCE = CAPSTONE_DIR / "repo" / "output" / "pool" / "pooled_articles.jsonl"  # 2 GB, streamed

# Written by this folder. Both folders are gitignored.
DATA_DIR = FILTER_DIR / "data"
POOL_TEXTS_PATH = DATA_DIR / "pool_texts.jsonl"
OUTPUT_DIR = FILTER_DIR / "output"
DECISIONS_PATH = OUTPUT_DIR / "filter_decisions.csv"
POOL_ARTICLES_PATH = OUTPUT_DIR / "pool_articles.json"   # the extractor input

# Layer 1: buckets that always go to the model, flu word or not.
ALWAYS_KEEP_PREFIXES = ("P_", "Z_")

# Layer names, as written in filter_decisions.csv.
LAYER_KEEP_BUCKET = "keep_bucket"
LAYER_DROP_KEYWORD = "drop_no_flu_word"
LAYER_FLU_WORD = "has_flu_word"
