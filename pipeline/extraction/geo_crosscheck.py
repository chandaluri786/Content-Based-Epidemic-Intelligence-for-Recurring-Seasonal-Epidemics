"""Geotagging cross-check: GDELT's assigned country tag vs. the LLM extraction
step's own `primary_country` judgment (Step 3).

GDELT's V2Locations tagging is confirmed unreliable (see
dev/active/flu-pipeline/context.md): a UK content-farm article about Australia
mistagged as Brazil, a US wire story mistagged to 71.8% of Kenya's matched
articles, and an Australian bird-flu story mistagged to 132 India articles.
This module implements the agree/ambiguous/disagree verdict used to exclude
confidently-mistagged articles while keeping genuinely ambiguous ones.
"""

from typing import Literal

GeoVerdict = Literal["agree", "ambiguous", "disagree"]


def classify_geo_match(primary_country: str | None, gdelt_country: str) -> GeoVerdict:
    """Compare the LLM's extracted primary_country against GDELT's country tag.

    `None` means the article was genuinely ambiguous/global in scope -- not a
    confident disagreement, so it stays in (flagged, not excluded). Any other
    value that isn't an exact match to `gdelt_country` (including "other") is
    a confident disagreement.
    """
    if primary_country is None:
        return "ambiguous"
    if primary_country == gdelt_country:
        return "agree"
    return "disagree"
