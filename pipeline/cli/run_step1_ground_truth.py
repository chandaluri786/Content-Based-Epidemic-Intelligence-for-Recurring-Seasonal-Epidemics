"""Step 1: fetch the full FluNet + UKHSA weekly series for all 8 cohort
countries, 2015-2024, compute onset dates per country-season, and write one
row per country-season to data/ground_truth/country_seasons.csv.
"""

import csv
import time
from pathlib import Path

from pipeline.ground_truth.ground_truth_builder import build_ground_truth_table

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "data" / "ground_truth" / "country_seasons.csv"

FIELDNAMES = [
    "country_iso3",
    "country_display",
    "year",
    "source",
    "onset_method",
    "onset_iso_week",
    "onset_date",
    "value_at_onset",
    "data_quality_flag",
    "included_in_gdelt_cohort",
]


def main() -> None:
    started = time.monotonic()
    rows = build_ground_truth_table()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "country_iso3": row.country_iso3,
                    "country_display": row.country_display,
                    "year": row.year,
                    "source": row.source,
                    "onset_method": row.onset_method,
                    "onset_iso_week": row.onset_iso_week or "",
                    "onset_date": row.onset_date.isoformat() if row.onset_date else "",
                    "value_at_onset": row.value_at_onset if row.value_at_onset is not None else "",
                    "data_quality_flag": row.data_quality_flag,
                    "included_in_gdelt_cohort": row.included_in_gdelt_cohort,
                }
            )

    onsets_found = sum(1 for r in rows if r.onset_date is not None)
    cohort_rows = [r for r in rows if r.included_in_gdelt_cohort]
    cohort_onsets = sum(1 for r in cohort_rows if r.onset_date is not None)

    elapsed = time.monotonic() - started
    print(f"Wrote {len(rows)} country-season rows to {OUTPUT_PATH} in {elapsed:.1f}s")
    print(f"Onsets found (all 8 countries): {onsets_found}/{len(rows)}")
    print(f"Onsets found (6-country GDELT cohort): {cohort_onsets}/{len(cohort_rows)}")
    for r in rows:
        if r.data_quality_flag != "ok":
            print(
                f"  flag={r.data_quality_flag:16s} {r.country_iso3} {r.year} "
                f"source={r.source} method={r.onset_method}"
            )


if __name__ == "__main__":
    main()
