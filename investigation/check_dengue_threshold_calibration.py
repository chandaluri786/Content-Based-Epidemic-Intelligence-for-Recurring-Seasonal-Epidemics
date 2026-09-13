"""
Follow-up item 3: check whether the flat >=10 cases/100k-for-2-weeks dengue onset rule
under-detected activity in low-onset-count capitals (Belem: 2/10, Curitiba: 2/10), the
same failure mode a flat threshold already caused for flu (UK/Japan both hit 0/10 under
FluNet's flat rule due to different reporting baselines).

Pre-registered alternative rule (decided before computing): each city's own 75th
percentile of its complete 2015-2024 weekly incidence series (city-relative, not a shared
cross-city number), same "sustained 2+ consecutive weeks" structure.

Re-fetches the full weekly InfoDengue series per capital -- the existing
infodengue_results.json only stored onset summaries, not the full series needed to
compute a per-city percentile.
"""
import json
import time
import urllib.request
import urllib.error

API_BASE = "https://info.dengue.mat.br/api/alertcity"

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
FLAT_THRESHOLD = 10.0
PERCENTILE = 75


def fetch_year(geocode, year):
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


def percentile(values, pct):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def find_onset(records, threshold):
    """First week where incidence >= threshold for 2+ consecutive weeks. Returns (week, value) or None."""
    records = sorted(records, key=lambda r: r["SE"])
    for i in range(len(records) - 1):
        v1 = records[i].get("p_inc100k") or 0
        v2 = records[i + 1].get("p_inc100k") or 0
        if v1 >= threshold and v2 >= threshold:
            return records[i]["SE"], v1
    return None


def main():
    all_city_records = {}
    for city, (geocode, uf, tier) in CAPITALS.items():
        yearly = {}
        for year in YEARS:
            recs = fetch_year(geocode, year)
            time.sleep(0.3)
            yearly[year] = recs
        all_city_records[city] = {"geocode": geocode, "tier": tier, "yearly": yearly}
        n_weeks = sum(len(r) for r in yearly.values())
        print(f"{city}: fetched {n_weeks} weeks across {len(YEARS)} years")

    results = {}
    flat_onset_incidences = []  # for cross-city reference distribution
    for city, data in all_city_records.items():
        all_incidences = [
            r.get("p_inc100k") or 0
            for recs in data["yearly"].values()
            for r in recs
        ]
        city_p75 = percentile(all_incidences, PERCENTILE)

        flat_onsets, relative_onsets = {}, {}
        for year, recs in data["yearly"].items():
            if not recs:
                continue
            flat = find_onset(recs, FLAT_THRESHOLD)
            relative = find_onset(recs, city_p75) if city_p75 else None
            if flat:
                flat_onsets[year] = flat
                flat_onset_incidences.append(flat[1])
            if relative:
                relative_onsets[year] = relative

        results[city] = {
            "tier": data["tier"],
            "city_p75_incidence": round(city_p75, 2) if city_p75 else None,
            "flat_onset_count": len(flat_onsets),
            "relative_onset_count": len(relative_onsets),
            "flat_onsets": {y: {"week": w, "incidence": round(v, 2)} for y, (w, v) in flat_onsets.items()},
            "relative_onsets": {y: {"week": w, "incidence": round(v, 2)} for y, (w, v) in relative_onsets.items()},
        }
        print(f"{city} ({data['tier']}): p75={city_p75:.2f} | flat rule {len(flat_onsets)}/10 | "
              f"relative rule {len(relative_onsets)}/10")

    out_path = "/Users/aditya.rallapalli/Code/projects/capstone-project/investigation/dengue_threshold_calibration_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    total_flat = sum(r["flat_onset_count"] for r in results.values())
    total_relative = sum(r["relative_onset_count"] for r in results.values())
    median_flat_onset_incidence = sorted(flat_onset_incidences)[len(flat_onset_incidences) // 2] if flat_onset_incidences else None

    print("\n=== ITEM 3 SUMMARY ===")
    print(f"Original flat-rule (>= {FLAT_THRESHOLD}/100k, 2wk) cohort: {total_flat}/120")
    print(f"New relative-rule (city's own p{PERCENTILE}, 2wk) cohort: {total_relative}/120")
    print(f"Reference: median incidence at flat-rule onsets across all cities = {median_flat_onset_incidence:.2f}/100k")
    print()
    for city in ["Belem", "Curitiba"]:
        r = results[city]
        rel_incidences = [v["incidence"] for v in r["relative_onsets"].values()]
        print(f"{city}: flat={r['flat_onset_count']}/10, relative={r['relative_onset_count']}/10, "
              f"p75={r['city_p75_incidence']}, relative-onset incidences={rel_incidences}")
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
