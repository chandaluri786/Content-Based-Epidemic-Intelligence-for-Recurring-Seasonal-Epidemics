"""
Stage 4: parse one raw GKG 2.1 line into a structured GkgRecord.

Field positions and sub-field formats confirmed empirically against live
GKG data (not assumed from documentation alone):
  - field 5  (index 4):  DocumentIdentifier -- the article URL
  - field 9  (index 8):  Themes_V2 -- ';'-separated "THEME,offset" entries
  - field 11 (index 10): Locations_V2 -- ';'-separated '#'-delimited 9-tuples
                          (type#name#FIPS#adm1#adm2#lat#lon#featureid#offset)

This is the step that determines what's available to every later stage --
the original version of this pipeline only kept the URL and a flat set of
FIPS codes from locations, discarding themes entirely and discarding every
location sub-field except the FIPS code. This version keeps the character
offsets too, since Stage 9 needs them for the proximity check.
"""

from __future__ import annotations

import csv

from models import GkgRecord, LocationHit, ThemeHit

_IDX_RECORD_ID = 0
_IDX_TIMESTAMP = 1
_IDX_URL = 4
_IDX_THEMES_V2 = 8
_IDX_LOCATIONS_V2 = 10
_MIN_FIELDS = _IDX_LOCATIONS_V2 + 1

_LOCATION_SUBFIELD_COUNT = 9


def _parse_themes(field: str) -> tuple[ThemeHit, ...]:
    hits = []
    for entry in field.split(";"):
        if not entry:
            continue
        theme, _, offset = entry.partition(",")
        if offset.isdigit():
            hits.append(ThemeHit(theme=theme, char_offset=int(offset)))
    return tuple(hits)


def _parse_locations(field: str) -> tuple[LocationHit, ...]:
    hits = []
    for entry in field.split(";"):
        if not entry:
            continue
        parts = entry.split("#")
        if len(parts) != _LOCATION_SUBFIELD_COUNT:
            # Confirmed rare (~0.07%) in a live audit of 150k+ entries --
            # skip rather than guess at a malformed record's meaning.
            continue
        offset = int(parts[8]) if parts[8].isdigit() else -1
        hits.append(LocationHit(
            location_type=parts[0], name=parts[1], country_fips=parts[2],
            adm1=parts[3], adm2=parts[4], lat=parts[5], lon=parts[6],
            feature_id=parts[7], char_offset=offset,
        ))
    return tuple(hits)


def parse_line(raw_line: str) -> GkgRecord | None:
    """Returns None if the line is too short to contain the fields we need,
    or has no URL -- both confirmed to happen occasionally in real GDELT
    data, not treated as exceptional errors."""
    fields = next(csv.reader([raw_line], delimiter="\t"), None)
    if fields is None or len(fields) < _MIN_FIELDS:
        return None

    url = fields[_IDX_URL].strip()
    if not url:
        return None

    return GkgRecord(
        record_id=fields[_IDX_RECORD_ID],
        timestamp=fields[_IDX_TIMESTAMP],
        url=url,
        themes=_parse_themes(fields[_IDX_THEMES_V2]),
        locations=_parse_locations(fields[_IDX_LOCATIONS_V2]),
    )
