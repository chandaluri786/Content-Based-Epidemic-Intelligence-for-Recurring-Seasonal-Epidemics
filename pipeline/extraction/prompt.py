"""Few-shot prompt builder for Step 3 extraction.

5 fixed examples (not retrieved/dynamic), chosen to cover the judgment calls
the LLM has to make: a real signal, an explainer that mentions flu without
reporting an event, a genuinely ambiguous case, a mistagged story (mirroring
the "story about a different country mistagged to Brazil" pattern already
seen in the spike data), and animal/avian flu with no human cases -- added
after a real pilot run found 35.7% of USA's matched URLs were avian/bird flu
content (2023's H5N1 outbreak), and the model initially marked a
poultry-trade avian-flu article as relevant=True before this example existed.

Kept deliberately terse (short example texts, compact JSON, tight header):
after discovering Groq's real bottleneck is a 200K tokens/day/model cap (not
the 1000 RPD first assumed), this prompt's fixed overhead directly divides
into how many articles/day the pipeline can process. Every example still
covers a distinct, empirically-motivated judgment call -- terseness came from
trimming words, not dropping categories.
"""

import json
from typing import Any, TypedDict

from pipeline.config import MAX_ARTICLE_CHARS


class FewShotExample(TypedDict):
    kind: str
    article_text: str
    output: dict[str, Any]


FEW_SHOT_EXAMPLES: list[FewShotExample] = [
    {
        "kind": "clear_positive",
        "article_text": (
            "Nairobi health officials report a flu surge, 3 deaths at Kenyatta Hospital. "
            "H3N2 confirmed. Symptoms: fever, cough, body aches."
        ),
        "output": {
            "disease_signal": True,
            "relevant": True,
            "severity": "severe",
            "symptoms": ["fever", "cough", "body aches"],
            "strain": "h3n2",
            "location_mentioned": "Nairobi",
            "confidence": 0.95,
        },
    },
    {
        "kind": "explainer_negative",
        "article_text": (
            "What is the flu? Influenza is a contagious respiratory illness. Symptoms include "
            "fever, cough, fatigue. Get your annual flu vaccine to stay protected."
        ),
        "output": {
            "disease_signal": False,
            "relevant": False,
            "severity": "unknown",
            "symptoms": ["fever", "cough", "fatigue"],
            "strain": "not_mentioned",
            "location_mentioned": None,
            "confidence": 0.9,
        },
    },
    {
        "kind": "ambiguous_low_confidence",
        "article_text": (
            "A small-town clinic noted 'a few more coughs and colds than usual' this month; "
            "no outbreak declared, too early to tell if flu-related."
        ),
        "output": {
            "disease_signal": True,
            "relevant": True,
            "severity": "unknown",
            "symptoms": ["cough"],
            "strain": "unspecified",
            "location_mentioned": None,
            "confidence": 0.3,
        },
    },
    {
        "kind": "mistagged_negative",
        "article_text": (
            "Brazil's stock market rallied Tuesday on strong earnings, with influenced trading "
            "pushing the Bovespa to a new high."
        ),
        "output": {
            "disease_signal": False,
            "relevant": False,
            "severity": "none",
            "symptoms": [],
            "strain": "not_mentioned",
            "location_mentioned": None,
            "confidence": 0.95,
        },
    },
    {
        "kind": "animal_flu_negative",
        "article_text": (
            "Agriculture officials report another avian flu wave at Midwest poultry farms, "
            "culling 2 million birds. No human infections reported."
        ),
        "output": {
            "disease_signal": True,
            "relevant": False,
            "severity": "none",
            "symptoms": [],
            "strain": "not_mentioned",
            "location_mentioned": "Midwest",
            "confidence": 0.9,
        },
    },
]

SYSTEM_PROMPT_HEADER = (
    "Extract structured HUMAN seasonal influenza signal from one news article, for "
    "comparison against WHO FluNet data. JSON only, matching the schema. Mark "
    "relevant=true ONLY for reported human flu cases -- not explainers, unrelated "
    "'flu'-adjacent stories, or animal/avian/swine flu with no human infections "
    "(a real disease event, but not human seasonal flu). Examples:\n"
)


def _build_system_prompt() -> str:
    parts = [SYSTEM_PROMPT_HEADER]
    for example in FEW_SHOT_EXAMPLES:
        compact_output = json.dumps(example["output"], separators=(",", ":"))
        parts.append(f"[{example['kind']}] {example['article_text']} -> {compact_output}")
    return "\n".join(parts)


def build_extraction_messages(article_text: str, country_hint: str) -> list[dict[str, str]]:
    """Build the system + user chat messages for one extraction call."""
    truncated_text = article_text[:MAX_ARTICLE_CHARS]
    user_content = f"Country: {country_hint}\nArticle: {truncated_text}"
    return [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": user_content},
    ]
