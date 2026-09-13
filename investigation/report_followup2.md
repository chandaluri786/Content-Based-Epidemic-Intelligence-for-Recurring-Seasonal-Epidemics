# Feasibility Spike #4 — Follow-up 2: Three Remaining Open Items

Spec: `/Users/aditya.rallapalli/.claude/plans/fse-570-capstone-starry-meadow.md`
This is additive to `report.md` / `updated_problem_statement.md` — flu's already-confirmed 8-country content-depth number (30/34, 88%/88%) is **not** revisited here.

## Item 1 — UK/FluNet gap: ECDC/TESSy (via UKHSA's own dashboard)

**Pre-registered criteria:** live public access, no special credentials; weekly granularity with a percent-positivity-comparable metric; historical depth overlapping FluNet's window.

**Result: PASS on all three.** ECDC/TESSy itself is not directly queryable without registration, but UKHSA's own open dashboard (`api.ukhsa-dashboard.data.gov.uk`) publishes the same underlying metric the UK reports into that system: `influenza_testing_positivityByWeek`, England-level, weekly, percent of PCR tests positive — the identical definition FluNet uses (positive specimens / specimens tested). No auth required. 479 weekly records fetched, spanning **2017-07-03 to 2026** (overlapping FluNet's 2015–2024 window from 2017 onward).

**Onsets computed using the identical rule** (≥10% positivity for 2 consecutive weeks):

| Year           | Onset found | Week | Positivity |
| -------------- | ----------- | ---- | ---------- |
| 2017           | Yes         | 51   | 19.9%      |
| 2018           | Yes         | 1    | 25.57%     |
| 2019           | Yes         | 1    | 19.22%     |
| 2020           | No          | —    | —          |
| 2021           | No          | —    | —          |
| 2022           | Yes         | 47   | 12.38%     |
| 2023           | Yes         | 51   | 11.45%     |
| 2024           | Yes         | 1    | 22.9%      |
| 2025           | Yes         | 1    | 14.5%      |
| 2026 (partial) | Yes         | 2    | 12.89%     |

**8/10 years with a defined onset** — a completely different picture from FluNet's 0/10 (which was a true reporting gap, not absent UK flu activity). The two "no onset" years, 2020–2021, line up with real COVID-era non-pharmaceutical interventions suppressing flu circulation globally — a sanity check that the metric and rule behave sensibly, not an artifact.

**Verdict: MERGE.** UK/UKHSA (England) replaces the empty UK/FluNet cell in the flu cohort, adding 8 onset-units. Revised flu cohort: **63/80** (7 other countries at 55/70 + UK/UKHSA at 8/10), comfortably clearing the ≥40 bar with more margin than before. Note for the build: UKHSA covers England specifically, not the full UK (Scotland/Wales/NI report separately) — close enough for a country-level cohort slot, but worth naming precisely rather than silently equating "England" with "UK" in the final writeup.

## Item 2 — Brazil/Indonesia: extended from 1 day to 5 stratified days

**Pre-registered sample:** 5 years spread evenly across 2015–2024 (2015, 2017, 2019, 2021, 2023), using each country's own real FluNet onset week for that year, resolved to a calendar date before running — not chosen after seeing results.

**Result:**

| Country   | Year | Matched URLs | Sampled | Retrievable | Content-rich |
| --------- | ---- | ------------ | ------- | ----------- | ------------ |
| Brazil    | 2015 | 2            | 2       | 0/2         | 0/2          |
| Brazil    | 2017 | 0            | 0       | —           | —            |
| Brazil    | 2019 | 0            | 0       | —           | —            |
| Brazil    | 2021 | 0            | 0       | —           | —            |
| Brazil    | 2023 | 1            | 1       | 1/1         | 1/1          |
| Indonesia | 2015 | 0\*          | 0       | —           | —            |
| Indonesia | 2017 | 0            | 0       | —           | —            |
| Indonesia | 2019 | 0            | 0       | —           | —            |
| Indonesia | 2021 | 0            | 0       | —           | —            |
| Indonesia | 2023 | 0            | 0       | —           | —            |

\*Indonesia's 2015 date (2015-01-05) predates GDELT GKG 2.0's launch (Feb 2015) — all 96 files failed to download because they don't exist yet, a genuine data-availability edge case, not a bug. The other 4 Indonesia days are valid GDELT windows and still returned zero.

**Combined: 3 articles sampled total, 1/3 retrievable (33%), 1/3 content-rich (33%).** The two Brazil-2015 matches are Oman/Chandigarh bird-flu-scare wire stories, not about Brazil's own flu activity at all (a geotagging artifact, similar to the earlier "Northern Territory flu vaccine" story mistagged to Brazil in the original pilot). The single genuine Brazil-2023 match is retrievable and content-rich (8 markers).

