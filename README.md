# GDELT Flu-Article Extraction Pipeline

Pulls GDELT news-article metadata for a cohort of countries, filters it down
to articles plausibly about human seasonal/pandemic influenza, fetches and
cleans the real article text, and stores the result for downstream human
labeling. Built to replace an earlier pipeline whose URL-keyword-only
filter was found to miss the large majority of real candidates and whose
quality checks were unreliable on bot-blocked or boilerplate-heavy pages.

This README explains how to run it, how to configure it, what each stage
does and why it's built the way it is, and what's deliberately left for a
later phase.

---

## 1. Quick start

```bash
pip install -r requirements.txt

# Smoke test first: skip Stage 1/2 (no FluNet call) and run Stages 3-10
# against exactly one GDELT file (one 15-minute timestamp):
python run_pipeline.py --test-timestamp 20230115121500 --countries USA IND

# Local filesystem storage (default, zero config):
python run_pipeline.py --countries USA AUS IND --start-year 2020 --end-year 2023

# Run the unit tests (no network required):
pytest
```

Output lands in `./output/extracted_articles/{year}/matched_articles.jsonl`
by default -- one JSON object per line, one file per calendar year (bucketed
by each article's own GKG scan year). Every stored article mentions at
least one of the requested cohort countries (Stage 5's location filter) and
carries its full, unfiltered `locations` list (not narrowed to just the
matched country -- see section 7). See "Configuration" below to point this
at Google Drive instead, or to change which countries/years run.

Every real run (not `--test-timestamp`) also prints, and saves to
`./output/run_summary.json`, a per-(country, season-year)-window count of
how many articles were stored -- see section 7, "Run summary report."

This pipeline makes real, live network calls (WHO's FluNet API and GDELT's
public file mirror) -- there is no offline/mock mode. A full run across all
six configured countries and the full 2015-2024 study window is a
multi-hour job (GDELT publishes 96 files/day per calendar day needed); see
"Performance expectations" below before running it unscoped. Use
`--test-timestamp` first to confirm everything works before committing to
a real run.

---

## 2. Configuration

Everything that controls behavior lives in `config.py`. The settings most
likely to need changing:

| Setting | Default | What it controls |
|---|---|---|
| `TARGET_COUNTRIES` | USA, AUS, BRA, IND, KEN, IDN | The cohort. Maps ISO3 to GDELT's FIPS 10-4 location code (these differ — confirm a new country's real FIPS code against live data before adding it, don't assume). |
| `STUDY_YEARS` | 2015-2024 | Earliest/latest season years ground truth is pulled for. |
| `WEEKS_BEFORE_ONSET` / `WEEKS_AFTER_ONSET` | 10 / 2 | How wide each country-season's ingestion window is around its FluNet onset date. |
| `FLU_INCLUDE_THEMES` | see file | The exhaustively-verified theme list that drives half of candidate matching (Stage 5's theme condition — presence of any of these themes is sufficient). Don't edit without re-reading section 4's derivation. |
| `FLU_EXCLUDE_THEMES` | see file | Exhaustively-verified, but **not currently used** by Stage 5's gate (`has_theme_match()` no longer checks it — explicit decision). Kept for reference and possible future reinstatement; see Stage 5 below. |
| `MIN_FLU_THEME_HITS_ALONE`, `COOCCURRENCE_PROXIMITY_CHARS` | 2, 1000 | Content-richness thresholds (Stage 9). |
| `STORAGE_BACKEND` | `"local"` | `"local"` or `"gdrive"` — see below. |
| `RUN_SUMMARY_PATH` | `./output/run_summary.json` | Where the end-of-run per-window count report is written — see section 7, "Run summary report." Always local, regardless of `STORAGE_BACKEND`. |
| `COMPLETED_DAYS_PATH` | `./output/completed_days.json` | The cross-run day checkpoint — see section 4, Stage 3 "Cross-run day checkpoint." Always local, regardless of `STORAGE_BACKEND`. Delete this file to force every day to be reprocessed on the next run. |

### Environment variables (storage)

Decided: Google Drive, not an AWS/cloud-provider bucket. Local filesystem
storage is the zero-config default.

| Variable | Required for | Default |
|---|---|---|
| `PIPELINE_STORAGE_BACKEND` | — | `local` |
| `PIPELINE_LOCAL_STORAGE_DIR` | local backend | `./output/extracted_articles` |
| `PIPELINE_GDRIVE_FOLDER_ID` | gdrive backend | *(none — must be set)* |
| `PIPELINE_GDRIVE_CREDENTIALS_PATH` | gdrive backend | `./credentials.json` |
| `PIPELINE_GDRIVE_TOKEN_PATH` | gdrive backend | `./token.json` |

**One-time Google Drive setup** (do this once, before the first `gdrive`
run):
1. In [Google Cloud Console](https://console.cloud.google.com/), create a
   project (or reuse one), then enable the **Google Drive API** for it
   (APIs & Services → Enable APIs and Services → search "Google Drive API").
2. Go to APIs & Services → Credentials → Create Credentials → OAuth client
   ID → Application type **Desktop app**. Download the resulting JSON and
   save it as `credentials.json` in the directory you'll run the pipeline
   from (or point `PIPELINE_GDRIVE_CREDENTIALS_PATH` at it).
3. Go to APIs & Services → OAuth consent screen, set it to **Testing**, and
   add your own Google account under "Test users" (required while the app
   is unverified — fine for personal/project use, no Google review needed).
4. In Google Drive, create (or pick) a destination folder, open it, and
   copy the ID out of its URL: `https://drive.google.com/drive/folders/<ID>`.
5. First run with `PIPELINE_STORAGE_BACKEND=gdrive` opens a browser window
   asking you to log in and grant access to "see, edit, create, and delete
   only the specific Google Drive files you use with this app" (the
   `drive.file` scope — it cannot see your other Drive files). After you
   approve, the token is cached to `token.json` and later runs won't
   prompt again (until the token is revoked or deleted).

Example Google Drive run:
```bash
export PIPELINE_STORAGE_BACKEND=gdrive
export PIPELINE_GDRIVE_FOLDER_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz
python run_pipeline.py --countries USA --start-year 2020 --end-year 2023
```

### CLI flags

```
--countries   One or more of USA AUS BRA IND KEN IDN (default: all)
              Drives BOTH the ingestion windows (Stage 2) and the location
              filter (Stage 5) -- `--countries USA` means only US onsets
              build windows, AND only articles mentioning the US pass the
              location condition. The two aren't independently scopable.
--start-year  Earliest season year to pull ground truth for, inclusive
              (default: earliest STUDY_YEARS)
--end-year    Latest season year to pull ground truth for, inclusive
              (default: latest STUDY_YEARS). Must be >= --start-year.
--test-timestamp YYYYMMDDHHMMSS
              Smoke-test mode. Skips Stage 1/2 entirely (no FluNet call,
              no real season window) and runs Stages 3-10 against exactly
              one GDELT file, e.g. 20230115121500. Ignores
              --start-year/--end-year. Prints/saves a report the same way
              a real run does, but against a single synthetic one-day
              window (country "TEST") instead of a real season window --
              see section 7, "Run summary report."
```

---

## 3. Project layout

```
config.py                   # every tunable constant, in one place
models.py                   # shared dataclasses passed between stages
run_pipeline.py             # CLI entry point, orchestrates all 10 stages
pipeline/
  ground_truth.py           # Stage 1 -- WHO FluNet onset dates
  windows.py                # Stage 2 -- ingestion windows + day union
  gkg_downloader.py         # Stage 3 -- raw GDELT file download
  gkg_parser.py             # Stage 4 -- raw line -> structured record
  theme_matcher.py          # Stage 5 -- candidate matching (theme AND location, the only content filter)
  article_fetcher.py        # Stage 6 -- HTTP fetch
  content_extractor.py      # Stage 7 -- trafilatura cleaning
  quality_gates.py          # Stages 8-9 -- retrievability + content-richness
  storage.py                # Stage 10 -- persistence
tests/
  test_parsing.py           # unit tests for Stages 4-5 (no network needed)
```

---

## 4. Pipeline stages, and the decisions behind each

### Stage 1 — Ground truth (`pipeline/ground_truth.py`)
Pulls weekly influenza test-positivity data from WHO FluNet for each
country. Onset = the first week of a sustained `ONSET_SUSTAIN_WEEKS`-week
run where positivity (`INF_ALL / SPEC_PROCESSED_NB`) is `>= ONSET_POSITIVITY_THRESHOLD_PCT`.
This rule and its thresholds were inherited unchanged from the project's
original design — they're a reasonable a priori choice, not independently
re-derived here.

### Stage 2 — Windows (`pipeline/windows.py`)
Each country-season gets an ingestion window of `onset − 10 weeks` to
`onset + 2 weeks`. All windows across the whole cohort are unioned into one
set of unique calendar days, so a day needed by two countries isn't
downloaded twice.

### Stage 3 — Raw download (`pipeline/gkg_downloader.py`)
GDELT publishes a new file every 15 minutes (96/day) at a fixed,
predictable URL — no search endpoint, no auth. This stage downloads
everything for each needed day; all filtering happens later.

**Cross-run day checkpoint.** Before downloading, `run_pipeline.py` checks
`COMPLETED_DAYS_PATH` (default `./output/completed_days.json`) — a record
of which calendar days were already fully processed, and for which
countries, in a previous run. A day is skipped only if *every* country the
current run is asking for was already checked for that day
(`_day_needs_processing`); asking for an additional country later forces
that day to be reprocessed rather than silently skipped, since the
checkpoint is a lower bound on what's been checked, never an upper bound on
what could be found there. Progress is saved after each day, not just at
the end, so an interrupted run doesn't lose what it already finished. This
exists because country-season windows overlap in calendar time by design
(see section 6), so separate runs frequently need the same day more than
once — without this, that day's 96 files would be redownloaded and
re-filtered every time.

### Stage 4 — Parse (`pipeline/gkg_parser.py`)
**The key structural change from the original pipeline.** Each raw line has
27 tab-separated fields; the original pipeline read only the URL and a flat
*set* of location country codes, discarding the Themes field entirely and
discarding every location sub-field except the country code. This version
also keeps:
- **Themes_V2**, as `(theme_name, character_offset)` pairs
- **Locations_V2**'s full 9-field structure, including each location
  mention's own character offset

Those offsets are what make Stages 5 and 9 possible at all — without them,
there's no way to tell "two flu mentions close together" from "one flu
mention and one unrelated mention 4,000 characters apart."

### Stage 5 — Candidate matching (`pipeline/theme_matcher.py`)
Two independent conditions, **both** required (`is_flu_candidate`):

**Condition 1, theme match.** Theme-based, not URL-keyword-based. The
original pipeline required `"flu"`/`"influenza"` to appear literally in the
article's URL — this only works for English-language URLs and was measured
(in this project's own exploration, not asserted) to miss roughly 90%+ of
genuinely flu-themed articles in a real sample. GDELT's theme tags are
computed from the article's actual (translated, where non-English) content,
so matching on theme presence instead removes that language dependency
entirely. A record passes this condition if it carries at least one theme
from `FLU_INCLUDE_THEMES` — presence of an include-listed theme is
sufficient on its own; **absence of an exclude-listed theme is not
checked and is not required.** `FLU_EXCLUDE_THEMES` (bird/avian/canine/
equine/feline flu) and the `has_excluded_theme()` function that checks it
both still exist in `config.py`/`theme_matcher.py` — exhaustively verified
and kept available — but `has_theme_match()` no longer calls
`has_excluded_theme()`. Explicit, known consequence: a record tagged with
both a human-flu theme and an animal-flu theme (e.g. `TAX_DISEASE_FLU` +
`TAX_DISEASE_AVIAN_INFLUENZA` on the same article) now passes this
condition, where an earlier version of this gate would have rejected it —
this matters because the original pipeline's own pilot found roughly 36%
of its early matches were avian/poultry stories carrying both kinds of
tag. Both lists were derived by **exhaustively reading all 8,528
`TAX_DISEASE_*` theme codes** in GDELT's published taxonomy (see section
5, source list), not by guessing likely substrings — see the inline
comments in `config.py` for what was deliberately left out and why (e.g.
"stomach flu" is gastroenteritis, not influenza; *Haemophilus influenzae*
is a bacterium historically misnamed, not the influenza virus). If the
exclude check ever needs to be reinstated, re-wire `has_excluded_theme()`
back into `has_theme_match()` in `pipeline/theme_matcher.py`.

**Condition 2, location match.** A flat presence check — does at least one
of the requested cohort countries' FIPS codes appear anywhere in the
record's locations (`countries_mentioned`, `has_location_match`). This
condition went through its own history before settling here:

1. *Country bucketing* (first version) — tagged an article with a cohort
   country only if that country's own season window also covered the
   article's publish date, on top of the flat presence check.
2. *Country tagging* (second version) — dropped the window-coverage
   condition, kept the flat check, and tagged every matched article with
   *every* cohort country its locations touched, as a stored field.
3. *Removed entirely* (third version) — even the flat tagging step was cut.
   Reasoning: a presence-only check can't tell "this article is genuinely
   about India's flu season" from "this article is about the US, with
   India mentioned once in passing" (confirmed as a real pattern on live
   GDELT data, e.g. the Kenya wire-story and Australia "predicts our flu
   season" cases) -- so neither version 1's extra window condition nor
   version 2's plain tag was trustworthy as an *attribution* of the
   article to a country. The pipeline briefly had no location awareness at
   all as a result.
4. *Restored as a simple gate, not attribution* (current version) — going
   fully without a location check turned out to be the wrong trade: every
   flu-themed article worldwide was being kept, cohort country or not.
   What's implemented now is deliberately narrower in scope than either
   bucketing or tagging ever were: it answers only "is at least one cohort
   country mentioned at all," a yes/no gate, and makes **no claim** about
   which country (or whether the mention is even relevant to the flu
   content). The full `locations` list -- every place found, not just the
   one that satisfied this condition -- is still carried through to
   storage unfiltered, so a human labeler has everything needed to make
   the attribution judgment this stage deliberately doesn't attempt.

### Stage 6 — Fetch (`pipeline/article_fetcher.py`)
Plain HTTP GET, retried with backoff. No headless browser. Two real failure
modes exist (bot-blocking services like Incapsula, and JS-rendered content
missing from the static HTML) but this project did not measure what
fraction of failures each one causes before deciding whether browser
automation is worth its added complexity and cost — see section 6.

### Stage 7 — Clean (`pipeline/content_extractor.py`)
Runs the raw HTML through **trafilatura** to isolate the real article body
from navigation, ads, and comment forms. See section 5 for why this
library specifically.

### Stage 8 — Retrievability (`pipeline/quality_gates.py::is_retrievable`)
Defined as "trafilatura found real extractable text," not "the HTTP request
returned 200" and not "the raw HTML is longer than N characters" — both of
those were tried in this project's exploration and found unreliable (a
212-byte bot-block stub page nearly cleared a 200-character raw-length
floor; a real `requests.get()` against a bot-protected URL returned HTTP
200 with zero actual article content).

### Stage 9 — Content-richness (`pipeline/quality_gates.py::is_content_rich`)
A rule-based proxy, not true relevance verification — see the "Known
limitations" note below, which this function's own docstring also carries.
≥2 independent flu-theme hits on a record counts as rich on its own; a lone
hit only counts if a generic health theme (`GENERAL_HEALTH`, `MEDICAL`,
etc.) occurs within `COOCCURRENCE_PROXIMITY_CHARS` of it, corroborating
that it isn't an isolated coincidental mention. This rule exists
specifically because of a real, found case: an article about Chinese COVID
policy got a single `TAX_DISEASE_INFLUENZA` hit purely because it named the
organization "Global Initiative on Sharing Avian Influenza Data."

### Stage 10 — Storage (`pipeline/storage.py`)
Only ever called for articles that passed **both** Stage 8 and Stage 9.
One record per article, trimmed to five fields plus an ID — see section 7
for the exact schema. Both backends bucket output by calendar year (the
article's own GKG scan year — see section 7) so a consumer can retrieve
just the year(s) it wants. Pluggable backend — see section 2's
configuration table and section 6's note on the storage decision.

**Duplicate-storage prevention, keyed on `gkg_record_id`.** At the start of
a run, `storage.already_stored_ids()` loads every `gkg_record_id` already
persisted by a previous run; `fetch_clean_and_store` skips any candidate
whose `record_id` is already in that set, before fetching it. `gkg_record_id`
(GDELT's own field, format `{15-minute-file-timestamp}-{sequential-line-
number}`) was chosen over the article URL because it's **deterministic**:
parsing the same raw GDELT file + line always produces the same ID, every
time — confirmed empirically (747/747 distinct IDs within one real file,
zero recurrence of the same URL with a different ID across a 20-file,
12,100-record sample spanning two separate days).

This is a *different* safety net from the Stage 3 day-checkpoint above, not
a redundant one — the checkpoint avoids wasted recompute, this guarantees
no duplicate storage regardless of *why* a day gets reprocessed. Concrete
cases where a day is reprocessed even with the checkpoint in place, and
this dedup is what actually prevents the duplicate:
- **A later run asks for an additional country.** The checkpoint forces
  reprocessing (correctly — the new country was never checked), which
  would re-fetch and re-store the country that *was* already checked,
  without this.
- **A crash or interruption mid-day.** Articles are written as they're
  found, but a day is only marked complete in the checkpoint after its
  whole loop finishes — a restart reprocesses that day from scratch.
- **The checkpoint file is lost but the stored output isn't** (deleted/
  reset `completed_days.json` pointed at existing output) — every day
  looks unchecked, so everything would be reprocessed and, without this,
  re-stored.

### Deliberately not in this pipeline
Two things from the original design are **not** implemented here: geo-tag
cross-checking (comparing GDELT's location tag against an LLM's independent
read of the article) and human-case relevance filtering (excluding
animal-only disease reports at the sentence level). Both are the same
shape of problem Stage 5's location condition deliberately stops short of:
deciding what an article's text actually *means*, which a rule built on
theme/location presence can't reliably do. GDELT's full location list is
carried through to storage (`locations`, see section 7) as raw data, not
an authoritative claim about relevance — human labelers are expected to
make that judgment, the same role the original pipeline's LLM-based
cross-check was meant to play.

---

## 5. Key building blocks, and the sources behind them

**GDELT GKG 2.1 (Global Knowledge Graph)** — the raw data source. Real-time
(15-minute cadence) article-level metadata: themes, locations, tone,
entities — computed by GDELT's own NLP pipeline from each article's text.
It never provides the article's actual prose; only the URL and GDELT's
analysis of it. Field layout confirmed against GDELT's own codebook and
verified empirically against live downloaded data (not taken on faith):
`https://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf`

**GDELT's theme taxonomy** — the full reference list used to derive
`FLU_INCLUDE_THEMES`/`FLU_EXCLUDE_THEMES`, read in its entirety (8,528
`TAX_DISEASE_*` entries) before finalizing those sets:
`http://data.gdeltproject.org/api/v2/guides/LOOKUP-GKGTHEMES.TXT`

**WHO FluNet** — the ground-truth source for onset dates (Stage 1). Public
REST API, no authentication, confirmed live with a direct sample call
before building `pipeline/ground_truth.py` against it:
`https://xmart-api-public.who.int/FLUMART/VIW_FNT`

**trafilatura** (Stage 7, `pipeline/content_extractor.py`) — the library
that separates real article text from page boilerplate. Chosen over a
hand-rolled HTML tag-stripper (the original pipeline's approach, which left
navigation/ad/comment-form text mixed into the output) based on independent
third-party evidence, not just the library's own claims:
- Peer-reviewed: *"Trafilatura: A Web Scraping Library and Command-Line
  Tool for Text Discovery and Extraction"*, ACL 2021 —
  `https://aclanthology.org/2021.acl-demo.15.pdf`
- A 2023 SIGIR paper (Bevendorff et al., *"An Empirical Comparison of Web
  Content Extraction Algorithms"*) independently benchmarked 14 extraction
  tools and found trafilatura among the best-performing and most robust —
  notably outperforming neural-network-based extractors.
- A separate Sandia National Laboratories evaluation (Aug 2024) ranked it
  highest on both F1 and precision among the tools it compared.
It is not infallible — on the ScrapingHub article-extraction benchmark it
scores roughly F1 0.96, meaning it still makes mistakes on a small fraction
of pages. Worth spot-checking against this project's own messier real
cases (JS-heavy sites, non-English pages) before treating its output as
ground truth for labeling.

**google-api-python-client / google-auth-oauthlib** (optional, Stage 10
Google Drive backend) — Google's official Python client and OAuth helper,
used only if `STORAGE_BACKEND=gdrive`. Imported lazily in
`pipeline/storage.py` so they're not a hard dependency for local-only runs.

---

## 6. Open decisions — not resolved by this code, flagged deliberately

- **`TAX_DISEASE_JUNGLE_FLU`** — low-volume (17 occurrences GDELT-wide),
  ambiguous theme. Not in either theme list in `config.py`. Resolve and add
  it to the appropriate set with a comment once its meaning is confirmed.
- **Storage destination — resolved: Google Drive**, not an AWS/cloud-
  provider bucket. Implemented as `GoogleDriveStorageBackend` in
  `pipeline/storage.py`, using per-user OAuth credentials (not a service
  account — see section 2's one-time setup steps for why). Requires
  `PIPELINE_GDRIVE_FOLDER_ID` to be set and a one-time interactive login.
- **Headless-browser fetching** — not implemented. Before adding it,
  diagnose what fraction of current retrieval failures are genuinely
  JS-rendering gaps (which a headless browser fixes) versus bot-blocking
  (which it may or may not fix) versus dead links (which nothing fixes) —
  building this without that diagnosis is a guess at where the problem is.
- **Content-richness is a proxy, not verification** — Stage 9 cannot
  confirm an article actually reports case counts, deaths, or spread; that
  requires reading the text's meaning (LLM or real NLP), deferred entirely
  to a later phase. Every article this pipeline stores should be treated as
  a "plausible candidate" for a human labeler, not "confirmed relevant."
- **Geo cross-check and human-case relevance filtering** — both
  intentionally out of scope here (see section 4); GDELT's location data is
  stored as raw fact, not ground truth about relevance.
- **Stage 5's location condition is a gate, not an attribution** — it only
  answers "is at least one cohort country mentioned somewhere," the same
  flat presence check two earlier (removed) versions of this stage also
  used, just without either of their extra steps (window-coverage
  requirement, or a stored per-article country tag). It will still let
  through articles where the only cohort-country mention is passing or
  unrelated to the flu content (the Kenya wire-story / Australia
  "predicts our flu season" pattern) — that's accepted here as the cost of
  a cheap recall-oriented gate, with the full `locations` list stored
  precisely so a human labeler can make the real attribution call Stage 5
  deliberately doesn't attempt.

---

## 7. Final storage structure

One record per article -- every one already passed Stage 5's theme-and-
location gate, so it necessarily mentions at least one requested cohort
country somewhere in its `locations` list. Deliberately trimmed -- five
content fields plus the GDELT record ID as a storage key. No author, no
media/image links, no pass/fail gate booleans (a record only exists here
because it already passed both quality gates -- see Stages 8-9 -- so
storing that fact again would be redundant). The same JSON shape is used
by both backends.

**Bucketed by year.** Both backends group output into one bucket per
calendar year, so you can fetch just the year(s) you want instead of
scanning everything. `year` is the year of the article's own `datetime`
field (the GKG record's scan timestamp) -- it is **not** a country-season
year, since no single season year is attributable to a record once it
could match any requested country (see section 6, "Stage 5's location
condition is a gate, not an attribution", and the discussion of cross-
country window overlap). If you need "articles from country X's Nth flu
season specifically," filter further on `datetime` within that season's
own window bounds (recomputable from Stage 1 / `pipeline/ground_truth.py`
for that country) and on `locations` containing X -- this pipeline buckets
by year only, not by season or country.

### Local backend (default)
```
{LOCAL_STORAGE_DIR}/{year}/matched_articles.jsonl
```
One file per year, one JSON object per line within it, append-only. Pick
the year(s) you want by just opening that subdirectory, then filter
further in your own tooling by inspecting each line's `locations` list
(e.g. `jq 'select(.locations[].country_fips == "IN")'`) -- there's no
separate country field or per-country file to rely on instead.

### Google Drive backend
```
{PIPELINE_GDRIVE_FOLDER_ID}/{year}/{gkg_record_id}.json
```
One subfolder per year under the configured root folder (created
automatically on first use), one file per article inside it, keyed by its
GDELT record ID -- no per-country nesting. Open the year's subfolder and
filter on `locations` the same way.

### Record schema
```json
{
  "gkg_record_id": "20230115121500-66",
  "url": "https://example.com/flu-shot-article",
  "datetime": "2023-01-15T12:15:00",
  "themes": [
    {"theme": "TAX_DISEASE_INFLUENZA", "offset": 626}
  ],
  "locations": [
    {"name": "United States", "country_fips": "US", "offset": 580}
  ],
  "article": "..."
}
```

| Field | Meaning |
|---|---|
| `gkg_record_id` | GDELT's own ID for this record (format `{15-minute-file-timestamp}-{sequential-line-number}`), deterministic and unique across the whole dataset -- confirmed empirically, see section 4's Stage 10 note. Kept as the storage key (and the Drive file's name), and is also the cross-run deduplication key -- not one of the five content fields, just an identifier. |
| `url` | The article's source URL. |
| `datetime` | The GKG record's own scan timestamp (field 2 of the raw line), reformatted from GDELT's `YYYYMMDDHHMMSS` to ISO 8601. This is metadata *about when GDELT saw the article*, not a publish date extracted from the page itself -- trafilatura's own date/author/title extraction was dropped entirely (see `pipeline/content_extractor.py`) since none of it makes it into this schema. |
| `themes` | Only the flu-specific theme hits that made this article a candidate (Stage 5's `FLU_INCLUDE_THEMES` matches), each with its character offset -- not the article's full (often 20-50 entry) raw theme list. |
| `locations` | **Every** location GDELT found in the article, full and unfiltered -- not narrowed to just the cohort country (or countries) that satisfied Stage 5's location condition (see section 4, "Stage 5 -> condition 2"). Each entry is `{name, country_fips, offset}`; the richer raw fields (lat/lon, ADM1/ADM2, feature ID -- see `models.LocationHit`) are dropped here as GIS detail not needed for text-relevance labeling. |
| `article` | The cleaned article text from Stage 7 (trafilatura). |

### Run summary report

Every run of `run_pipeline.py` (`--test-timestamp` included) ends by
printing, and writing to `RUN_SUMMARY_PATH` (default
`./output/run_summary.json`, always local regardless of `STORAGE_BACKEND`
-- it's a small report, not pipeline output data), a count of stored
articles for each `(country, season_year)` window built in Stage 1/2
(`run_pipeline.py::build_window_report`):

```json
[
  {
    "country": "USA",
    "season_year": 2023,
    "window_start": "2023-10-06",
    "window_end": "2024-02-23",
    "total_articles": 212,
    "per_country_counts": {"USA": 204, "IND": 9, "AUS": 0}
  }
]
```

- `total_articles` -- every stored article whose `datetime` falls inside
  that window, **regardless of which country it mentions**.
- `per_country_counts` -- of that same subset, how many mention each
  requested country.

Two kinds of overlap show up here on purpose, not as bugs:
1. **A window's total can include articles about a different cohort
   country.** Stage 3 downloads the *union* of every requested country's
   window days (see section 6), and Stage 5's location filter checks
   against the full requested country set, not just the country whose
   window caused a given day to be downloaded. So "USA, season 2023" above
   including 9 India-mentioning articles means 9 articles happened to fall
   on a day inside USA's window that also (by presence-only match) mention
   India -- not that those 9 are part of India's own 2023 season.
2. **`per_country_counts` can sum to more than `total_articles`** if a
   single article mentions more than one requested country (e.g. a wire
   story covering both).

`--test-timestamp` mode reports against one synthetic window
(`country: "TEST"`, a single-day span) instead of a real season window,
and writes to `./output/test_run_summary.json` instead of the default
path, since there's no real FluNet onset involved in that mode.

---

## 8. Performance expectations

Based on this project's own prior measurements of GDELT's raw-file mirror
(not estimated from scratch): downloading and parsing all 96 files/day for
every day a cohort needs runs at roughly 100-150 calendar-days/hour with
reasonable concurrency (this generated code runs sequentially and is
slower than that reference point — add concurrency, e.g. a thread pool
around `gkg_downloader.download_file`, before a full multi-year run). A
full 6-country, 2015-2024 run covers on the order of 2,500-3,000 unique
calendar days.
