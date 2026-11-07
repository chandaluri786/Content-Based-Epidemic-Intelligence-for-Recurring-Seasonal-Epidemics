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
# Every cohort country-season whose window holds the article's date, mentioned or not (season_assign.py).
SEASON_ASSIGNMENTS_PATH = CAPSTONE_DIR / "repo" / "output" / "pool" / "season_assignments.jsonl"
# The pooled corpus (2 GB, streamed): each article's GDELT locations, used for the countries it mentions.
POOLED_ARTICLES_PATH = CAPSTONE_DIR / "repo" / "output" / "pool" / "pooled_articles.jsonl"
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

# GDELT location codes (FIPS 10-4, not ISO) of the cohort -> ISO3. Same as repo/config.py TARGET_COUNTRIES.
COHORT_FIPS = {"US": "USA", "AS": "AUS", "BR": "BRA", "IN": "IND", "KE": "KEN", "ID": "IDN"}

# Where an article's answer came from.
SOURCE_GOLD = "gold"
SOURCE_LLM = "llm"
SOURCE_NOT_SENT = "not_sent"                 # dropped by the keyword filter: not useful, no items

DROPPED_LAYER = "drop_no_flu_word"

# Step 2: weekly signals.
WEEKLY_PATH = OUTPUT_DIR / "weekly_signals.csv"
WEEKLY_REPORT_PATH = OUTPUT_DIR / "weekly_report.json"

# Week index = whole weeks from the FluNet onset (week 0 starts on the onset date). A window runs from
# onset - 70 days to onset + 14 days, both included: weeks -10 .. +1, plus one day (onset + 14) that is
# folded into week +1. So every season has 12 weeks.
FIRST_WEEK = -10
LAST_WEEK = 1

# Season split (decided 2026-11-07): by season year, held out from 2022 on.
HELD_OUT_FROM_YEAR = 2022
SPLIT_CALIBRATION = "calibration"
SPLIT_HELD_OUT = "held_out"
# The headline comparison. BRA, KEN and IDN have almost no content and go to the all-38 table only.
HEADLINE_COUNTRIES = ("USA", "AUS", "IND")

# Items that are not a signal of seasonal human flu: bird flu and other animal-origin strains
# (prompt 1.3 makes trend items for animal outbreaks linked to food), and swine-origin variant
# viruses ("v" suffix). Matched on the lower-cased strain.
NON_SEASONAL_STRAIN_PREFIXES = ("h5", "h7", "h9", "h10", "avian")
NON_SEASONAL_STRAIN_SUFFIX = "v"
# Trend words that report flu activity going on. inactive, low and falling do not.
ACTIVITY_WORDS = ("present", "moderate", "high", "rising")
RISING_WORDS = ("rising", "high")
COUNT_KINDS = ("cases", "deaths", "hospitalized")

# Item fields copied to items.csv, in order.
ITEM_FIELDS = ("kind", "number", "count_type", "status", "strain", "city", "state", "country",
               "start_date", "end_date", "words")
