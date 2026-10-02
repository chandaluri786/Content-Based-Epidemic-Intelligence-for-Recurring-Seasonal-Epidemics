"""
Unit tests for Stage 8's is_retrievable -- pure function of extracted text,
no network needed. Run with: pytest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.content_extractor import ExtractionResult
from pipeline.quality_gates import is_retrievable

# Real garbled text pulled from a live test run (omaha.com, a Lee
# Enterprises "BLOX" CMS site) -- the raw HTML stores this pre-obfuscated
# behind a "subscriber-only encrypted-content" CSS class, decrypted
# client-side via JavaScript for subscribers only. trafilatura has no way
# to decrypt it and just extracts the still-encrypted string.
_PAYWALL_GARBLED_TEXT = (
    "kAm!2E:6?ED H:E9 r~'xs\\`h 2C6 7:==:?8 @?=J 92=7 E96 ?F>36C @7 365D "
    "E92E E96J H6C6 2E E9:D E:>6 =2DE J62C[ H9:49 :D 8@@5 ?6HD 7@C }63C2D<2VD"
)

_REAL_ARTICLE_TEXT = (
    "In the emergency department at MLK Community Hospital, masked patients "
    "lay in wheeled stretchers lining the hallways. Others slumped in chairs "
    "where nurses attended to them. Amid the crush of people on a recent night."
)


def test_is_retrievable_true_for_real_prose():
    assert is_retrievable(ExtractionResult(text=_REAL_ARTICLE_TEXT))


def test_is_retrievable_false_for_empty_text():
    assert not is_retrievable(ExtractionResult(text=None))
    assert not is_retrievable(ExtractionResult(text="   "))


def test_is_retrievable_false_for_obfuscated_paywall_text():
    """The actual failure case this check was added for -- see
    config.py's MAX_DIGIT_CHAR_RATIO comment for the measured digit-ratio
    evidence (28.8% garbled vs 0.7%-1.5% real, from the same live test
    run)."""
    assert not is_retrievable(ExtractionResult(text=_PAYWALL_GARBLED_TEXT))
