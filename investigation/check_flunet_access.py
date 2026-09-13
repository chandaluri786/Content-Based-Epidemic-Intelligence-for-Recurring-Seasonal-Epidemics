"""
Flu/FluNet fallback: Checkpoint 1 + 2. Confirms WHO xMart public FluNet API access
and computes season onsets for a stratified sample of countries, 2015-2024,
mirroring Ganser et al.'s 24-country design (mix of income tiers and hemispheres).
"""
import csv
import io
import time
import urllib.request
import urllib.parse

API = "https://xmart-api-public.who.int/FLUMART/VIW_FNT"

COUNTRIES = {
    "USA": ("United States", "high_income", "NH"),
    "GBR": ("United Kingdom", "high_income", "NH"),
    "JPN": ("Japan", "high_income", "NH"),
    "AUS": ("Australia", "high_income", "SH"),
    "BRA": ("Brazil", "upper_middle_income", "SH"),
    "IND": ("India", "lower_middle_income", "NH"),
    "KEN": ("Kenya", "low_income", "SH_equatorial"),
    "IDN": ("Indonesia", "lower_middle_income", "SH_equatorial"),
}

YEARS = list(range(2015, 2025))


def fetch_country_year(iso3: str, year: int) -> list[dict]:
    filt = f"COUNTRY_CODE eq '{iso3}' and ISO_YEAR eq {year}"
    params = {"$format": "csv", "$filter": filt, "$top": 100}
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "fse570-feasibility-spike"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  FETCH FAILED {iso3} {year}: {e}")
        return []
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def find_onset(records: list[dict], positivity_threshold: float = 10.0) -> dict | None:
    """First week where % positive (INF_ALL / SPEC_PROCESSED_NB) crosses threshold for 2+ weeks."""
    def pct_pos(r):
        try:
            processed = float(r.get("SPEC_PROCESSED_NB") or 0)
            inf_all = float(r.get("INF_ALL") or 0)
            return (inf_all / processed * 100) if processed > 0 else None
        except (ValueError, TypeError):
            return None

    rows = sorted(records, key=lambda r: (r.get("ISO_YEAR", ""), int(r.get("ISO_WEEK") or 0)))
    for i in range(len(rows) - 1):
        p1, p2 = pct_pos(rows[i]), pct_pos(rows[i + 1])
        if p1 is not None and p2 is not None and p1 >= positivity_threshold and p2 >= positivity_threshold:
            return {
                "onset_week": rows[i].get("ISO_WEEK"),
                "onset_pct_positive": round(p1, 1),
                "peak_pct_positive": round(max((pct_pos(r) or 0) for r in rows), 1),
                "weeks_with_data": len(rows),
            }
    return None


def main():
    results = {}
    total_calls = len(COUNTRIES) * len(YEARS)
    call_count = 0
    for iso3, (name, tier, hemi) in COUNTRIES.items():
        results[iso3] = {"name": name, "tier": tier, "hemisphere": hemi, "seasons": {}}
        for year in YEARS:
            call_count += 1
            records = fetch_country_year(iso3, year)
            time.sleep(0.3)
            if not records:
                results[iso3]["seasons"][year] = {"status": "no_data"}
                continue
            onset = find_onset(records)
            results[iso3]["seasons"][year] = {
                "status": "onset_found" if onset else "no_onset_above_threshold",
                "weeks_returned": len(records),
                **(onset or {}),
            }
        n_onsets = sum(1 for s in results[iso3]["seasons"].values() if s["status"] == "onset_found")
        print(f"[{call_count}/{total_calls}] {name} ({tier}, {hemi}): {n_onsets}/{len(YEARS)} seasons with onset")

    out_path = "/Users/aditya.rallapalli/Code/projects/capstone-project/investigation/flunet_results.json"
    import json
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    onset_units = sum(
        1 for c in results.values() for s in c["seasons"].values() if s["status"] == "onset_found"
    )
    reachable_cells = sum(
        1 for c in results.values() for s in c["seasons"].values() if s["status"] != "no_data"
    )
    print("\n=== CHECKPOINT 1: FluNet structural access ===")
    print(f"API reachable: {'YES' if reachable_cells > 0 else 'NO'}")
    print(f"Cells with data returned: {reachable_cells}/{total_calls}")
    print("\n=== CHECKPOINT 2: cohort of defined onsets (8-country slice) ===")
    print(f"Country-season units with defined onset (>=10% positivity, 2+ consecutive weeks): {onset_units} of {total_calls}")
    print(f"Results written to {out_path}")


if __name__ == "__main__":
    main()
