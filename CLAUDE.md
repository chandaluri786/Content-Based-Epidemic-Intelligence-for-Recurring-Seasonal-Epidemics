# Flu Content-Aware Epidemic Intelligence

## What this is

A content-based outbreak-detection system for seasonal influenza. It extracts structured signal (case/severity/symptom mentions) from GDELT-indexed news articles and compares how early that **content signal** crosses a detection threshold against a **frequency-count baseline** (just counting flu-tagged articles per week, no LLM) and against the **official onset date** from WHO FluNet / UKHSA surveillance data.

This directly extends Ganser et al. (2022), who found frequency-count monitoring (HealthMap/EIOS) caught only 22 of 238 seasonal flu outbreaks within 2 weeks of WHO FluNet's own onset across 24 countries. The question this project tests: does content extraction beat frequency counting where that prior work showed frequency counting fails?

Dengue (via InfoDengue/PAHO) is a paused secondary track — not part of the active build. Don't touch dengue data sources or logic.

Full investigation/feasibility history: `investigation/report.md`, `investigation/report_followup2.md`, `investigation/updated_problem_statement.md`.

## Architecture (Steps 1-8)

```
pipeline/
  config.py         # every named constant: countries, thresholds, API URLs, model pool
  common/            # epiweek math, retry/backoff HTTP, disk guard, resumable JSONL I/O
  ground_truth/      # Step 1: FluNet + UKHSA onset detection -> country-season table
  gdelt/             # Step 2: raw GKG mirror ingestion, flu-term filtering, article fetch
  extraction/        # Step 3: LLM structured extraction (schema, prompt, relevance, client)
  join/              # Step 5: deterministic country x epi-week join
  detection/         # Step 6: content-signal vs frequency-baseline detection rule, lead time
  mapping/           # Step 7: country-level relative-intensity aggregation
  evaluation/        # Step 8: lead-time distribution + retrievability reporting
  cli/               # entry points: run_step{1,2,3}_*.py
tests/unit/          # mirrors pipeline/ structure, 100% coverage on all non-CLI modules
data/                # gitignored: ground_truth/, gdelt_matched/, gdelt_manifest/, extractions/
```

Build plan and detailed step-by-step design: `dev/active/flu-pipeline/plan.md`.
Current status and open work: `dev/active/flu-pipeline/tasks.md`.
Non-obvious decisions and why: `dev/active/flu-pipeline/context.md`.

## Key decisions that shape the code

- **Cohort**: 8 countries (USA, GBR, JPN, AUS, BRA, IND, KEN, IDN), 2015-2024. GBR uses UKHSA (FluNet has zero UK records). JPN uses a peak-count proxy (no specimen-processed denominator in FluNet). BRA/IDN are computed for ground-truth documentation only; excluded from GDELT ingestion and detection (confirmed thin content, see `context.md`).
- **GDELT ingestion is fully in-memory** — each 15-minute GKG zip is downloaded, parsed via `zipfile.ZipFile(io.BytesIO(...))`, and discarded (`del`) immediately. Nothing from the raw GDELT stream is ever written to disk; only matched-URL metadata (tiny) and a resumable manifest are persisted. Ingestion is 8-way concurrent (`ThreadPoolExecutor`).
- **LLM extraction uses Groq's free tier** through the OpenAI-compatible endpoint (`base_url=https://api.groq.com/openai/v1`, the already-installed `openai` SDK). Confirmed empirically (not assumed), and it took two rounds to find the real constraint: Groq enforces both a 1,000 requests/day (RPD) cap **and a separate, tighter 200,000 tokens/day (TPD) cap, each tracked per model**, not account-wide, with no meaningful RPM throttle. TPD binds first given this prompt's size. `extraction/multi_model_client.py` waterfalls across `openai/gpt-oss-120b -> openai/gpt-oss-20b -> qwen/qwen3.8-27b` (the three models in the account's catalog that support `response_format=json_schema`). A 429 (either cap) raises `DailyQuotaExceeded`, which the CLI catches to fall through to the next pooled model and, once all are exhausted, stop cleanly rather than retrying.
- **Prompt is deliberately terse**: `MAX_ARTICLE_CHARS=1500` (not 6000) and a tightened 5-example few-shot prompt, plus an explicit `max_tokens=300` completion cap — cut real measured tokens/call from ~3,372 to ~741 (~78%), since every token/call directly divides into the 200K TPD/model budget. Spot-checked against the original longer prompt on the same articles before adopting; no quality regression found. Even so, a full 6-country run is projected at ~2.3 months of continuous daily extraction on the free tier — see `dev/active/flu-pipeline/context.md` for the full projection and the open team decision it requires (accept the timeline / scope down / paid tier or different provider).
- **Extraction is resumable by URL**: `extraction/extraction_store.py` records one JSONL line per processed URL (status + result), so a run interrupted by the daily cap or anything else picks back up via `is_done(url)` without reprocessing or double-spending quota.
- **Relevance schema explicitly excludes animal/avian flu**: found via pilot testing that ~36% of USA's matched articles were H5N1/avian-flu content (agriculture/trade, not human cases), and the LLM initially misclassified some as `relevant=True`. Fixed via an explicit few-shot example and system-prompt instruction (`extraction/prompt.py`) — only human-case articles should be `relevant=True`.
- **Detection rule**: baseline mean/stdev from each country-season's first 4 weeks, first-crossing of `mean + 2*stdev` (floored at 3 articles) sustained 2 weeks — computed identically for the content signal (LLM-filtered, `relevant=True` + confidence >= 0.6) and the frequency baseline (raw regex-matched count, no LLM), so the two are directly comparable on the same ingested data.

## Environment

- `uv` for dependency management (`uv sync`, `uv run ...`).
- `.env` (gitignored) holds `GROQ_API_KEY`.
- `pytest -m unit --cov=pipeline --cov-report=term-missing` for the test suite.
