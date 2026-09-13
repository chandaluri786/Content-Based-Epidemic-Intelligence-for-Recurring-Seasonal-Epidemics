# Updated Problem Statement & Data Plan (Reframe #4 — feasibility-tested, GO, flu-primary)

**See `investigation/report_followup2.md`** for three items resolved after this document was first drafted: the UK/FluNet gap (resolved — UK/UKHSA merges in, flu cohort now 63/80), a confirmed (not just single-day) finding that Brazil/Indonesia's flu content-depth is genuinely thin and shouldn't be assumed to generalize to other cohort countries, and a recommendation to use city-relative (not flat) dengue onset thresholds in the actual build.

## Problem Statement (updated)

Official disease surveillance systems typically register an outbreak after cases have been formally confirmed and reported, potentially introducing a delay in recognizing an emerging outbreak. Existing event-based surveillance approaches that rely primarily on report frequency can also produce unreliable outbreak signals — Ganser et al. (2022) found HealthMap/EIOS detected only 22 of 238 seasonal influenza outbreaks within a 2-week window against WHO FluNet, despite report-frequency monitoring across 24 countries for 7 years.

This project develops and evaluates a **content-based epidemic intelligence system** for **recurring seasonal epidemics**, using **influenza via WHO FluNet as the primary structured reference**, replacing our earlier focus on rare emerging events (WHO Disease Outbreak News), which structurally lacks enough discrete multi-report events to build a usable evaluation cohort (confirmed across three prior feasibility attempts). The system extracts structured information from unstructured reports (GDELT-indexed news) — disease, case/severity signals, symptoms, and location — aggregates it across reports, and compares its content-based signal against FluNet's own defined season onset to measure detection lead time, directly testing whether **content extraction beats frequency counting** where Ganser et al. showed frequency counting fails. This is a direct extension of Ganser et al.'s exact experimental setup (FluNet + informal-source monitoring, 24 countries), now testing content extraction instead of frequency counting where they showed frequency counting fails.

**Dengue (via PAHO PLISA / Brazil's InfoDengue) is kept as a secondary validation case**, not a co-equal build — see Scope Change below for why, and Secondary Track for what "secondary" means concretely.

Three connected questions, unchanged from the original design:
- **What is happening?** Extract disease, case/severity signals, symptoms, and confidence from reports.
- **Where is it happening?** Aggregate locations across reports into a **country-level relative-intensity map** (revised from municipality/state-level boundary mapping — see Scope Change below).
- **When can we detect it?** Compare the system's first meaningful signal against FluNet's own defined season onset to measure lead time.

## Scope Change #1 (disclosed, evidence-based): dengue is not a mapping differentiator

The original scoping decision picked dengue over flu as primary specifically because dengue has genuine subnational ground truth (InfoDengue, municipality-level). A 5-day, multi-state, multi-tier feasibility check of GDELT's own structured location tagging found **zero subnational (state/city) geotags among 28 Brazil-dengue-tied location entries checked — all resolved at country level**, including on the exact week São Paulo's 2019 outbreak peaked. Dengue's subnational ground truth does not have a matching subnational signal in the informal source, so it is not a mapping differentiator over flu after all. **Stage 8 (Affected-Region Mapping) is revised to target country-level relative-intensity choropleth mapping**, not municipality/state-level boundary expansion, for whichever disease is used.

## Scope Change #2 (disclosed): flu is primary, dengue is secondary — not a parallel co-equal build

The earlier draft of this document recommended running flu and dengue as parallel, co-equal pipelines, partly justified by "this satisfies the ≥2-heterogeneous-datasets course requirement." That justification doesn't hold: **FluNet (structured, numeric, tabular) + GDELT (unstructured, multilingual, text) already are two genuinely different data types on their own** — dengue isn't needed to clear that bar. Given the timeline (the team has already spent 3+ weeks and four attempts on this problem domain), building two full disease-specific extraction-and-evaluation pipelines is more scope than is supportable. **Flu/FluNet becomes the primary and only full build**; dengue/InfoDengue becomes a secondary validation case (see below), not a second pipeline.

Flu was chosen as primary over dengue once the mapping differentiator was gone, because: (a) it directly extends Ganser et al.'s own setup — the strongest literature anchor available; (b) its cohort is far broader (FluNet has near-global country coverage vs. dengue/PAHO's Americas-only reach); (c) content-depth is now confirmed across all 8 stratified countries tested (88% retrievable, 88% content-rich combined), not just the 2 originally tested.

