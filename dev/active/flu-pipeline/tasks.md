# Tasks

Mirrors the session's live task list. Update whenever that list changes materially.

## Done

- [x] `common/` module (epiweek, sustained_crossing, http, disk_guard, io_jsonl) — 100% coverage.
- [x] `ground_truth/` module (FluNet client, UKHSA client, onset detection, builder) — 100% coverage, validated against live APIs for all 8 countries x 2015-2024. Output: `data/ground_truth/country_seasons.csv`. Real onset counts for the 6-country GDELT cohort: USA 9, GBR 6, JPN 10, AUS 8, IND 10, KEN 8 (51 total).
- [x] `extraction/` module (schema, prompt, relevance prefilter, Groq client) — 100% coverage, validated against live Groq API.
- [x] `detection/`, `join/`, `mapping/`, `evaluation/` modules — 100% coverage against synthetic fixtures.
- [x] `gdelt/` module (window builder, manifest, raw downloader, gkg parser, flu filter, article fetcher) — validated against live GDELT (gkg_parser: 1142/1142 real lines parsed; FIPS country codes confirmed empirically: UK/JA/AS/KE/IN/US; a full real day reproduced the spike's known match count).
- [x] Step 2a hourly-subsampling calibration — ran, failed decisively (0-32% recall vs >=90% bar). Full 96-files/day method confirmed required.
- [x] Step 2 pilot ingestion — USA 2023 + KEN 2023, 170 unique days, 6,187 matched articles (6,179 USA, 8 KEN), ~2.06 hours.
- [x] Step 3 extraction for Kenya — 8/8 done (4 extracted, 2 skipped_prefilter, 2 not_retrievable).
- [x] Fixed avian/animal-flu misclassification in the extraction prompt (see `context.md`).
- [x] Corrected Groq rate-limit model (round 1): 1,000 RPD per model, confirmed per-model not account-wide, built `MultiModelExtractionClient` round-robin across gpt-oss-120b/gpt-oss-20b/qwen3.8-27b.
- [x] Corrected Groq rate-limit model (round 2, the real bottleneck): discovered a second, tighter per-model cap -- 200,000 tokens/day (TPD), hit before RPD given our prompt size. Shrunk `MAX_ARTICLE_CHARS` 6000->1500, tightened the few-shot prompt, added `max_tokens=300`. Measured ~78% token reduction (3372->741 tokens/call) via the API's own `usage` field.
- [x] Per-model quality spot-check (gpt-oss-120b vs gpt-oss-20b, on the same 6 USA articles, old vs new prompt) — no model looked systematically weaker; `relevant` agreed 6/6; minor severity/strain variance only. See `context.md`.
- [x] Full 6-country token/volume projection, flagged plainly: even with the shrunk prompt, a full 6-country run is **~69 days (~2.3 months)** of continuous daily extraction on the free tier (~51,000 estimated LLM calls at ~741/day pooled) -- was ~263 days before the fix. **Open decision for the team**: accept the timeline, scope down, or move to a paid tier/different provider. See `context.md`.
- [x] Dev docs set up: this file, `plan.md`, `context.md`, and root `CLAUDE.md`.

## Paused -- checkpointed cleanly, ready to resume

- [x] Step 3 extraction for USA -- stopped cleanly (not killed mid-write) at **218 of 6,179 matched articles processed** (143 extracted, 67 not_retrievable, 2 skipped_prefilter, 6 failed; 149 total LLM calls across the pool: 43 gpt-oss-120b, 58 gpt-oss-20b, 1 qwen3.8-27b, plus ~47 earlier calls made before per-model tracking existed). Checkpoint verified valid: `data/extractions/USA.jsonl` (218 lines, 0 malformed, loads cleanly via `ExtractionStore`), `data/gdelt_manifest/manifest.jsonl` (16,320 lines, 0 malformed), `data/gdelt_matched/{USA,KEN}.jsonl` untouched (6,179 + 8). Resume anytime with `python -m pipeline.cli.run_step3_extract --country USA` -- no flags needed, it skips everything already done. Whatever infra the team decision below lands on, this checkpoint is valid to continue from as-is.

## BLOCKING: team decision needed before further pipeline work

- [ ] **Free-tier TPD caps make the full 6-country Step 3 run ~2.3 months even with the token-shrunk prompt (~51,000 estimated LLM calls at ~741/day pooled across 3 models).** Work is paused pending a decision among:
  - **(a) Local GPU inference** via Ollama / a quantized open model, matching Health Sentinel (Pant et al. 2025)'s own approach -- no API rate limits at all, but needs local GPU capacity and a new `ExtractionClient` implementation.
  - **(b) Groq's paid Dev Tier** -- pay-as-you-go, no subscription/minimum spend, removes the RPD/TPD caps entirely. **Cost estimate computed and ready** (see `context.md`): **~$3.89 (gpt-oss-20b) to ~$7.79 (gpt-oss-120b, current default) for the entire full 6-country run** — strikingly cheap, though pricing was sourced from third-party aggregators (Groq's own pricing page is JS-rendered and didn't return content via direct fetch) and should be confirmed in the Groq console before committing budget.
  - **(c) Tighter upstream relevance prefiltering** to cut LLM call volume before it ever reaches the model -- reduces cost/time on any tier, but trades off recall (some genuinely relevant articles would be filtered out before the LLM ever sees them); needs the tradeoff quantified before adopting.
  - This is not resolved here -- it's the team's call. Pilot-scale work (Steps 5-8 on USA 2023 + KEN 2023, using what's already extracted) can proceed independently of this decision if useful; full-scale work should not resume until it's made.

## Open (blocked on the decision above, or on pilot Steps 5-8)

- [ ] Step 5 join (USA 2023 + KEN 2023 pilot) -- can run now on the 218 USA + 8 KEN records already extracted, doesn't need the full USA backlog.
- [ ] Step 6 detection/lead-time (pilot) — the actual first real lead-time number for this project.
- [ ] Step 7 mapping (pilot, trivial for 2 countries).
- [ ] Step 8 evaluation (pilot) — lead-time distribution + retrievability vs the spike's 88%/88%.
- [ ] Full-scale Step 2 ingestion (~30 hrs, ~1.5TB transient transfer, ~0 disk growth) — independent of the Step 3 decision, needs its own explicit go-ahead given the scale.
- [ ] Full-scale Step 3 extraction — blocked on the team decision above.
- [ ] Full-scale Steps 5-8, final evaluation report with limitations section.
- [ ] Dengue secondary track — not started, paused.
