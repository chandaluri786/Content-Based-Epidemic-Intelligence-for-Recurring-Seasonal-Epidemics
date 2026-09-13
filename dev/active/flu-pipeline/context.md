# Context: decisions that aren't obvious from the code

## Why flu over dengue

The original scoping picked dengue as primary because it has genuine subnational ground truth (InfoDengue, municipality-level). A feasibility check found GDELT's own location tagging never resolved below country level for Brazil dengue stories (0/28 sampled locations were subnational), even at the exact week of a known 2019 São Paulo outbreak peak — so dengue's subnational ground truth had no matching subnational *signal* in the informal source, and wasn't a mapping differentiator after all. Flu became primary because it directly extends Ganser et al.'s own experimental setup (the strongest literature anchor), has near-global FluNet coverage vs. dengue/PAHO's Americas-only reach, and content-depth was confirmed across all 8 stratified flu countries (88%/88%) vs. dengue's narrower testing. Dengue is now a secondary/paused track, not a co-equal build — running both as parallel full pipelines was more scope than the timeline supports.

## Why Brazil/Indonesia are flagged, not silently dropped

A 5-day extended feasibility sample found Brazil/Indonesia's GDELT flu content is genuinely thin: 33% retrievable/content-rich, vs. the project's own >=60%/>=50% bars and the 88%/88% aggregate across the other 6 countries. This isn't a single-day fluke — it's Ganser et al.'s documented income/media-density coverage bias, observed directly in our own data. Decision: keep Brazil/Indonesia in the Step 1 ground-truth table (their FluNet onset dates are computed and stored, `included_in_gdelt_cohort=False`), but exclude them from Step 2 ingestion and the Step 6 detection/lead-time test. The remaining 6 countries alone give ~51 country-season units, comfortably above the project's own >=40-unit cohort bar. This is a disclosed limitation to state explicitly in any final writeup, not a number to quietly drop.

## Why Japan uses a peak-count proxy

FluNet's Japan records have no `SPEC_PROCESSED_NB` (specimen-processed denominator) — confirmed empirically (every JPN row returns an empty string for that field), not inferred from docs. Without a denominator, the flat >=10%-positivity-for-2-weeks rule used for every other country can't be computed. Decision: for Japan only, treat the single week with the peak raw `INF_ALL` count as the onset week (`onset_method="peak_count_proxy"`, `data_quality_flag="proxy_lower_rigor"`). No better free data source was pursued given the project timeline. Every output row carries this flag so Japan's onset is never silently presented as equivalent rigor to the positivity-based countries.

## Why UK uses UKHSA, and why it's labeled "England," not "UK"

WHO FluNet has literally zero records for GBR in any year (confirmed live, not just in the original spike). UKHSA's own dashboard (`api.ukhsa-dashboard.data.gov.uk`, metric `influenza_testing_positivityByWeek`) provides the same test-positivity metric, but only for **England** — not Scotland, Wales, or Northern Ireland. The live endpoint also defaults to returning per-age-band breakdowns (`age=65-79`, `age=45-64`, etc.), not the aggregate — this wasn't obvious from the previously-saved spike JSON, which had already been filtered to `age=all`. `ground_truth/ukhsa_client.py` explicitly filters `age=all&sex=all&stratum=default` server-side; getting this wrong would have silently 5x-10x'd the apparent weekly volume. Every UKHSA-sourced row's geography is "England," and this is never equated with "UK" in output or reporting.

## Why the round-robin model pool exists

Originally assumed Groq's constraint was a 30 RPM cap (a guess, not verified). Live testing (2026-09-13) showed the real constraint is a **1,000 requests/day (RPD) cap**, confirmed via the `x-ratelimit-*` response headers (reset-time spacing of exactly 86.4s = 86400s/1000 per call is the signature of a daily rolling window, not a per-minute one). At USA 2023's pilot volume alone (6,179 matched articles, roughly half reaching the LLM after the prefilter), a single model would take 5-6 real days.

Further testing found the RPD cap is tracked **per model**, not account-wide (a burst of calls to one model didn't move another model's `remaining-requests` counter). Of the models in this account's catalog, only three support `response_format=json_schema` (the structured-output mode the schema validation depends on): `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b` — all capped at 1,000 RPD each. A fourth model, `allam-2-7b`, has a 7,000 RPD cap but flatly rejects `json_schema` responses (hard capability gap, not a quality tradeoff) — not usable. `extraction/multi_model_client.py` waterfalls across the three usable models.

