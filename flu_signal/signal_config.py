"""Paths and settings of the weekly signal and change-point work.

The inputs live in the other worktrees of the capstone folder, so the paths are built from this
file's place: capstone-project/repo-llm-v2/flu_signal/.
"""

from pathlib import Path

SIGNAL_DIR = Path(__file__).resolve().parent
REPO_DIR = SIGNAL_DIR.parent                 # repo-llm-v2
CAPSTONE_DIR = REPO_DIR.parent               # the folder that holds the worktrees

# Read only. The LLM replies for the 39,248 pool articles sent to the model (one record per article).
LLM_REPLIES_PATH = REPO_DIR / "llm-extractor" / "results" / "pool_combined" / "raw_results.jsonl"
# The 1,120 gold articles (labelled with prompt v5.2). They were not sent to the pool run.
GOLD_LABELS_PATH = REPO_DIR / "llm-extractor" / "data" / "gold_labels.json"
# The pool: 50,640 articles, one per story, with scan date, sampling country and season.
POOL_BUCKETS_PATH = CAPSTONE_DIR / "repo-sampling" / "sampling" / "output" / "all_articles_buckets.csv"
# The keyword filter's layer for each pool article (drop_no_flu_word = not sent, counted as not useful).
FILTER_DECISIONS_PATH = REPO_DIR / "usefulness_filter" / "output" / "filter_decisions.csv"
# Every cohort country-season whose window holds the article and whose country it mentions.
SEASON_ASSIGNMENTS_PATH = CAPSTONE_DIR / "repo" / "output" / "pool" / "season_assignments.jsonl"
# The 38 country-seasons: onset date and window (both ends included). One writer: prepare_pool.py windows.
SEASON_WINDOWS_PATH = CAPSTONE_DIR / "repo" / "output" / "pool" / "season_windows.json"

# Written by this folder (gitignored).
OUTPUT_DIR = SIGNAL_DIR / "output"
ARTICLES_PATH = OUTPUT_DIR / "articles.csv"
ITEMS_PATH = OUTPUT_DIR / "items.csv"
TABLES_REPORT_PATH = OUTPUT_DIR / "tables_report.json"

# The six cohort countries: the item's `country` field (OpenStreetMap English name) -> ISO3.
COHORT_COUNTRIES = {
    "United States": "USA",
    "Australia": "AUS",
    "Brazil": "BRA",
    "India": "IND",
    "Kenya": "KEN",
    "Indonesia": "IDN",
}

# Where an article's answer came from.
SOURCE_GOLD = "gold"
SOURCE_LLM = "llm"
SOURCE_NOT_SENT = "not_sent"                 # dropped by the keyword filter: not useful, no items

DROPPED_LAYER = "drop_no_flu_word"

# Item fields copied to items.csv, in order.
ITEM_FIELDS = ("kind", "number", "count_type", "status", "strain", "city", "state", "country",
               "start_date", "end_date", "words")
