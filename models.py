"""Shared data structures passed between pipeline stages.

Kept separate from the stage modules so any stage can import the shapes it
needs without creating circular imports between stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ThemeHit:
    """One GDELT theme tag and the character position it was found at."""
    theme: str
    char_offset: int


@dataclass(frozen=True)
class LocationHit:
    """One parsed entry from GDELT's V2Locations field (9 sub-fields,
    confirmed against live data -- see pipeline/gkg_parser.py)."""
    location_type: str
    name: str
    country_fips: str
    adm1: str
    adm2: str
    lat: str
    lon: str
    feature_id: str
    char_offset: int


@dataclass(frozen=True)
class GkgRecord:
    """One fully parsed raw GKG 2.1 line -- Stage 4's output."""
    record_id: str
    timestamp: str
    url: str
    themes: tuple[ThemeHit, ...]
    locations: tuple[LocationHit, ...]


@dataclass(frozen=True)
class CountrySeasonWindow:
    """One country's ingestion window for one flu season -- Stage 2's output."""
    country_iso3: str
    season_year: int
    onset_date: date
    window_start: date
    window_end: date


@dataclass
class MatchedArticle:
    """A GkgRecord that passed Stage 5's combined theme-and-location gate
    -- the only content filter in the pipeline. The gate only answers "is
    this worth keeping at all"; it makes no claim about which mentioned
    country the article is really about -- the record's full, unfiltered
    location list is carried straight through to storage for a human
    labeler to judge that. See README "Stage 5" for the full reasoning."""
    record: GkgRecord
    flu_theme_hits: list[ThemeHit]    # just the include-list hits, carried forward for Stage 9


@dataclass
class ExtractedArticle:
    """Final record, after fetch + clean + quality gates -- storage's input.

    Deliberately trimmed to just what's useful for downstream human
    labeling: the article's own identity and timing, what GDELT tagged it
    with, every place it mentions, and the cleaned text itself. No author,
    no media links, no pass/fail gate flags -- a record only exists here at
    all if it already passed both quality gates (see pipeline/quality_gates.py)."""
    gkg_record_id: str
    url: str
    gkg_datetime: str                  # ISO 8601, converted from the raw GKG scan timestamp
    themes: list[ThemeHit]             # the flu-specific theme hits that made this a candidate (Stage 5)
    locations: list[LocationHit]       # every location GDELT found -- full, unfiltered; see README
    article_text: str
