"""Content-richness scoring for the audit scripts (Step 2 data-quality
checks), replacing two unreliable mechanisms:

- RETRIEVABLE_MIN_TEXT_LEN alone: a pure length gate with zero boilerplate
  awareness -- a long cookie-consent or "subscribe to continue" page clears
  200 chars easily.
- CHALLENGE_MARKERS (investigation/check_aus_ind_usa_full_audit.py): a
  keyword blocklist demonstrated unreliable in practice -- of AUS's 148
  flagged articles, sampled ones had 6,000+ real characters, because a
  stray challenge-adjacent phrase ("sign in", etc.) appeared inside
  otherwise-genuine long-form prose.

This module combines several structural signals instead of one keyword scan,
so a stray phrase inside real prose doesn't get penalized, while a genuine
stub/consent/nav page fails several signals at once: real length, multiple
properly-punctuated sentences, a length-independent vocabulary-diversity
ratio (repeated short link/nav text scores low), a reasonable average
sentence length (nav fragments and link lists are short), and at least one
topical content marker.

Scope: this only feeds the read-only audit scripts (investigation/*.py). It
does not change pipeline/gdelt/article_fetcher.py's FetchedArticle.retrievable,
which remains the cheap production gate used by Step 3.
"""

import re
from dataclasses import dataclass

from pipeline.config import (
    CONTENT_MARKERS,
    CONTENT_RICHNESS_MIN_AVG_CHUNK_WORDS,
    CONTENT_RICHNESS_MIN_SENTENCES,
    CONTENT_RICHNESS_MIN_TYPE_TOKEN_RATIO,
    CONTENT_RICHNESS_STTR_WINDOW_WORDS,
    RETRIEVABLE_MIN_TEXT_LEN,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[A-Za-z']+")


@dataclass(frozen=True)
class ContentRichnessScore:
    is_content_rich: bool
    text_len: int
    sentence_count: int
    type_token_ratio: float
    avg_chunk_words: float
    content_marker_hits: int


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _standardized_type_token_ratio(words: list[str], window: int) -> float:
    """Type-token ratio over a fixed-size window rather than the whole text,
    so a long genuine article isn't penalized just for reusing common words
    more as its length grows (vocabulary-growth curves naturally flatten)."""
    sample = words[:window] if window > 0 else words
    if not sample:
        return 0.0
    return len({w.lower() for w in sample}) / len(sample)


def score_content_richness(
    text: str,
    min_len: int = RETRIEVABLE_MIN_TEXT_LEN,
    min_sentences: int = CONTENT_RICHNESS_MIN_SENTENCES,
    min_ttr: float = CONTENT_RICHNESS_MIN_TYPE_TOKEN_RATIO,
    ttr_window: int = CONTENT_RICHNESS_STTR_WINDOW_WORDS,
    min_avg_chunk_words: float = CONTENT_RICHNESS_MIN_AVG_CHUNK_WORDS,
    min_marker_hits: int = 1,
) -> ContentRichnessScore:
    stripped = text.strip()
    text_len = len(stripped)

    sentences = _split_sentences(stripped)
    sentence_count = len(sentences)

    words = _WORD_RE.findall(stripped)
    ttr = _standardized_type_token_ratio(words, ttr_window)

    avg_chunk_words = (
        sum(len(_WORD_RE.findall(s)) for s in sentences) / sentence_count
        if sentence_count
        else 0.0
    )

    lowered = stripped.lower()
    marker_hits = sum(1 for marker in CONTENT_MARKERS if marker in lowered)

    is_content_rich = (
        text_len > min_len
        and sentence_count >= min_sentences
        and ttr >= min_ttr
        and avg_chunk_words >= min_avg_chunk_words
        and marker_hits >= min_marker_hits
    )

    return ContentRichnessScore(
        is_content_rich=is_content_rich,
        text_len=text_len,
        sentence_count=sentence_count,
        type_token_ratio=round(ttr, 3),
        avg_chunk_words=round(avg_chunk_words, 2),
        content_marker_hits=marker_hits,
    )
