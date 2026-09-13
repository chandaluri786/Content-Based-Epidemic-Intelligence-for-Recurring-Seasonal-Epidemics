"""Parse one raw GKG 2.1 CSV line into a minimal structured record.

Field positions confirmed empirically against live GKG data (not assumed from
docs alone): field[4] is the article URL (DocumentIdentifier), field[10] is
V2Locations -- a ';'-separated list of '#'-separated tuples
(type#name#FIPS_country_code#adm1#lat#lon#featureid#offset). We only need the
URL and the set of FIPS country codes mentioned.
"""

from dataclasses import dataclass

_URL_FIELD_INDEX = 4
_LOCATIONS_FIELD_INDEX = 10
_MIN_FIELDS = _LOCATIONS_FIELD_INDEX + 1
_LOCATION_FIPS_SUBFIELD_INDEX = 2


@dataclass(frozen=True)
class GkgRecord:
    url: str
    country_codes: frozenset[str]


def _extract_country_codes(locations_field: str) -> frozenset[str]:
    codes: set[str] = set()
    for location in locations_field.split(";"):
        subfields = location.split("#")
        if len(subfields) > _LOCATION_FIPS_SUBFIELD_INDEX:
            fips = subfields[_LOCATION_FIPS_SUBFIELD_INDEX].strip()
            if fips:
                codes.add(fips)
    return frozenset(codes)


def parse_gkg_line(line: str) -> GkgRecord | None:
    fields = line.rstrip("\n").split("\t")
    if len(fields) < _MIN_FIELDS:
        return None

    url = fields[_URL_FIELD_INDEX].strip()
    if not url:
        return None

    return GkgRecord(url=url, country_codes=_extract_country_codes(fields[_LOCATIONS_FIELD_INDEX]))
