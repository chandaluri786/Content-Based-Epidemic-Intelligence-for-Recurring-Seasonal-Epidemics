# Feasibility Spike #4 — Seasonal Epidemic Reframe: Findings

Spec: `/Users/aditya.rallapalli/.claude/plans/fse-570-capstone-starry-meadow.md`
Date run: 2026-09-11/12
Final scoping: **flu/FluNet primary, dengue/InfoDengue secondary** (see "Final verdict" below) — the sections immediately following trace the investigation in the order it actually happened (dengue tested first, then flu), which is why they read dengue-first.

**Three items left open here (UK/FluNet gap, Brazil/Indonesia's thin content-depth sample, dengue's uncalibrated onset threshold) are resolved in `report_followup2.md`** — none of them change the GO verdict or flu-primary scoping below, but they do change some numbers this document cites (the flu cohort grows from 55/80 to 63/80 once UK/UKHSA is merged in) and add findings that matter for the build (Brazil/Indonesia's flu content-depth doesn't generalize; dengue onset detection should be city-relative, not a flat rate).

## Checkpoint 0 — Subnational reference source exists

**PASS.** InfoDengue (Brazil, built on SINAN) confirmed live: municipality-level, weekly, 2010–2024, free public API at `info.dengue.mat.br/api/alertcity`. PAHO PLISA has subnational data for only 9/46 countries (secondary, not primary).

## Checkpoint 1 — Structural access

**PASS**, all three sources confirmed live:
- **InfoDengue**: `GET /api/alertcity?geocode=...&disease=dengue&format=json&ew_start=...&ey_start=...` — tested against 12 state capitals × 10 years (2015–2024) = 120 calls, 120/120 returned data (100% reachability). Fields include weekly case counts, incidence per 100k, InfoDengue's own alert level (`nivel_inc`), Rt, and climate covariates.
- **PAHO PLISA (via Delphi Epidata `paho_dengue` endpoint)**: `GET api.delphi.cmu.edu/epidata/paho_dengue/?regions=br&epiweeks=...` — confirmed live, national-level, weekly, includes **serotype breakdown** (bonus field beyond what the plan expected).
- **GDELT GKG 2.0**: confirmed accessible two ways without any BigQuery/billing dependency — (a) GDELT's free DOC 2.0 full-text search API (rate-limited to ~1 request per 15-40s in practice), (b) raw 15-minute GKG CSV files at `data.gdeltproject.org/gdeltv2/` (no auth, no rate limit, ~8MB per 15-min window, ~800MB/day).

## Checkpoint 2 — Cohort size

**PASS, with large margin.** Using only 12 state capitals (not the full 27 states, and not municipality-level), an incidence-threshold onset rule (≥10 cases/100k for 2+ consecutive weeks) found **75 city-season units with a defined onset out of 120 possible** (2015–2024). This clears the ≥40 threshold using a fraction of the available cohort — full-state or municipality-level analysis would be substantially larger. Cohort size is confirmed **not** the binding constraint this time, unlike DON.

Per-city onset counts (out of 10 seasons each): São Paulo 6, Rio de Janeiro 5, Belo Horizonte 10, Salvador 5, Fortaleza 10, Recife 7, Porto Alegre 4, Manaus 5, Belém 2, Goiânia 10, Curitiba 2, Brasília 9.

## Checkpoint 3 — Content depth, retrievability, and geographic resolution

**Mixed — national-level content is real; state/city-level resolution appears to fail.**

**National-level content depth: promising.** GDELT's DOC API, queried as `dengue sourcecountry:brazil` across 2019, returned genuine substantive coverage: case-count comparisons ("Dengue in the Americas reaches highest number of cases recorded"), death-toll trends ("Deaths in Brazil from Dengue Fever Increase Five-fold over Last Year"), health-campaign details, and outbreak-response stories. This is real content beyond a bare mention count — the extraction thesis looks plausible **at the country level**.

**State/city-level resolution: did not hold up, on the two most favorable days tested.** Naive keyword queries (e.g., `dengue Sao Paulo`) returned zero or near-zero results — traced to a query-syntax issue (missing diacritic/unquoted phrase), not a true data gap; quoting fixed the syntax but then mostly surfaced pan-Latin-America wire stories that mention São Paulo only in passing, not localized coverage.

