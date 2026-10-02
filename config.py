"""
Central configuration for the GDELT flu-article extraction pipeline.

Every constant that controls pipeline behavior lives here, not scattered
across modules -- this is the single place to review before running a real
extraction job. See README.md for the reasoning behind each setting.
"""

from __future__ import annotations

import os
from typing import Literal

# ---------------------------------------------------------------------------
# Cohort: countries and years
# ---------------------------------------------------------------------------

# ISO3 code -> GDELT FIPS 10-4 location code. These differ for several
# countries (UK not GB, Japan's JA not JP, etc.) -- confirmed against live
# GKG data, not assumed. Do not add a new country here without checking its
# real FIPS code the same way.
TARGET_COUNTRIES: dict[str, str] = {
    "USA": "US",
    "AUS": "AS",
    "BRA": "BR",
    "IND": "IN",
    "KEN": "KE",
    "IDN": "ID",
}

STUDY_YEARS: list[int] = list(range(2015, 2025))

# ---------------------------------------------------------------------------
# Ground truth onset rule (WHO FluNet) -- Stage 1
# ---------------------------------------------------------------------------

FLUNET_API_URL = "https://xmart-api-public.who.int/FLUMART/VIW_FNT"
ONSET_POSITIVITY_THRESHOLD_PCT = 10.0
ONSET_SUSTAIN_WEEKS = 2

# ---------------------------------------------------------------------------
# GDELT ingestion window -- Stages 2-3
# ---------------------------------------------------------------------------

GDELT_RAW_MIRROR_BASE = "https://data.gdeltproject.org/gdeltv2"
GDELT_EARLIEST_AVAILABLE_DATE = "2015-02-19"  # GKG 2.0 launch date
WEEKS_BEFORE_ONSET = 10
WEEKS_AFTER_ONSET = 2

# ---------------------------------------------------------------------------
# Theme-based candidate matching -- Stage 5 (theme condition; the location
# condition is TARGET_COUNTRIES above, used by the same stage)
#
# Exhaustively verified against GDELT's complete theme taxonomy
# (http://data.gdeltproject.org/api/v2/guides/LOOKUP-GKGTHEMES.TXT --
# all 8,528 TAX_DISEASE_* entries read in full, not sampled) before being
# finalized. See README "Key decisions -> theme list" for the full
# derivation and what was deliberately excluded.
# ---------------------------------------------------------------------------

FLU_INCLUDE_THEMES: frozenset[str] = frozenset({
    "TAX_DISEASE_FLU",
    "TAX_DISEASE_INFLUENZA",
    "WB_1421_INFLUENZA",
    "TAX_DISEASE_PANDEMIC_INFLUENZA",
    "TAX_DISEASE_INFLUENZA_PNEUMONIA",
    "TAX_DISEASE_INFLUENZAL_PNEUMONIA",
    "TAX_DISEASE_SWINE_FLU",
    "TAX_DISEASE_SWINE_INFLUENZA",
    "TAX_DISEASE_SWINE_FLU_H1N1",
    "TAX_DISEASE_SWINE_FLU_H3N2",
    "TAX_DISEASE_ORTHOMYXOVIRIDAE_INFECTIONS",
})

# NOT CURRENTLY USED by the active Stage 5 gate (pipeline/theme_matcher.py
# ::has_theme_match no longer checks this set -- explicit decision, see
# that module's docstring). Originally meant to override an include-theme
# match when both appear on the same record, since this project studies
# human seasonal/pandemic flu, not animal-to-animal influenza strains that
# rarely infect humans. Kept here, still exhaustively verified and correct,
# in case that check is reinstated -- wire has_excluded_theme() back into
# has_theme_match() to do so.
FLU_EXCLUDE_THEMES: frozenset[str] = frozenset({
    "TAX_DISEASE_BIRD_FLU",
    "TAX_DISEASE_AVIAN_FLU",
    "TAX_DISEASE_AVIAN_INFLUENZA",
    "TAX_DISEASE_INFLUENZA_IN_BIRDS",
    "TAX_DISEASE_H7N9",
    "TAX_DISEASE_CANINE_INFLUENZA",
    "TAX_DISEASE_EQUINE_INFLUENZA",
    "TAX_DISEASE_FELINE_INFLUENZA",
})

