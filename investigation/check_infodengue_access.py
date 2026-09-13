"""
Checkpoint 1 + 2 (partial): confirm InfoDengue API access and compute season onsets
for a stratified sample of Brazilian state capitals, 2015-2024.

Geocodes below are IBGE-verified (via servicodados.ibge.gov.br), not guessed.
"""
import json
import time
import urllib.request
import urllib.error

API_BASE = "https://info.dengue.mat.br/api/alertcity"

# state capital -> (IBGE geocode, state, rough media-market tier)
CAPITALS = {
    "Sao Paulo":      (3550308, "SP", "large_metro"),
    "Rio de Janeiro": (3304557, "RJ", "large_metro"),
    "Belo Horizonte": (3106200, "MG", "large_metro"),
    "Salvador":       (2927408, "BA", "mid_metro"),
    "Fortaleza":      (2304400, "CE", "mid_metro"),
    "Recife":         (2611606, "PE", "mid_metro"),
    "Porto Alegre":   (4314902, "RS", "mid_metro"),
    "Manaus":         (1302603, "AM", "small_metro"),
    "Belem":          (1501402, "PA", "small_metro"),
    "Goiania":        (5208707, "GO", "small_metro"),
    "Curitiba":       (4106902, "PR", "mid_metro"),
    "Brasilia":       (5300108, "DF", "large_metro"),
}

YEARS = list(range(2015, 2025))


def fetch_year(geocode: int, year: int) -> list[dict]:
    url = (
        f"{API_BASE}?geocode={geocode}&disease=dengue&format=json"
        f"&ew_start=1&ew_end=52&ey_start={year}&ey_end={year}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "fse570-feasibility-spike"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"  FETCH FAILED geocode={geocode} year={year}: {e}")
        return []


def find_onset(records: list[dict], incidence_threshold: float = 10.0) -> dict | None:
    """First epi-week where incidence per 100k crosses the threshold, sustained for 2+ weeks."""
    records = sorted(records, key=lambda r: r["SE"])
    for i in range(len(records) - 1):
        inc_a = records[i].get("p_inc100k") or 0
        inc_b = records[i + 1].get("p_inc100k") or 0
        if inc_a >= incidence_threshold and inc_b >= incidence_threshold:
            return {
                "onset_week": records[i]["SE"],
                "onset_incidence": inc_a,
                "onset_cases": records[i]["casos"],
                "peak_incidence": max((r.get("p_inc100k") or 0) for r in records),
                "peak_alert_level": max((r.get("nivel_inc") or 0) for r in records),
                "total_weeks_reported": len(records),
            }
    return None


def main():
    results = {}
    total_calls = len(CAPITALS) * len(YEARS)
    call_count = 0
    for city, (geocode, uf, tier) in CAPITALS.items():
        results[city] = {"geocode": geocode, "state": uf, "tier": tier, "seasons": {}}
        for year in YEARS:
            call_count += 1
            records = fetch_year(geocode, year)
            time.sleep(0.3)  # be polite to the free public API
            if not records:
                results[city]["seasons"][year] = {"status": "no_data"}
                continue
            onset = find_onset(records)
            results[city]["seasons"][year] = {
                "status": "onset_found" if onset else "no_onset_above_threshold",
                "weeks_returned": len(records),
                **(onset or {}),
            }
        print(f"[{call_count}/{total_calls} year-calls done] {city}: "
              f"{sum(1 for s in results[city]['seasons'].values() if s['status']=='onset_found')}"
              f"/{len(YEARS)} seasons with a defined onset")

    out_path = "/Users/aditya.rallapalli/Code/projects/capstone-project/investigation/infodengue_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Checkpoint summary
    onset_units = sum(
        1
        for city_data in results.values()
        for season in city_data["seasons"].values()
        if season["status"] == "onset_found"
    )
    weeks_returned_total = sum(
        season.get("weeks_returned", 0)
        for city_data in results.values()
        for season in city_data["seasons"].values()
    )
    print("\n=== CHECKPOINT 1: InfoDengue structural access ===")
    print(f"API reachable: {'YES' if weeks_returned_total > 0 else 'NO'}")
    print(f"Total (city, year) cells queried: {total_calls}")
    print(f"Cells with weekly data returned: "
          f"{sum(1 for c in results.values() for s in c['seasons'].values() if s['status'] != 'no_data')}")
    print("\n=== CHECKPOINT 2 (city-capital slice): cohort of defined onsets ===")
    print(f"City-season units with a defined onset (>=10/100k incidence, 2+ consecutive weeks): {onset_units} "
          f"out of {total_calls} possible")
    print(f"Results written to {out_path}")


if __name__ == "__main__":
    main()
