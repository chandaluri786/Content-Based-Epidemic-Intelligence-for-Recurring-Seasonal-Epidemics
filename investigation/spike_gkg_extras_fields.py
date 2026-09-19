"""Phase 0 spike: what does a raw GKG 2.1 record actually contain beyond the
two fields (`url`, `country_codes`) the production parser extracts today?

Empirically checks three questions that gate the term-matching fix design
(see dev plan: checkpoint-1 term-matching fix):

  1. Is V2.1ExtrasXML populated with a <PAGE_TITLE> tag, and how often?
  2. Does V2EnhancedThemes carry any disease-relevant taxonomy code?
  3. Does V2.1TranslationInfo reliably flag non-English source articles?
  4. Pre-term-filter candidate volume/day per country (bounds the cost of a
     live-fetch-per-candidate alternative if title metadata is unreliable).

Reuses pipeline.gdelt.raw_downloader's zip access (in-memory only, same as
production) but parses every tab field of each line instead of just the two
fields gkg_parser.py extracts today. Throwaway/investigation-only script --
not part of the production pipeline.
"""

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import GDELT_FIPS_COUNTRY_CODE
from pipeline.gdelt.raw_downloader import download_zip_bytes, iter_records_from_zip_bytes

# Raw GKG 2.1 field indices beyond the two the production parser uses.
# Derived from the documented GKG 2.1 codebook field ordering (1-indexed
# field N -> 0-indexed N-1, same convention the production parser's
# field[4]=V2DocumentIdentifier / field[10]=V2EnhancedLocations already
# confirm empirically): V2EnhancedThemes=9th field->idx 8,
# V2.1TranslationInfo=26th field->idx 25, V2.1ExtrasXML=27th field->idx 26.
# Presence/emptiness is verified empirically below, not just trusted from
# this derivation.
_V2_THEMES_FIELD_INDEX = 8
_EXTRAS_XML_FIELD_INDEX = 26
_TRANSLATION_INFO_FIELD_INDEX = 25
_LOCATIONS_FIELD_INDEX = 10

_PAGE_TITLE_RE = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.IGNORECASE | re.DOTALL)

# Sample stamps pulled from real dates already known to contain BRA/IND/KEN/IDN
# matches in data/gdelt_matched/{iso3}.jsonl, so we're inspecting real
# non-English-market candidate traffic, not guessing at dates.
SAMPLE_STAMPS = [
    "20150302063000",  # BRA match date
    "20151125193000",  # IND match date
    "20221227190000",  # KEN match date
    "20151026113000",  # IDN match date
]

TARGET_COUNTRIES = ["USA", "AUS", "BRA", "IND", "KEN", "IDN"]


def inspect_stamp(stamp: str) -> dict:
    raw_zip = download_zip_bytes(stamp)
    import io
    import zipfile

    title_present = 0
    title_empty = 0
    total_lines = 0
    theme_samples: Counter[str] = Counter()
    translation_flagged = 0
    country_candidate_counts: Counter[str] = Counter()  # FIPS-match only, no term filter

    fips_to_iso3 = {v: k for k, v in GDELT_FIPS_COUNTRY_CODE.items() if v}

    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        name = zf.namelist()[0]
        with zf.open(name) as f:
            for line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
                fields = line.rstrip("\n").split("\t")
                if len(fields) <= _LOCATIONS_FIELD_INDEX:
                    continue
                total_lines += 1

                # Pre-term-filter candidate volume: does this line's V2Locations
                # mention any target country's FIPS code, before any term check?
                locations_field = fields[_LOCATIONS_FIELD_INDEX]
                codes_in_line = {
                    loc.split("#")[2].strip()
                    for loc in locations_field.split(";")
                    if len(loc.split("#")) > 2 and loc.split("#")[2].strip()
                }
                for fips in codes_in_line:
                    iso3 = fips_to_iso3.get(fips)
                    if iso3 in TARGET_COUNTRIES:
                        country_candidate_counts[iso3] += 1

                if len(fields) > _EXTRAS_XML_FIELD_INDEX:
                    extras = fields[_EXTRAS_XML_FIELD_INDEX]
                    m = _PAGE_TITLE_RE.search(extras)
                    if m and m.group(1).strip():
                        title_present += 1
                    else:
                        title_empty += 1

                if len(fields) > _V2_THEMES_FIELD_INDEX:
                    themes_field = fields[_V2_THEMES_FIELD_INDEX]
                    for theme in themes_field.split(";"):
                        theme_name = theme.split(",")[0] if theme else ""
                        if theme_name and (
                            "DISEASE" in theme_name.upper()
                            or "EPIDEMIC" in theme_name.upper()
                            or "HEALTH" in theme_name.upper()
                            or "PANDEMIC" in theme_name.upper()
                        ):
                            theme_samples[theme_name] += 1

                if len(fields) > _TRANSLATION_INFO_FIELD_INDEX:
                    translation_field = fields[_TRANSLATION_INFO_FIELD_INDEX]
                    if translation_field.strip():
                        translation_flagged += 1

    del raw_zip
    return {
        "stamp": stamp,
        "total_lines": total_lines,
        "title_present": title_present,
        "title_empty": title_empty,
        "title_present_pct": round(100 * title_present / total_lines, 1) if total_lines else 0.0,
        "disease_theme_samples": dict(theme_samples.most_common(10)),
        "translation_flagged": translation_flagged,
        "translation_flagged_pct": round(100 * translation_flagged / total_lines, 1)
        if total_lines
        else 0.0,
        "pre_filter_candidate_counts": dict(country_candidate_counts),
    }


def main() -> None:
    results = []
    for stamp in SAMPLE_STAMPS:
        print(f"Fetching {stamp}...", file=sys.stderr)
        try:
            result = inspect_stamp(stamp)
        except Exception as exc:  # noqa: BLE001 -- investigation script, report and continue
            print(f"  FAILED: {exc}", file=sys.stderr)
            continue
        results.append(result)
        print(f"  total_lines={result['total_lines']}")
        print(
            f"  title_present={result['title_present']} "
            f"({result['title_present_pct']}%) title_empty={result['title_empty']}"
        )
        print(f"  disease_theme_samples={result['disease_theme_samples']}")
        print(
            f"  translation_flagged={result['translation_flagged']} "
            f"({result['translation_flagged_pct']}%)"
        )
        print(f"  pre_filter_candidate_counts={result['pre_filter_candidate_counts']}")
        print()

    import json

    out_path = Path(__file__).resolve().parent / "spike_gkg_extras_fields_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
