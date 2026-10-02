"""
Stages 8-9: retrievability and content-richness.

Deliberately does NOT attempt to verify that an article genuinely reports
case counts, deaths, or active spread -- that requires reading the text's
actual meaning (an LLM or real NLP), which is out of scope for this
credential-free, no-LLM-dependency pipeline. This is a disclosed, known
limitation -- see README "Known limitations" -- not something quietly
assumed to be handled.
"""

from __future__ import annotations

from config import (
    COOCCURRENCE_PROXIMITY_CHARS,
    GENERIC_HEALTH_THEMES,
    MAX_DIGIT_CHAR_RATIO,
    MIN_FLU_THEME_HITS_ALONE,
)
from models import GkgRecord, ThemeHit
from pipeline.content_extractor import ExtractionResult


def is_retrievable(extraction: ExtractionResult) -> bool:
    """Retrievable = trafilatura found real, readable extractable text.

    Three failure modes were found and rejected, in order:
      - raw HTTP status alone: a bot-block page can return 200 OK with a
        tiny stub body, which isn't genuinely "retrieved."
      - raw text length on the UNCLEANED html: a cookie-consent banner can
        easily clear a 200-character floor while containing zero article
        content.
      - non-empty extracted text alone: some paywalled sites ship the real
        article body pre-obfuscated in the raw HTML (decrypted client-side
        via JS for subscribers only) -- trafilatura extracts this as
        plausible-looking, non-empty text, but it's a substitution-ciphered
        blob, not readable content. See config.py's MAX_DIGIT_CHAR_RATIO
        comment for the live example and the measured digit-ratio evidence
        this check is based on.
    A bot-block stub typically yields no extractable article body at all;
    an obfuscated-paywall blob yields text with an abnormally high digit
    ratio. Both are caught here."""
    text = extraction.text
    if not text or not text.strip():
        return False
    digit_ratio = sum(c.isdigit() for c in text) / len(text)
    return digit_ratio <= MAX_DIGIT_CHAR_RATIO


def _nearby_generic_health_theme(flu_hit: ThemeHit, all_themes: tuple[ThemeHit, ...], proximity: int) -> bool:
    return any(
        other.theme in GENERIC_HEALTH_THEMES and abs(other.char_offset - flu_hit.char_offset) <= proximity
        for other in all_themes
    )


def is_content_rich(record: GkgRecord, matched_flu_hits: list[ThemeHit]) -> bool:
    """>=2 independent flu-theme hits -> content-rich on their own.

    Exactly 1 hit -> content-rich only if a generic health theme occurs
    nearby, corroborating that it's not an isolated coincidental mention.
    (The concrete case this rule exists to catch: an article about China's
    COVID-19 protocol got a single TAX_DISEASE_INFLUENZA hit purely because
    it named the organization "Global Initiative on Sharing Avian Influenza
    Data" -- confirmed on real data, not hypothetical.)"""
    if len(matched_flu_hits) >= MIN_FLU_THEME_HITS_ALONE:
        return True
    if len(matched_flu_hits) == 1:
        return _nearby_generic_health_theme(matched_flu_hits[0], record.themes, COOCCURRENCE_PROXIMITY_CHARS)
    return False
