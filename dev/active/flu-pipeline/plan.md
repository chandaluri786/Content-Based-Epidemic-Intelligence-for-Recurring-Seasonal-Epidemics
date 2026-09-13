# Flu Pipeline Build Plan

Source plan (full detail, module signatures, test surface): `~/.claude/plans/prompt-for-claude-magical-aurora.md`. This file tracks the condensed 8-step plan and where we are in it.

## The 8 steps

1. **Ground truth** — FluNet + UKHSA weekly series, 8 countries x 2015-2024, onset dates per country-season. `pipeline/ground_truth/`.
2. **GDELT ingestion** — bounded window per country-season (~10 weeks before onset to 2 weeks after), raw 15-min GKG mirror, in-memory only. `pipeline/gdelt/`.
3. **Content extraction** — LLM few-shot structured extraction (disease signal, severity, symptoms, strain, location, confidence). `pipeline/extraction/`.
4. **Relevance filtering** — rule-based prefilter before any LLM call; `relevant=True and confidence>=0.6` as the single relevance predicate, reused everywhere.
5. **Cross-document linking** — deterministic join by country x epi-week. `pipeline/join/`.
6. **The actual test** — content-signal vs frequency-baseline first-crossing date, lead time vs official onset. `pipeline/detection/`.
7. **Mapping** — country-level relative-intensity aggregation (lightweight). `pipeline/mapping/`.
8. **Evaluation** — lead-time distribution, retrievability/content-depth at full scale vs the spike's 88%/88%. `pipeline/evaluation/`.

## Current phase: pilot validation

All 8 steps are built and unit-tested (100% coverage on every module except CLI entry points). Before committing to the full 6-country/~30-hour/~1.5TB run, we're validating the whole pipeline end-to-end on a small real pilot: **USA 2023 + Kenya 2023** (2 country-seasons, 170 unique ingestion days, no calendar overlap).

Pilot progress:
- Step 1 (ground truth): done for all 8 countries, real data — `data/ground_truth/country_seasons.csv`. 51/60 onsets found in the 6-country GDELT cohort (comfortably clears the >=40 bar).
- Step 2 (ingestion): done for the pilot — 6,187 matched articles (6,179 USA, 8 Kenya), ~2.06 hours real runtime.
- Step 2a (hourly-subsampling calibration): done, **failed** the >=90% recall bar (0-32% recall on 3 known days) — confirmed the full 96-files/day method is required, not a subsampling shortcut.
- Step 3 (extraction): Kenya done (8/8). USA in progress (running with a shrunk, token-efficient prompt after discovering Groq's real bottleneck is 200K tokens/day/model, not the 1000 RPD first assumed) — see `tasks.md` for live status.
- Steps 5-8: not yet run on the pilot; blocked on Step 3 finishing.

**Important finding from the pilot** (see `context.md` for full detail): projecting USA's own real match rate across the full 6-country cohort, a full-scale Step 3 run needs an estimated ~51,000 LLM calls, which is **~69 days (~2.3 months) of continuous daily extraction even with the token-efficient prompt** on Groq's free tier. This is flagged as an open decision for the team below, not resolved here.

## After the pilot

1. Run Steps 5-8 on the pilot cohort (USA 2023 + KEN 2023) to get a first real lead-time number and sanity-check the whole shape.
2. **Team decision needed**: given the ~2.3-month free-tier timeline for full-scale Step 3, decide whether to (a) accept the multi-month timeline, (b) scope the full build down (fewer countries/seasons, or a stratified sample of matched articles rather than every one), or (c) move to a paid tier or different LLM provider for the full run. Not resolved in this build phase — a deliberate call, not something to back into.
3. Full-scale Step 2 ingestion (~30 hours, ~1.5TB transient transfer, zero persistent disk growth) — independent of the Step 3 decision above, and much less of a bottleneck.
4. Full-scale Step 3 extraction — timeline depends on the decision in (2).
5. Steps 5-8 on the full cohort, final evaluation report.
6. Write up limitations explicitly: Brazil/Indonesia excluded from GDELT cohort, Japan's peak-count proxy, UK=England-only, India's projected volume has no real data point behind it yet (see `context.md`).
7. Dengue secondary track (InfoDengue/PAHO) — not started, out of scope for the current build phase.