# OPEN DECISION -- NOT YET RESOLVED (see README "Open decisions"):
# TAX_DISEASE_JUNGLE_FLU is low-volume (17 occurrences project-wide) and its
# exact meaning wasn't confidently identified. Deliberately left out of both
# sets above rather than guessed into either one. If resolved, add it to
# FLU_INCLUDE_THEMES or FLU_EXCLUDE_THEMES with a comment explaining why.

# Generic health themes used by the content-richness co-occurrence check
# (Stage 9) -- corroborating evidence for a single isolated flu-theme hit.
GENERIC_HEALTH_THEMES: frozenset[str] = frozenset({
    "GENERAL_HEALTH",
    "MEDICAL",
    "HEALTH_VACCINATION",
    "CRISISLEX_C03_WELLBEING_HEALTH",
    "EPU_CATS_HEALTHCARE",
})

# ---------------------------------------------------------------------------
# Retrievability threshold -- Stage 8
#
# Found on a live test run, not hypothetical: some paywalled sites (e.g.
# Lee Enterprises' "BLOX" CMS, seen on omaha.com) ship the real article body
# in the raw HTML pre-obfuscated behind a CSS class like "subscriber-only
# encrypted-content", meant to be decrypted client-side via JavaScript for
# subscribers. trafilatura extracts this as if it were real text -- non-
# empty, plausible length -- but it's actually a substitution-ciphered
# blob. Measured on that live example: digit-character ratio was 28.8% in
# the garbled text vs 0.7% and 1.5% in two genuinely-extracted articles
# from the same test run. Real prose, in any language/script, essentially
# never has this many digits interspersed within word-like tokens -- see
# pipeline/quality_gates.py::is_retrievable.
# ---------------------------------------------------------------------------

MAX_DIGIT_CHAR_RATIO = 0.05

# ---------------------------------------------------------------------------
# Content-richness thresholds -- Stage 9
# ---------------------------------------------------------------------------

MIN_FLU_THEME_HITS_ALONE = 2         # >=2 flu-theme hits -> content-rich on their own
COOCCURRENCE_PROXIMITY_CHARS = 1000  # max distance (characters) between a lone flu-theme
                                      # hit and a generic health theme for it to count as corroborated

# ---------------------------------------------------------------------------
# Fetching and extraction -- Stages 6-7
# ---------------------------------------------------------------------------

HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT_SECONDS = 30
HTTP_MAX_RETRIES = 2
HTTP_BACKOFF_BASE_SECONDS = 1.0

# ---------------------------------------------------------------------------
# Storage -- Stage 10
#
# Decided: Google Drive, not an AWS/cloud-provider bucket -- a local
# filesystem backend is also provided for development/testing and needs
# zero configuration. See README "Storage -> Google Drive" for one-time
# setup (OAuth client credentials, sharing a destination folder).
# ---------------------------------------------------------------------------

StorageBackendName = Literal["local", "gdrive"]
STORAGE_BACKEND: StorageBackendName = os.environ.get("PIPELINE_STORAGE_BACKEND", "local")  # type: ignore[assignment]

LOCAL_STORAGE_DIR = os.environ.get("PIPELINE_LOCAL_STORAGE_DIR", "./output/extracted_articles")

# The Drive folder articles are uploaded into -- the ID in the folder's own
# URL (https://drive.google.com/drive/folders/<THIS_PART>), not its name.
GDRIVE_FOLDER_ID = os.environ.get("PIPELINE_GDRIVE_FOLDER_ID", "")
# OAuth client secret downloaded from Google Cloud Console (Desktop app
# credentials) -- used only for the one-time interactive consent.
GDRIVE_CREDENTIALS_PATH = os.environ.get("PIPELINE_GDRIVE_CREDENTIALS_PATH", "./credentials.json")
# Where the authorized-user token is cached after the first interactive
# login, so later runs don't need a browser again.
GDRIVE_TOKEN_PATH = os.environ.get("PIPELINE_GDRIVE_TOKEN_PATH", "./token.json")

# ---------------------------------------------------------------------------
# Run summary -- the end-of-run per-window article count report
# (run_pipeline.py::build_window_report). Always written locally, regardless
# of STORAGE_BACKEND -- it's a small human-readable report, not pipeline
# output data, so there's no reason to route it through the Drive API too.
# ---------------------------------------------------------------------------

RUN_SUMMARY_PATH = os.environ.get("PIPELINE_RUN_SUMMARY_PATH", "./output/run_summary.json")