## Data Plan

| Source | Role | Access confirmed |
|---|---|---|
| **WHO FluNet** (`xmart-api-public.who.int/FLUMART/VIW_FNT`) | **Primary structured reference**, influenza, country-week, includes strain subtype breakdown (H1N1, H3N2, B/Victoria, B/Yamagata) | Live, no auth, server-side filterable |
| **GDELT GKG 2.0 / DOC 2.0 API** | **Primary informal/unstructured input**, global news, 2015–present | Confirmed live via free DOC API and the raw 15-minute file mirror — **BigQuery not required** for this scale of investigation; revisit if the full build needs indexed querying across the full historical window |
| **PAHO PLISA / Delphi Epidata `paho_dengue`** | Secondary/validation reference, dengue, country-week, Americas, includes serotype breakdown | Live, no auth |
| **InfoDengue** (`info.dengue.mat.br/api/alertcity`) | Secondary/validation reference, dengue, municipality-week, Brazil, includes its own alert-level system | Live, no auth |

**Primary cohort (flu):** **63 country-season units** with defined onsets from 8 stratified countries (income tier × hemisphere) — comfortably clears a ≥40-unit go/no-go bar using a fraction of FluNet's near-global country coverage. (Updated from 55: the UK/FluNet gap is resolved — see below.) Content-depth confirmed across all 8: 30/34 sampled articles retrievable (88%), 30/34 content-rich (88%), both clearing the ≥60%/≥50% thresholds. Two per-country items, both now resolved with fuller evidence in `report_followup2.md` rather than left as single-day caveats:
- **UK has no WHO FluNet data at all** — resolved by using UKHSA's own open dashboard (England-level weekly test-positivity, the same metric FluNet uses), which found 8/10 onset years. UK/UKHSA is now merged into the cohort above.
- **Brazil/Indonesia showed almost no genuine flu content** — a 5-stratified-day extension (not just the original 1 day) **confirmed** this rather than reversing it (combined 1/3 articles retrievable/content-rich, 33%/33%, vs. the ≥60%/≥50% thresholds). This is a real, evidenced instance of Ganser et al.'s documented income/media-density coverage bias, not a sampling fluke — the full build's country selection should check content-depth per-country rather than assume the aggregate 88%/88% figure generalizes.

**Secondary track (dengue):** 75 city-season units from just 12 Brazilian capitals under the original flat onset rule (78 under a city-relative alternative tested in `report_followup2.md` — cohort size is not sensitive to this choice either way). Confirmed content-rich at the national level. Scope this as a smaller supplementary analysis — e.g., "does the same content-extraction approach generalize to a second disease/region, evaluated at country level" — sized to fit around the flu build, not as a second full pipeline with its own complete stage-by-stage extraction and evaluation. If built, use a **city-relative onset threshold** (each city's own 75th percentile), not the flat rate tested in the original spike — the flat rule reads as low-activity for genuinely low-endemicity cities (Belém, Curitiba, Porto Alegre) and maxed-out for high-endemicity ones (Goiânia, Fortaleza) regardless of what's actually happening locally.

## Open items before build start

1. Tune the onset-detection threshold per country (UK and Japan returned zero onsets under the flat 10%-positivity rule used in this spike — likely needs per-country calibration, not a structural blocker).
2. Resolve the UK/FluNet gap — either find a UK-specific reference (ECDC/TESSy) or drop the UK from the flu cohort.
3. Confirm GDELT full-text retrievability and content-depth at full scale (this spike sampled single digits to low tens of articles per cell/country; the full build should run a properly-sized stratified sample, ideally via BigQuery once a dedicated project/billing decision is made).
4. **Not decided here — team call:** the FSE 570 proposal deadline was Sept 15, 2026. This spike now has a GO verdict with real evidence behind it. Whether that's strong enough to submit against that date, or whether to continue treating the date as already forfeited (the team's provisional stance going into this spike), needs a team decision, not something this document resolves.
