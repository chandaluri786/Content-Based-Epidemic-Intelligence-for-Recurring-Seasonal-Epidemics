"""
Stage 5: decide whether a parsed GkgRecord is a flu candidate.

Two independent conditions, both required:
  1. Theme match -- at least one include-listed theme, none of the
     exclude-listed (animal-flu) ones. Theme-based, not URL-keyword-based:
     GDELT's theme tags are computed from the article's actual (translated,
     where needed) content, so this doesn't share the English-URL-only
     limitation a keyword filter would have. See README "Stage 5" for the
     measured evidence behind this choice.
  2. Location match -- at least one of the six cohort countries appears
     anywhere in the record's locations. A flat presence check,
     deliberately simple: it answers "is this worth keeping at all," not
     "which country is this really about" -- that attribution question was
     tried twice (country bucketing, then plain country tagging) and
     removed both times because a presence-only check can't answer it
     reliably. See README "Stage 5 -> location filtering" for that history.

Both conditions gate whether a record is kept; neither restricts what gets
stored once it passes -- a kept article's full, unfiltered `locations` list
(every place GDELT found, not just the matched cohort country) is still
carried through to storage. See README "Final storage structure."
"""

from __future__ import annotations

from config import FLU_EXCLUDE_THEMES, FLU_INCLUDE_THEMES, TARGET_COUNTRIES
from models import GkgRecord, ThemeHit


def flu_theme_hits(record: GkgRecord) -> list[ThemeHit]:
    return [hit for hit in record.themes if hit.theme in FLU_INCLUDE_THEMES]


def has_excluded_theme(record: GkgRecord) -> bool:
    return any(hit.theme in FLU_EXCLUDE_THEMES for hit in record.themes)


def has_theme_match(record: GkgRecord) -> bool:
    """Condition 1: at least one include-listed theme, none excluded.
    Exclusion wins even if an include theme is also present on the same
    record."""
    if has_excluded_theme(record):
        return False
    return len(flu_theme_hits(record)) > 0


def countries_mentioned(record: GkgRecord, target_countries: dict[str, str] = TARGET_COUNTRIES) -> set[str]:
    """Every target country whose FIPS code appears anywhere in this
    record's locations -- flat presence check, not an attribution claim.
    Used both for condition 2 below and available for callers that want
    the actual set, not just a yes/no.

    target_countries defaults to the full cohort (config.TARGET_COUNTRIES)
    but accepts a narrower dict -- run_pipeline.py passes exactly the
    countries requested on the CLI, so `--countries USA` actually scopes
    the location filter to the US only, not silently falling back to the
    full six-country config regardless of what was asked for."""
    present_fips = {loc.country_fips for loc in record.locations}
    return {iso3 for iso3, fips in target_countries.items() if fips in present_fips}


def has_location_match(record: GkgRecord, target_countries: dict[str, str] = TARGET_COUNTRIES) -> bool:
    """Condition 2: mentions at least one of the requested countries."""
    return len(countries_mentioned(record, target_countries)) > 0


def is_flu_candidate(record: GkgRecord, target_countries: dict[str, str] = TARGET_COUNTRIES) -> bool:
    """A record is a candidate only if BOTH the theme and location
    conditions hold. This is the single content filter in the pipeline --
    nothing downstream re-checks either condition."""
    return has_theme_match(record) and has_location_match(record, target_countries)