**Verdict: FAIL, and the extended sample confirmed rather than reversed the 1-day finding** — the opposite of what happened with dengue's resolution' check, where a small sample was misleading and a larger one flipped the conclusion. Here, 5 real stratified days across 9 years of Brazil/Indonesia flu-onset weeks produced essentially the same picture as the original single day: **genuinely thin-to-absent GDELT flu coverage for these two countries specifically**, not a sampling artifact.

**Consequence for the build:** the aggregate 8-country flu content-depth figure (30/34, 88%/88%, already confirmed and not being revisited) still stands, but it is carried almost entirely by the 6 higher-media-density countries (USA, UK, Japan, Australia, Kenya, India). Brazil and Indonesia specifically should not be assumed to work if included in a broader cohort — this is a real, evidenced instance of the exact income/media-density coverage variation Ganser et al. (2022) documented, not a hypothetical risk. Any full-build cohort selection should treat content-depth as something to check per-country, not assume uniform from the aggregate pass.

## Item 3 — Dengue onset threshold calibration

**Pre-registered alternative rule:** each of the 12 capitals' own 75th percentile of its complete 2015–2024 weekly incidence series, same "sustained 2+ consecutive weeks" structure, computed before looking at how it would move Belém/Curitiba specifically.

**Result — cohort barely moves in aggregate:** 75/120 (flat rule) → **78/120 (relative rule)**. Threshold choice is not the dominant lever on cohort size either way; both clear ≥40 by a wide margin. The more informative result is the per-city redistribution and what it reveals about baseline dengue intensity — city p75 values range from **2.82/100k (Curitiba) to 72.03/100k (Goiânia)**, a 25x spread, which itself says a single flat threshold applied uniformly across cities with such different baselines was never going to treat them equivalently.

**Belém — genuinely lower activity, not under-detection.** Flat rule: 2/10. Relative rule: 6/10, but at incidences of **3.2–5.13/100k** — well below both the flat threshold (10) and the cross-city median incidence at flat-rule onsets (13.13/100k). Belém's own top-quartile weeks are still low in absolute terms. This matches the pre-registered "genuinely lower activity" interpretation, not under-detection.

**Curitiba — mostly the same pattern, with one genuine threshold-edge artifact.** Flat rule: 2/10 (2016: 16.63/100k; 2024: 12.61/100k). Relative rule: 8/10, adding six low-incidence years (4.0–8.21/100k, consistent with "genuinely lower activity" like Belém) **plus one 2024 week at 9.99/100k** — just under the flat rule's 10.0 cutoff, for the same year the flat rule _did_ separately detect an onset at 12.61 later in the season. This is a real, if marginal, case of the flat rule's binary cutoff creating an edge-case miss (9.99 vs. 10.0 is a threshold-definition artifact, not a meaningful epidemiological difference), rather than a general under-detection problem for Curitiba.

**Verdict: threshold choice does not materially change the cohort go/no-go call (both clear ≥40), but it does matter for city-level validity.** Recommendation for the build: use each city's own relative baseline (e.g., the 75th-percentile rule tested here) rather than one shared absolute number, precisely because the 25x spread in city baselines means a flat rule will systematically read as "10/10 onsets, every year" for high-endemicity cities (Goiânia, Fortaleza) and "rare/no onset" for low-endemicity ones (Belém, Curitiba, Porto Alegre) regardless of what's actually happening locally — the same failure mode already seen with FluNet's flat rule on UK/Japan.

## Summary

| Item                            | Verdict                                                                                                                                                                                                               |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. UK/FluNet gap                | **Resolved** — UK/UKHSA merges in cleanly, 8/10 onsets, flu cohort now 63/80                                                                                                                                          |
| 2. Brazil/Indonesia flu content | **Confirmed thin/absent** on a 5-day extended sample — a real finding, not a 1-day artifact; doesn't change the aggregate 8-country pass but rules out assuming these two countries generalize                        |
| 3. Dengue threshold calibration | **Cohort size not threshold-sensitive** (75→78/120); Belém reflects genuine low activity, Curitiba shows one marginal edge-case artifact — city-relative thresholds recommended for the actual build over a flat rate |

None of these findings change the overall GO verdict or flu's primary/dengue-secondary scoping from `report.md`. They sharpen what the actual build needs to do differently: use a UK reference outside FluNet, do not assume content-depth is uniform across the flu cohort, and calibrate dengue onset detection per-city rather than with one shared threshold.
