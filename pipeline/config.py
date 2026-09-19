"""Single source of truth for every named constant in the pipeline.

No module should hardcode a threshold, URL, or magic number that appears here.
"""

from typing import Literal, NamedTuple

# ---------------------------------------------------------------------------
# Cohort definition
# ---------------------------------------------------------------------------

OnsetMethod = Literal["positivity_2wk", "peak_count_proxy"]


class CountryDef(NamedTuple):
    name: str
    income_tier: str
    hemisphere: str
    onset_method: OnsetMethod
    included_in_gdelt_cohort: bool


# UK/GBR has zero WHO FluNet records (structural gap -> UKHSA dashboard) and JPN's
# FluNet records lack a specimen-processed denominator (-> peak-count proxy); both
# are computed for ground-truth documentation only. Team decision: excluded from
# GDELT ingestion (Step 2) and the detection/lead-time test (Step 6) to keep a
# uniform 6-country cohort with one onset-detection method (flat FluNet
# positivity_2wk threshold), no per-country exceptions.
# BRA/IDN use that same flat method and are included in the cohort despite
# confirmed thinner GDELT flu content (33% retrievable/content-rich vs the
# >=60%/>=50% bar for the other countries) -- a disclosed limitation, not an
# oversight; see dev/active/flu-pipeline/context.md.
COUNTRIES: dict[str, CountryDef] = {
    "USA": CountryDef("United States", "high_income", "NH", "positivity_2wk", True),
    "GBR": CountryDef("United Kingdom", "high_income", "NH", "positivity_2wk", False),
    "JPN": CountryDef("Japan", "high_income", "NH", "peak_count_proxy", False),
    "AUS": CountryDef("Australia", "high_income", "SH", "positivity_2wk", True),
    "BRA": CountryDef("Brazil", "upper_middle_income", "SH", "positivity_2wk", True),
    "IND": CountryDef("India", "lower_middle_income", "NH", "positivity_2wk", True),
    "KEN": CountryDef("Kenya", "low_income", "SH_equatorial", "positivity_2wk", True),
    "IDN": CountryDef("Indonesia", "lower_middle_income", "SH_equatorial", "positivity_2wk", True),
}

# UK has no FluNet data at all; UKHSA covers England only, not Scotland/Wales/NI.
# Never silently equate "England" with "UK" in output or reporting.
UK_ISO3 = "GBR"
UKHSA_GEOGRAPHY = "England"

YEARS: list[int] = list(range(2015, 2025))

# GDELT's V2Locations field uses FIPS 10-4 country codes, not ISO3 -- these
# differ for several of our cohort countries (UK not GB, JA not JP) and were
# confirmed empirically against live GKG data, not assumed from documentation.
GDELT_FIPS_COUNTRY_CODE: dict[str, str] = {
    "USA": "US",
    "GBR": "UK",
    "JPN": "JA",
    "AUS": "AS",
    "BRA": "BR",
    "IND": "IN",
    "KEN": "KE",
    "IDN": "ID",
}

MIN_COHORT_SIZE = 40

# ---------------------------------------------------------------------------
# Ground truth onset rule (Step 1)
# ---------------------------------------------------------------------------

ONSET_POSITIVITY_THRESHOLD_PCT = 10.0
ONSET_SUSTAIN_WEEKS = 2

# ---------------------------------------------------------------------------
# External APIs
# ---------------------------------------------------------------------------

FLUNET_API_URL = "https://xmart-api-public.who.int/FLUMART/VIW_FNT"
FLUNET_PAGE_SIZE = 100
FLUNET_USER_AGENT = "flu-epidemic-intelligence-pipeline"

UKHSA_API_BASE = "https://api.ukhsa-dashboard.data.gov.uk"
UKHSA_METRIC = "influenza_testing_positivityByWeek"
UKHSA_TOPIC = "Influenza"
UKHSA_PAGE_SIZE = 100

# ---------------------------------------------------------------------------
# GDELT ingestion (Step 2)
# ---------------------------------------------------------------------------

GDELT_RAW_MIRROR_BASE = "https://data.gdeltproject.org/gdeltv2"
GDELT_WEEKS_BEFORE_ONSET = 10
GDELT_WEEKS_AFTER_ONSET = 2
GDELT_EARLIEST_AVAILABLE_DATE = "2015-02-19"  # GKG 2.0 launch date

MIN_FREE_DISK_GB = 5.0