**Per-model spot-check (done):** compared old-prompt vs. new-prompt extractions on the same 6 USA articles, spread across gpt-oss-120b and gpt-oss-20b (the pool naturally used both during testing; qwen3.8-27b wasn't hit in this particular sample). All 6 agreed on `relevant`; severity/strain showed only minor stochastic variance (e.g. "unspecified" vs "not_mentioned" -- same practical meaning). No model in the sample looked systematically weaker. One extraction failed transiently and succeeded on immediate retry with the same model/prompt -- ordinary API flakiness, not a quality issue.

## The real bottleneck is tokens/day (TPD), not requests/day (RPD) -- and it changes the full-build timeline materially

The 1,000 RPD cap above turned out not to be the binding constraint. Groq also enforces a **200,000 tokens/day (TPD) cap, per model**, confirmed by directly triggering it: `"Rate limit reached for model openai/gpt-oss-120b ... on tokens per day (TPD): Limit 200000, Used 199121, Requested 3372. Please try again in 17m56s."` -- a rolling window (like RPD), not a hard once-a-day reset. Our original prompt (6,000-char articles + 5 verbose few-shot examples, no `max_tokens` cap on the completion) used ~3,000-3,400 tokens/call, so **TPD, not RPD, is what a real run hits first**: 200,000 / 3,000 ≈ only ~65 calls/model/day -- not the ~1,000 RPD implied. This is why "all 3 pooled models exhausted their quota" happened after just 86 calls in one run, not the ~3,000 the RPD-only estimate predicted.

**Fix**: cut `MAX_ARTICLE_CHARS` 6000->1500 (news articles front-load key facts) and tightened the few-shot prompt (terser examples, compact JSON, shorter header) without dropping any of the 5 judgment categories; added an explicit `max_tokens=300` cap on completions (previously unbounded). Measured real result via the API's own `usage` field: **741 prompt tokens for a realistic 1,500-char article, vs. ~3,372 before -- a ~78% reduction.** New effective throughput: ~247 calls/model/day, ~741/day pooled across 3 models (vs. ~65/day and ~195/day pooled before).

**Full 6-country projection (done, flagged plainly as asked)**: using USA's own real measured match rate (6,179 matches / 85-day window = 72.7/day) as the primary anchor, the spike's per-country relative rates (UK/Japan/Australia) calibrated against that anchor, Kenya's real rate (8/85 days), and a flagged rough guess for India (no raw-mirror data point exists for it yet) --

| | Estimate |
|---|---|
| Total matched articles, full 6-country cohort (51 country-seasons) | ~74,000 |
| Estimated LLM calls needed (USA's own observed 69% reach-LLM rate) | ~51,000 |
| Time at the *old* prompt (~195 calls/day pooled) | ~263 days (~8.8 months) |
| Time at the *new shrunk* prompt (~741 calls/day pooled) | ~69 days (~2.3 months) |

Even after the ~3.8x token-efficiency fix, **a full 6-country run is ~2-3 months of continuous daily extraction on Groq's free tier** -- dominated by the USA alone (~75% of total volume). This is a volume-vs-free-tier-quota mismatch that further prompt engineering won't solve. **Explicit decision point for the team**: either accept a multi-month timeline, scope the full build down (e.g. fewer countries/seasons, or a stratified sample rather than every matched article), or move to a paid tier / different provider for the full run. Not resolved here -- flagged for a deliberate decision before committing to the full 6-country build. Pipeline work is **paused** pending this decision (see `tasks.md`).

### Option (b) cost estimate: Groq's paid Dev Tier

Groq's Dev Tier is pay-as-you-go with **no subscription fee and no minimum spend** -- it removes the free tier's RPD/TPD caps entirely, so on paid tier there's no need for the round-robin pool at all; a single model can handle the whole run. Pricing confirmed via web search against third-party aggregator sites summarizing Groq's public rates (Groq's own pricing page is JS-rendered and didn't return content via direct fetch -- **verify these exact rates in the Groq console before committing budget**, but they're internally consistent across multiple independent sources):

| Model | Input $/M tokens | Output $/M tokens |
|---|---|---|
| `openai/gpt-oss-120b` | $0.15 | $0.60 |
| `openai/gpt-oss-20b` | $0.075 | $0.30 |
| `qwen3-32b` (proxy for our `qwen/qwen3.8-27b`; source gave a blended, not split, rate) | $0.36 | $0.36 |

Using the real measured per-call token split (741 prompt + 68 completion tokens, from the same `usage`-field measurement above) across the ~51,249 estimated calls for the full 6-country run: **~38.0M prompt tokens + ~3.48M completion tokens total.**

| Model (single-model run, no pooling needed on paid tier) | Total cost, full 6-country run |
|---|---|
| `openai/gpt-oss-20b` (cheapest) | **~$3.89** |
| `openai/gpt-oss-120b` (higher quality, still our current default) | **~$7.79** |
| `qwen3-32b` proxy | ~$14.93 |

**This is a strikingly cheap option** -- under $8 for the entire full-scale extraction using our current default model, vs. ~2.3 months of wall-clock time on the free tier. Worth the team weighing seriously against options (a) and (c). Caveats: (1) pricing sourced from aggregators, not confirmed directly against Groq's own console; (2) assumes Dev Tier has no other binding rate limit that would slow a sustained high-volume run (not verified); (3) the ~51,249-call estimate carries the same uncertainty as the volume projection above (India's rate especially).

## Why avian/animal flu had to be explicitly excluded

Pilot testing found ~36% of USA's matched articles were about H5N1/avian flu (2023's major poultry outbreak) — agricultural/trade news, not human seasonal flu. The word-boundary regex correctly matches "avian-flu" as a `flu`-containing URL token (working as designed), but the LLM initially marked at least one such article `relevant=True`, since the original 4 few-shot examples never covered this distinction. Fixed by adding a 5th few-shot example (poultry outbreak, no human cases -> `relevant=False`) and an explicit system-prompt instruction that `relevant=True` requires reported human cases. Verified against the real previously-misclassified article after the fix (`relevant` flipped to `False`). This is exactly the kind of issue only a real pilot run surfaces — worth remembering as a reason to always validate content-quality assumptions against real data before scaling up.

## Why hourly-subsampling for Step 2 was rejected

The plan proposed a fallback: if full 96-files/day ingestion is too slow, try subsampling to 24 files/day (top-of-hour only) and adopt it if it retains >=90% of matched URLs found by the full method, on a few known days. Calibrated against 3 real days (USA 2023-12-11, GBR 2023-01-16, JPN 2023-11-27): recall was 31.7%, 0%, and 0% respectively — decisively failing the bar. News volume and specific flu stories cluster unevenly across a day's 96 windows; sparse-content countries (GBR, JPN) can miss every relevant article entirely under hourly sampling. Full 96-files/day ingestion is required; the tractability problem is solved via 8-way concurrency (measured ~2.9x speedup) and calendar-date-union deduplication across overlapping country-season windows, not via subsampling.
