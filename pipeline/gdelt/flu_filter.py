"""URL-level flu-candidate filter (Step 2), reusing the word-boundary regex
already validated in the feasibility spike -- a naive `"flu" in url` substring
match false-positived on "fluid", "hydrofluoric", "influencer", "Flutter
Entertainment", etc.
"""

import re

from pipeline.config import FLU_TERM_REGEX, GDELT_FIPS_COUNTRY_CODE
from pipeline.gdelt.gkg_parser import GkgRecord

FLU_TERM_RE = re.compile(FLU_TERM_REGEX, re.IGNORECASE)


def find_matching_countries(record: GkgRecord, target_countries: list[str]) -> list[str]:
    """Return every target ISO3 country whose GDELT FIPS code is mentioned in
    this record's locations, provided the URL also contains a genuine
    flu/influenza term. Checks all target countries in one pass so a single
    day's parsed lines can be filtered against the whole cohort at once."""
    if not FLU_TERM_RE.search(record.url):
        return []

    return [
        iso3
        for iso3 in target_countries
        if GDELT_FIPS_COUNTRY_CODE.get(iso3) in record.country_codes
    ]
