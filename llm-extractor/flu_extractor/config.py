"""Central configuration: file locations and model settings.

Everything that a user might reasonably want to change lives here, so the other
modules contain no hard-coded paths or magic numbers. Model settings and the results
folder can be overridden with environment variables (or lines in the `.env` file).

All inputs live inside the project folder, so nothing depends on where the capstone
files are on disk (see scripts/build_data_files.py for how they were produced).
"""

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

# The prompt. To try a new prompt version, add new files and point these at them.
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt_v5.1.txt"  # the rules, word for word
# Solved examples, sent as chat turns. EXAMPLES_PATH in .env selects another set, e.g. the
# k=4, 8, 12 candidates (prompts/examples_v5.1_k8.json), without editing this file.
EXAMPLES_PATH = Path(os.getenv("EXAMPLES_PATH", PROMPTS_DIR / "examples_v5.1.json"))
# How to learn from the examples. Added after the rules only when examples are sent, so a
# zero-shot run is the rules alone.
FEWSHOT_GUIDE_PATH = PROMPTS_DIR / "fewshot_guide_v5.1.txt"

# Inputs for the run: the articles to send, the gold answers to score against, and the human
# `useful` answers, kept as a second comparison.
ARTICLES_PATH = DATA_DIR / "articles.json"
GOLD_LABELS_PATH = DATA_DIR / "gold_labels.json"
HUMAN_LABELS_PATH = DATA_DIR / "human_labels.json"
# The fixed development sample used to compare example sets.
DEV_SAMPLE_PATH = DATA_DIR / "dev_sample_200.txt"

# Answers of the place check (is this a real city / state / country?), one per name, so that
# each name is looked up only once and later runs repeat exactly.
PLACE_CACHE_PATH = DATA_DIR / "place_lookups.json"

# Every run writes its own sub-folder here.
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", PROJECT_DIR / "results"))

# --- Model settings ----------------------------------------------------------

BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
MODEL_ID = os.getenv("NVIDIA_MODEL_ID", "nvidia/nemotron-3.5-lightning-30b-a3b")

# 0 makes the output as repeatable as the server allows, so prompt versions can be compared.
TEMPERATURE = 0
# Upper limit for the reply only. The longest gold reply is 15,683 characters, roughly 5,000 tokens.
MAX_TOKENS = 8000
# Seconds to wait for one reply; the prompt is ~30k tokens with examples, so replies are slow.
REQUEST_TIMEOUT_SECONDS = 300
# Retries after a rate-limit, timeout, connection or server error (done in llm_client.ask_model).
MAX_RETRIES = 4
# Requests repeated, with a note naming the problem, when a reply is cut off, not valid JSON or
# breaks the reply format (done in extractor.extract_article). The last one asks for a compact
# reply at LAST_RETRY_TEMPERATURE: at temperature 0 a repeated request tends to repeat the mistake.
MAX_VALIDATION_RETRIES = 3
LAST_RETRY_TEMPERATURE = 0.3
# A fixed seed, so that any sampling on the server is repeatable (temperature 0 already removes ours).
SEED = 20261101
# Stop a run after this many API failures in a row (e.g. the daily quota is used up). The run can
# be resumed later with --run-dir.
STOP_AFTER_CONSECUTIVE_API_ERRORS = 5
# The API allows 40 requests per minute. Every request, retries included, counts. The window is a
# little over 60 s so that clock differences between us and the server cannot push us over.
REQUESTS_PER_MINUTE = int(os.getenv("NVIDIA_REQUESTS_PER_MINUTE", "40"))
RATE_WINDOW_SECONDS = 61.0
# Nemotron-specific switch: no separate thinking block. The v5 reply carries its reasoning in JSON.
EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}


def get_api_key() -> str:
    """Return the NVIDIA API key from the environment, or fail with a clear message."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "NVIDIA_API_KEY is not set. Add a line NVIDIA_API_KEY=... to the .env file."
        )
    return api_key
