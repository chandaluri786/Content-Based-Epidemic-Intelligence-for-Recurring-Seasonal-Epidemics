"""Rule-based relevance pre-filter (Step 4), applied before any LLM call.

An article must contain at least `min_markers` of the validated content-marker
terms before it's worth spending an LLM call on. This is a cost gate only --
the actual relevant/confidence judgment on surviving articles is made by the
LLM in the same structured-output call as the rest of extraction (see
llm_client.py), not by this prefilter and not by a second LLM call.
"""

from pipeline.config import CONTENT_MARKERS


def passes_rule_prefilter(text: str, min_markers: int = 1) -> bool:
    lowered = text.lower()
    hits = sum(1 for marker in CONTENT_MARKERS if marker in lowered)
    return hits >= min_markers