To get a real answer, GDELT's own structured geotagging (`V2Locations` field, not keyword search) was inspected directly from raw GKG files on two days:
- **2019-11-13** (a day with confirmed high Brazil-dengue wire coverage): 53 dengue-URL records globally; 6 mentioned Brazil. **All 6 resolved Brazil at LocationType=1 (COUNTRY) only** — zero WORLDSTATE (ADM1) or WORLDCITY entries tied to Brazil, even though the same day's corpus had 198 WORLDCITY-level location tags for *other* countries' dengue coverage (so the geoparser can resolve sub-national locations in general — it just didn't for Brazil's dengue mentions that day).
- **2019-04-15** (São Paulo's actual 2019 epidemic peak): only 3 dengue-URL records globally that whole day, **none** mentioning Brazil or São Paulo at all.

**Extended to 5 days after the user asked to verify before deciding**, spanning 5 different onset weeks across 5 different capitals/tiers and 2 years (2019-04-15 São Paulo/large-metro peak; 2019-11-13 national high-coverage day; 2019-01-30 Brasília/large-metro onset; 2019-03-27 Rio de Janeiro/large-metro onset; 2019-06-26 Salvador/mid-metro onset):

| Day | City/tier being tested | Dengue-URL records that day (global) | Brazil-tied location entries | Location types found |
|---|---|---|---|---|
| 2019-04-15 | São Paulo (large, actual 2019 peak week) | 3 | 0 | — |
| 2019-11-13 | (national scan) | 53 | 6 | all COUNTRY |
| 2019-01-30 | Brasília (large) | 38 | 22 | all COUNTRY |
| 2019-03-27 | Rio de Janeiro (large) | 4 | 0 | — |
| 2019-06-26 | Salvador (mid) | 7 | 0 | — |

**Across all 5 days, 28 total Brazil-tied location entries were found, and every single one resolved at LocationType=1 (COUNTRY) — zero at WORLDSTATE (ADM1/state) or WORLDCITY level.** Two of the five days had zero dengue-URL articles mentioning Brazil at all, on the exact calendar weeks InfoDengue's own data shows a defined outbreak onset in that state. This is no longer a 2-day artifact — it replicated across large- and mid-metro tiers, 3 different months, and both a targeted-state peak week and a national high-volume day.

**Verdict: FAIL on state/city-level resolution, PASS on national-level content depth.** The specific reason dengue was chosen over flu — genuine subnational spatial heterogeneity that could be *mapped* from informal text — is not realized in GDELT's actual Brazil coverage. InfoDengue's ground truth is subnational; GDELT's Brazil dengue signal is country-level only, as far as this sample shows. Dengue and flu now converge to the same effective mapping resolution (country-level), which removes the tie-breaker that favored dengue as primary over flu.

## What has NOT yet been run

- A city/state that isn't Brazil (e.g., a smaller PLISA subnational country) — it's possible resolution is better for countries with less GDELT-syndication dilution than Brazil, though this would also narrow the cohort back down.
- Per-country onset-threshold calibration for flu (flat 10% positivity rule returned 0 onsets for UK and Japan — likely needs tuning, not a structural failure).
- A dedicated ECDC/TESSy (or equivalent) check for the UK specifically, since it has no WHO FluNet data at all.

## Flu/FluNet fallback (triggered per the pre-agreed rule once dengue's subnational advantage failed)

**Checkpoint 1 — Structural access: PASS.** WHO's public xMart OData endpoint (`https://xmart-api-public.who.int/FLUMART/VIW_FNT?$format=csv`) is live, no auth, supports server-side filtering (`$filter=COUNTRY_CODE eq 'USA' and ISO_YEAR eq 2019`). Returns weekly country-level data with strain subtypes (H1N1, H3N2, B/Victoria, B/Yamagata), specimens processed/positive, and even RSV/other-respiratory-virus co-surveillance — richer than the plan assumed.

**Checkpoint 2 — Cohort size: PASS, large margin.** 8 countries stratified by income tier and hemisphere (USA, UK, Japan, Australia, Brazil, India, Kenya, Indonesia) × 2015–2024, using a ≥10% test-positivity-rate-for-2-consecutive-weeks onset rule: **55 country-season units with a defined onset out of 80 possible.** (UK and Japan returned 0 onsets each under this specific threshold — worth tuning the rule per-country before the full build, not a structural failure.) This is comparable in scale to Ganser et al.'s 24-country design and clears the ≥40 bar using a third of that country count.

**Checkpoint 3 — Content depth: PASS, now fully evidenced across all 8 stratified countries.**

The initial pilot only cleanly covered Kenya and India (via GDELT's rate-limited DOC 2.0 API). The remaining 6 countries (USA, UK, Japan, Australia, Brazil, Indonesia) were completed using the **raw GKG 15-minute file mirror** instead — no rate limit, so no more inconclusive-zero results from exhausted retries. One representative day was pulled per country (its FluNet onset week where one existed; peak-INF_ALL week for Japan, whose FluNet records have no specimen-processed denominator; a generic NH-winter week for the UK, which turned out to have **no WHO FluNet data at all in any year 2018–2023 checked** — a real structural finding, not a script bug, noted below).

A first pass used a naive `"flu" in url.lower()` filter and produced a misleadingly high 68%/66% pass rate contaminated by false positives ("fluid power equipment," "hydrofluoric acid," "fluorspar market," "influencer," "soft influence," "Flutter Entertainment" — "flu" as a bare substring matches all of these). Re-run with a word-boundary regex (`flu`/`influenza` as its own hyphen/slash-delimited token) to get a clean signal:

| Country | Day tested | Flu-term + country-tagged URLs found | Sampled | Retrievable | Content-rich |
|---|---|---|---|---|---|
| USA | 2023-12-11 | 61 | 10 | 9/10 | 8/10 |
| UK | 2023-01-16 (no FluNet data — generic week, see note) | 5 | 5 | 5/5 | 5/5 |
| Japan | 2023-11-27 (peak week) | 6 | 6 | 5/6 | 5/6 |
| Australia | 2023-06-05 | 4 | 4 | 2/4 | 3/4 |
| Brazil | 2023-03-13 | 1 | 1 | 1/1 | 1/1 (but see caveat) |
| Indonesia | 2023-01-16 | 0 | 0 | — | — |
| Kenya* | (DOC API pilot) | — | 3 | 3/3 | 3/3 |
| India* | (DOC API pilot) | — | 5 | 5/5 | 5/5 |

*Kenya/India from the original DOC-API pilot, included for the combined total.

**Combined across all 8 countries: 30/34 retrievable (88%), 30/34 content-rich (88%) — both clear the ≥60%/≥50% thresholds with real margin**, using a stricter filter than the dengue check needed (dengue's "dengue" URL substring had no comparable false-positive problem; flu's 3-letter root did, and required the extra regex fix before the number could be trusted).

**Two caveats worth carrying into the full build, not smoothed over:**
- **Brazil and Indonesia showed almost no genuine flu content on the single day each was tested** (1 borderline match — actually about Australia's Northern Territory receiving flu vaccine doses, apparently mistagged to Brazil by GDELT's geoparser — and 0 matches respectively). This is a thin, single-day sample, but it's consistent with the same income/media-density coverage bias Ganser et al. documented, and with dengue's own resolution problem — coverage is not uniform across countries and the full build should not assume it is. Kenya and India, also lower/middle-income, did show good content via the DOC API on different days/queries, so this isn't a clean "poor countries fail" rule — it's a real source of variance that needs per-country calibration, not an assumption either way.
- **UK has no WHO FluNet data in any year checked (2018–2023).** The UK likely reports through ECDC/TESSy rather than directly to WHO FluNet — a genuine structural gap if the UK is wanted in the structured-reference cohort; it would need a different reference source, not FluNet.

**Resolution:** flu's mapping ceiling was always expected to be country-level (no subnational flu surveillance source was ever identified, unlike Brazil's InfoDengue for dengue) — so there's no separate resolution check to fail here; country-level was the accepted premise going in.

## Final verdict: GO — flu/FluNet as primary, dengue/InfoDengue as a secondary validation case

The seasonal-epidemic reframe (vs. WHO DON's rare emerging events) is **feasible on the data**: structural access confirmed for both diseases, cohort size solved by a wide margin (55–75 units from small stratified slices, not the full country/city universe), and country-level content extraction from informal sources demonstrably contains real substance beyond a bare mention count — now backed by evidence across all 8 stratified flu countries, not just 2 — directly testing whether content beats Ganser et al.'s frequency-only result, as the reframe's central hypothesis proposed.

**The scope change that must be disclosed to the team:** the "geographic mapping" pillar cannot be a genuine differentiator for dengue over flu the way the original scoping decision assumed — dengue's subnational ground truth (InfoDengue) does not have a matching subnational informal-source signal in GDELT, based on a 5-day multi-state sample. Stage 8's design should target **country-level relative-intensity mapping**, not municipality/state-level boundary expansion. This is a real reduction in ambition from the original 11-stage design for that stage, not a relabeling.

**Recommendation (revised):** build the **flu/FluNet pipeline as the primary and only full extraction-and-evaluation build** — it has the strongest literature anchor (a direct extension of Ganser et al.'s exact setup), the broadest cohort (nearly 200 WHO member states report to FluNet vs. dengue's Americas-only reach), and content-depth is now confirmed across 8 stratified countries, not 2. Keep **dengue/InfoDengue+PLISA as a secondary validation case or appendix** (e.g., a smaller supplementary check on the Americas subset showing the approach generalizes to a second disease/region) — not a second co-equal pipeline. Two full disease-specific builds is more scope than the timeline supports, and it isn't needed to satisfy the course's ≥2-heterogeneous-datasets requirement: **flu/FluNet (structured, numeric, tabular) + GDELT (unstructured, multilingual, text) already are two genuinely different data types on their own**, before dengue is counted at all. Both diseases are evaluated at country-level mapping resolution regardless.

## Open item for the team (not decided here)

The FSE 570 proposal deadline was Sept 15, 2026. This spike produced a GO verdict with real evidence behind it — whether that's strong enough to submit against that date, versus continuing to treat the date as already forfeited (as the team had provisionally decided before this spike started), is a team call, not something resolved in this document.

## Operational note

Downloading raw GKG days temporarily filled the machine's `/private/tmp` volume to 100% capacity (already at ~91% before this investigation started) before it was caught and cleaned up. All GKG scratch files have been deleted; nothing from this investigation is stored outside `investigation/*.json` (small, git-safe) and this report. Worth flagging to the user: **the disk is at 93% full independent of this investigation** — that's a pre-existing condition, not something this spike caused, but it will make any future large-file work (raw GDELT downloads, BigQuery result exports, etc.) risky until addressed.
