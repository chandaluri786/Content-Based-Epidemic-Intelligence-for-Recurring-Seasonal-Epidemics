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

# The prompt, in two files. To try a new prompt version, add new files and point these at them.
# Build them with `python scripts/build_prompt_files.py <version>`.
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt_v2.1.txt"  # instructions only
EXAMPLES_PATH = PROMPTS_DIR / "examples_v2.1.json"           # solved examples, sent as chat turns

# Inputs for the run: the articles to send, and the human answers to score against.
ARTICLES_PATH = DATA_DIR / "articles.json"
HUMAN_LABELS_PATH = DATA_DIR / "human_labels.json"

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
# Upper limit for the reply only. The longest labeled answer is estimated at ~1,800 tokens.
MAX_TOKENS = 4000
# Seconds to wait for one reply; the prompt is ~25-30k tokens, so replies are slow.
REQUEST_TIMEOUT_SECONDS = 300
# The OpenAI client retries rate-limit, timeout and server errors this many times by itself.
MAX_RETRIES = 4
# Nemotron-specific switch: answer directly instead of writing out its reasoning first.
EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}


def get_api_key() -> str:
    """Return the NVIDIA API key from the environment, or fail with a clear message."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "NVIDIA_API_KEY is not set. Add a line NVIDIA_API_KEY=... to the .env file."
        )
    return api_key
