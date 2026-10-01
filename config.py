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

# Presence of ANY of these overrides an include-theme match, even if both
# appear on the same record -- this project studies human seasonal/pandemic
# flu, not animal-to-animal influenza strains that rarely infect humans.
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
# OPEN DECISION, DEFAULTED (see README "Open decisions"): no cloud provider
# had been specified at the time this pipeline was built. S3 was chosen as
# the default real cloud backend since it's the most common choice for this
# kind of workload; a local filesystem backend is also provided for
# development/testing and needs zero configuration. Swap STORAGE_BACKEND to
# a different value and implement the corresponding class in
# pipeline/storage.py if a different provider is actually wanted.
# ---------------------------------------------------------------------------

StorageBackendName = Literal["local", "s3"]
STORAGE_BACKEND: StorageBackendName = os.environ.get("PIPELINE_STORAGE_BACKEND", "local")  # type: ignore[assignment]

LOCAL_STORAGE_DIR = os.environ.get("PIPELINE_LOCAL_STORAGE_DIR", "./output/extracted_articles")

S3_BUCKET_NAME = os.environ.get("PIPELINE_S3_BUCKET", "")
S3_KEY_PREFIX = os.environ.get("PIPELINE_S3_PREFIX", "flu-extraction/")
S3_REGION = os.environ.get("AWS_REGION", "us-east-1")
