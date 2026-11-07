"""Central configuration: file locations and model settings.

Everything that a user might reasonably want to change lives here, so the other
modules contain no hard-coded paths or magic numbers. Model settings and the results
folder can be overridden with environment variables (or lines in the `.env` file).

All inputs live inside the project folder, so nothing depends on where the capstone
files are on disk (see scripts/build_gold_files.py for how they were produced).
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# --- Locations (all inside the project) --------------------------------------

# The `llm-extractor` folder (this file is llm-extractor/flu_extractor/config.py).
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Read `.env` once, here, so that every module sees the same environment.
load_dotenv(PROJECT_DIR / ".env")

PROMPTS_DIR = PROJECT_DIR / "prompts"
DATA_DIR = PROJECT_DIR / "data"

# The prompt version. The three prompt files below are named after it, and
# scripts/build_gold_files.py makes the system prompt from prompt_versions/llm_extraction_prompt_<version>.md.
# PROMPT_VERSION in .env selects another version (README section "Making changes").
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v5.2")
SYSTEM_PROMPT_PATH = PROMPTS_DIR / f"system_prompt_{PROMPT_VERSION}.txt"  # the rules, word for word
# The one set of solved examples, sent as chat turns (written by scripts/select_examples.py).
# EXAMPLES_PATH in .env points at another file instead.
EXAMPLES_PATH = Path(os.getenv("EXAMPLES_PATH", PROMPTS_DIR / f"examples_{PROMPT_VERSION}.json"))
# How to learn from the examples. Added after the rules only when examples are sent, so a
# zero-shot run is the rules alone.
FEWSHOT_GUIDE_PATH = PROMPTS_DIR / f"fewshot_guide_{PROMPT_VERSION}.txt"

# Inputs for the run: the articles to send and the gold answers to score against. Both are built
# from the v5.2 label records by scripts/build_gold_files.py (no human labels are used).
ARTICLES_PATH = DATA_DIR / "articles.json"
GOLD_LABELS_PATH = DATA_DIR / "gold_labels.json"
# The chain-of-thought record files the gold labels are built from: every <Name><RECORDS_SUFFIX>
# file in RECORDS_DIR. RECORDS_SUFFIX in .env selects another label version.
RECORDS_DIR = DATA_DIR / "chain_of_thought"
RECORDS_SUFFIX = os.getenv("RECORDS_SUFFIX", "_labels_v5.2.jsonl")

# Prompt 5.1: every city, state and country has one agreed form, its name in OpenStreetMap in this
# language. Gold and model values are turned into it (places.agreed_names) before they are checked,
# matched, scored or combined. PLACE_NAME_LANGUAGE in .env selects another language.
PLACE_NAME_SOURCE = "openstreetmap"   # Nominatim, OpenStreetMap's geocoder (the only source supported)
PLACE_NAME_LANGUAGE = os.getenv("PLACE_NAME_LANGUAGE", "en")
# The saved answers of the place lookups. It is not a list of allowed places: a chain not in it is
# asked online and then added, so each chain is asked once and later runs give the same names.
PLACE_CACHE_PATH = DATA_DIR / "place_lookups.json"

# Review decisions on duplicate candidates in gold (distinct / duplicate / unresolved). The
# evaluator reads it if it exists; duplicate_candidates.csv in each run lists the groups to review.
ADJUDICATION_PATH = DATA_DIR / "duplicate_adjudication.json"

# Every run writes its own sub-folder here.
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", PROJECT_DIR / "results"))

# --- Model settings ----------------------------------------------------------

# DeepSeek V4.1 Flash, served by NVIDIA's OpenAI-compatible API (the V4 Flash line; NVIDIA lists
# only the 4.1 build). Change NVIDIA_MODEL_ID in .env to use another model on the same API.
BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
MODEL_ID = os.getenv("NVIDIA_MODEL_ID", "deepseek-ai/deepseek-v4.1-flash")

# Decoding settings chosen for the least run-to-run variation: greedy decoding (temperature 0,
# top_p 1, no penalties), a fixed seed, and the same settings on every request, retries included.
TEMPERATURE = 0
TOP_P = 1
# Upper limit for the reply only. The longest gold reply is 15,683 characters, roughly 5,000 tokens.
MAX_TOKENS = 8000
# Seconds to wait for one reply. NVIDIA's queue for this model is slow: a 15-token test request
# took 153 s on 2026-11-05, and a real request carries ~30k prompt tokens with the examples.
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "900"))
# Hard limit on the total time of one request. The timeout above counts only the wait between two
# pieces of data, so a server that keeps a connection open (e.g. sends keep-alive bytes) without ever
# answering never trips it: on 2026-11-07 a DeepSeek run waited over an hour that way. A request
# past this limit is given up and retried like a timeout. REQUEST_DEADLINE_SECONDS in .env changes it.
DEFAULT_REQUEST_DEADLINE_SECONDS = 600.0


def parse_deadline(text: str | None) -> float:
    """The deadline in seconds from REQUEST_DEADLINE_SECONDS, or the default when it is unset or blank."""
    if text is None or not text.strip():
        return DEFAULT_REQUEST_DEADLINE_SECONDS
    try:
        seconds = float(text)
    except ValueError as error:
        raise RuntimeError(f"REQUEST_DEADLINE_SECONDS in .env must be a number of seconds, not {text!r}") from error
    if seconds <= 0:
        raise RuntimeError(f"REQUEST_DEADLINE_SECONDS in .env must be above 0, not {text!r}")
    return seconds


REQUEST_DEADLINE_SECONDS = parse_deadline(os.getenv("REQUEST_DEADLINE_SECONDS"))
# Retries after a rate-limit, timeout, connection or server error (done in llm_client.ask_model).
MAX_RETRIES = 4
# Requests repeated, with a note naming the problem, when a reply is cut off, not valid JSON, breaks
# the prompt's format or quotes evidence that is not in the article (done in extractor.extract_article).
# The last one asks for a compact reply; the decoding settings never change.
MAX_VALIDATION_RETRIES = 3
# A fixed seed, so that any sampling on the server is repeatable (temperature 0 already removes ours).
SEED = 20261101
# Stop a run after this many API failures in a row (e.g. the daily quota is used up). The run can
# be resumed later with --run-dir.
STOP_AFTER_CONSECUTIVE_API_ERRORS = 5
# The API allows 40 requests per minute. Every request, retries included, counts. The window is a
# little over 60 s so that clock differences between us and the server cannot push us over.
REQUESTS_PER_MINUTE = int(os.getenv("NVIDIA_REQUESTS_PER_MINUTE", "40"))
RATE_WINDOW_SECONDS = 61.0
# Model-specific request options. No separate thinking block: the v5 reply carries its reasoning
# inside the JSON, and a hidden thinking pass adds tokens, time and variation. The switch depends on
# the API, so EXTRA_BODY_JSON in .env can replace the default:
#   NVIDIA (default): DeepSeek's chat template reads "thinking" (verified: 0 reasoning tokens).
#   DeepSeek's own API: thinking is ON by default there; EXTRA_BODY_JSON={"thinking": {"type": "disabled"}}.
#   Nemotron on NVIDIA: {"chat_template_kwargs": {"enable_thinking": false}}.
DEFAULT_EXTRA_BODY = {"chat_template_kwargs": {"thinking": False}}


def parse_extra_body(text: str | None) -> dict:
    """The request options from EXTRA_BODY_JSON, or the default when it is unset or blank."""
    if text is None or not text.strip():
        return DEFAULT_EXTRA_BODY
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"EXTRA_BODY_JSON in .env is not valid JSON ({error}): {text!r}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"EXTRA_BODY_JSON in .env must be a JSON object such as "
                           f'{{"thinking": {{"type": "disabled"}}}}, not {text!r}')
    return value


EXTRA_BODY = parse_extra_body(os.getenv("EXTRA_BODY_JSON"))
# Sent as the x-session-affinity header on every request when set. Fireworks caches a prompt prefix
# only inside one replica; one fixed value sends every request of a run to the same replica, so the
# shared prefix (rules and examples) is a cache hit. Empty = no header (NVIDIA, DeepSeek's own API).
SESSION_AFFINITY = os.getenv("SESSION_AFFINITY", "").strip()


def get_api_key() -> str:
    """Return the NVIDIA API key from the environment, or fail with a clear message."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "NVIDIA_API_KEY is not set. Add a line NVIDIA_API_KEY=... to the .env file."
        )
    return api_key
