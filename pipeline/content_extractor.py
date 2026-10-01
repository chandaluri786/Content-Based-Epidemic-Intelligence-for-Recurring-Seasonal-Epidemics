"""
Stage 7: extract just the article body from raw HTML, discarding navigation,
ads, comment forms, and other page boilerplate.

Uses trafilatura -- see README "Key building blocks -> trafilatura" for why
this replaced a naive tag-stripping approach and what independent benchmark
evidence backs the choice.
"""

from __future__ import annotations

from dataclasses import dataclass

import trafilatura


@dataclass(frozen=True)
class ExtractionResult:
    """Just the cleaned text. trafilatura can also return title/author/date
    metadata, but none of that is part of the final stored record (see
    README "Final storage structure") so it's not extracted at all --
    no point paying for metadata parsing that's discarded immediately."""
    text: str | None


def extract(raw_html: str) -> ExtractionResult:
    """favor_precision=True: when a block of text is ambiguous (could be
    real content or could be boilerplate), lean toward excluding it. Better
    to risk losing a borderline paragraph than to let navigation/ad text
    leak into what's treated as article content."""
    text = trafilatura.extract(raw_html, include_comments=False, favor_precision=True)
    return ExtractionResult(text=text)