FLU_TERM_REGEX = r"(?:^|[-_/])(flu|influenza)(?:[-_/]|$)"

CONTENT_MARKERS: list[str] = [
    "case",
    "cases",
    "hospitaliz",
    "death",
    "outbreak",
    "epidemic",
    "strain",
    "h1n1",
    "h3n2",
    "influenza b",
    "surge",
    "vaccine",
    "severe",
    "world health organization",
]

RETRIEVABLE_MIN_TEXT_LEN = 200

# Content-richness structural scoring (pipeline/gdelt/content_richness.py),
# replacing the demonstrated-unreliable CHALLENGE_MARKERS keyword blocklist
# (investigation/check_aus_ind_usa_full_audit.py: 148/10,451 AUS articles
# flagged, but sampled ones had 6,000+ real characters -- a stray keyword
# inside genuine long-form text, not real boilerplate). Placeholder values,
# calibrated empirically in Phase 3b validation against the 148 known AUS
# false positives and the near-threshold short USA examples before being
# treated as final -- see dev/active/flu-pipeline/context.md.
CONTENT_RICHNESS_MIN_SENTENCES = 3
CONTENT_RICHNESS_STTR_WINDOW_WORDS = 100  # standardized TTR window, length-independent
CONTENT_RICHNESS_MIN_TYPE_TOKEN_RATIO = 0.4
CONTENT_RICHNESS_MIN_AVG_CHUNK_WORDS = 6.0

# ---------------------------------------------------------------------------
# LLM extraction (Step 3)
# ---------------------------------------------------------------------------

GROQ_API_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_FALLBACK_MODEL = "openai/gpt-oss-20b"

# Empirically confirmed against the live API (2026-09-13), not assumed: the
# response headers (x-ratelimit-limit-requests=1000, reset-requests spacing
# exactly 86.4s = 86400s/1000 per call) confirm a 1000 requests/day (RPD)
# rolling-window cap for openai/gpt-oss-120b -- there is no separate RPM
# throttle (6 back-to-back calls in 3.2s all succeeded). The daily cap, not
# request pacing, is the real constraint for any batch over ~1000 articles.
GROQ_RPD_LIMIT = 1000
GROQ_MIN_INTERVAL_SECONDS = 0.2  # light safety margin only; no RPM cap observed

# Every model checked has the same 1000 RPD cap except allam-2-7b (7000 RPD,
# but it flatly rejects response_format=json_schema -- not usable here).
# The RPD cap was confirmed empirically to be tracked PER MODEL, not
# account-wide (a burst of calls to one model did not move another model's
# remaining-requests counter), so waterfalling across every structured-
# output-capable model multiplies today's effective throughput. Order
# matters only in that MultiModelExtractionClient exhausts each entry before
# moving to the next.
GROQ_EXTRACTION_MODEL_POOL: list[str] = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

MAX_ARTICLE_CHARS = 1500  # cut from 6000 after discovering Groq's 200K TPD/model cap is the
# real bottleneck (not the 1000 RPD first found) -- news articles front-load key facts, so
# quality was spot-checked at this length against full-length extractions before adopting it.
EXTRACTION_MAX_TOKENS = 300  # our JSON schema output is small; previously unbounded
# gpt-oss-120b/20b are reasoning models -- confirmed empirically that their default
# reasoning effort spends 100-400+ completion tokens on hidden reasoning before emitting
# any JSON, which blew EXTRACTION_MAX_TOKENS on nearly every call once the schema's
# primary_country field (geo cross-check) made the judgment harder. "low" keeps the
# response inside budget without raising max_tokens, which would directly cut the
# TPD-bound daily throughput; qwen3.8-27b (not a reasoning model) accepts the param
# without error and simply ignores it.
GROQ_REASONING_EFFORT = "low"
EXTRACTION_MAX_RETRIES = 3
EXTRACTION_BACKOFF_BASE_SECONDS = 2.0

RELEVANCE_CONFIDENCE_THRESHOLD = 0.6

# ---------------------------------------------------------------------------
# Detection rule (Step 6)
# ---------------------------------------------------------------------------

BASELINE_WEEKS = 4
DETECTION_Z_SCORE = 2.0
DETECTION_MIN_ABSOLUTE_FLOOR = 3
DETECTION_SUSTAIN_WEEKS = 2
MIN_TOTAL_ARTICLES_FOR_DETECTION = 10
