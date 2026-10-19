# Flu news LLM extractor

Runs a large language model over human-influenza news articles, extracts structured
findings, and scores the result against human labels. For each article the model says:

- whether the article is **useful** (does it contain a current human flu statement?), and
- the **items** it reports: `cases`, `deaths`, `hospitalized` or `trend`, with place, dates,
  numbers and the quoted evidence.

The model is **NVIDIA Nemotron 3.5 Lightning 30B-A3B**, called through NVIDIA's hosted,
OpenAI-compatible API. The prompt is a system prompt plus solved examples that are sent with
every request (few-shot prompting). Everything the extractor reads is inside this folder
(`prompts/` and `data/`), so it does not depend on where the capstone files are on disk.

## Contents

1. [Quick start](#1-quick-start)
2. [How it works](#2-how-it-works)
3. [Data formats](#3-data-formats)
4. [Commands](#4-commands)
5. [Configuration](#5-configuration)
6. [Prompt versions](#6-prompt-versions)
7. [Which rows are run](#7-which-rows-are-run)
8. [How results are scored](#8-how-results-are-scored)
9. [Automatic checks](#9-automatic-checks)
10. [Output files](#10-output-files)
11. [Testing](#11-testing)
12. [Layout](#12-layout)
13. [Known limitations](#13-known-limitations)

---

## 1. Quick start

Requirements: Python 3.12 (tested on 3.12.3), Linux, an NVIDIA API key with access to the model
(https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b), and internet access.

```bash
# one-time setup
cd llm-extractor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env          # then edit .env and put your key after NVIDIA_API_KEY=
chmod 600 .env                # only you can read it

# every session: activate the environment, then
python -m unittest discover tests                      # 1. the logic works (no API, no internet)
python run_extraction.py --rows 6                      # 2. ONE API call; prints the run folder name
python evaluate_run.py results/run_<timestamp>         # 3. score it, write the reports
python inspect_row.py results/run_<timestamp> 6        # 4. read that article field by field
python run_extraction.py                               # 5. all 257 rows (about 257 API calls)
python evaluate_run.py results/run_<timestamp>         # 6. score the full run, then read report.md
```

All commands run from the `llm-extractor` folder with the virtual environment active.
The API key is read from `.env` and never printed.

## 2. How it works

```
 prompts/system_prompt_*.txt ─┐
 prompts/examples_*.json ─────┼─► run_extraction.py ─► results/run_<time>/raw_results.jsonl
 data/articles.json ──────────┘   (one API call         (one line per article: reply, tokens,
                                   per article)           timing, errors)
                                                                   │
 data/human_labels.json ───────────────────────────────────────────┼─► evaluate_run.py ─► report.md
 data/place_lookups.json (saved place answers; geocoder if new) ───┘                      row_results.csv
                                                                                          item_comparison.csv
```

The two steps are separate on purpose: scoring can be repeated, or changed, without paying for
new model calls.

### Step 1: `run_extraction.py` (calls the model)

Order of execution:

| # | Function (module) | Input | Output |
|---|---|---|---|
| 1 | `load_articles` (`data_loading.py`) | `data/articles.json` | `{row: Article}` |
| 2 | `load_human_labels` (`data_loading.py`) | `data/human_labels.json` | `{row: HumanLabel}` |
| 3 | `load_examples` (`prompt.py`) | the examples JSON file | list of example dicts |
| 4 | `default_rows_to_run` (`evaluation.py`) or `parse_row_spec` | labels, example rows; or the `--rows` text | sorted list of row numbers |
| 5 | `rows_already_done` | an existing `raw_results.jsonl` (when resuming) | set of rows to skip |
| 6 | `load_system_prompt`, `build_prefix_messages` (`prompt.py`) | system prompt file, examples | the shared part of every request (see below) |
| 7 | `create_client` (`llm_client.py`) | settings from `config.py` and the API key | an `OpenAI` client |

Then, for each row (up to `--workers` at the same time), `extract_article` (`extractor.py`) runs:

| # | Function | Input | Output |
|---|---|---|---|
| a | `build_messages` (`prompt.py`) | the shared messages and one `Article` | the full list of chat messages |
| b | `ask_model` (`llm_client.py`) | client, messages | `ModelReply`: text, finish reason, token counts, seconds |
| c | `parse_reply` (`extractor.py`) | the reply text | the reply as a dict, or an error message |

The record is appended to `raw_results.jsonl` as soon as it is done. A failed call never stops
the run: the error is stored in the record.

**What the model receives.** One request is a list of chat messages:

1. a `system` message: the instructions (`system_prompt_*.txt`);
2. for each solved example, a `user` message with the example article, then an `assistant`
   message with the human answer as JSON (43 pairs for prompt v2.0). This is how the model
   learns the task and the reply format from worked examples; its weights do not change;
3. a final `user` message with the article to process.

Every article block, in the examples and for the real article, has the same layout
(`format_article` in `prompt.py`):

```
Scan date: 2016-12-30
Link: http://cbs6albany.com/news/local/...
Article:
<article text>
```

The messages in 1 and 2 are the same for every article and are built once per run. The human
labels of the articles being scored are never sent.

**Model call settings** (`llm_client.py`, values in `config.py`): `temperature=0` (no sampling
randomness), `max_tokens=4000` (ceiling for the reply), `extra_body` with
`enable_thinking: False` (a Nemotron setting: answer directly), a 300 s timeout and 4
automatic retries on rate-limit, timeout and server errors.

### Step 2: `evaluate_run.py` (scores a run)

| # | Function | Input | Output |
|---|---|---|---|
| 1 | `read_run_records` (`evaluation.py`) | `raw_results.jsonl` | `{row: record}` (a later line replaces an earlier one) |
| 2 | `load_articles`, `load_human_labels` | the data files | as in step 1 |
| 3 | `PlaceChecker(cache, offline)` (`places.py`) | `data/place_lookups.json`, `--offline` flag | the place checker |
| 4 | `evaluate_run` (`evaluation.py`) | records, articles, labels, place checker | an `Evaluation` |
| 5 | `write_report` (`report.py`) | the `Evaluation`, the run folder | `report.md`, `row_results.csv`, `item_comparison.csv` |

Inside `evaluate_run`, each row that has a human label gets a **status**:

| Status | Meaning |
|---|---|
| `api_error` | the call failed after all retries |
| `unparseable` | the reply was not valid JSON, or was cut off at `max_tokens` |
| `malformed` | valid JSON that breaks the reply format (`find_shape_errors`) |
| `scored` | everything is fine; the row enters the numbers |

Rows that are not `scored` are left out of every score and listed in section 4 of `report.md`.
Rows that are scored then get the rule checks (`find_rule_violations`), exact item matching
(`match_items` with `EXACT_KEY_FIELDS`), and their contribution to the usefulness and item tallies.

## 3. Data formats

**`data/articles.json`**: a list with one object per article (320). The fields are already
separated, so nothing has to be parsed from text at run time.

```json
{"row": 6, "article_id": "20161230170000-2179", "scan_date": "2016-12-30",
 "link": "http://cbs6albany.com/news/local/influenza-forcing-ny-hospitals-to-adjust-visitation-rules",
 "article": "Influenza forcing NY hospitals to adjust visitation rules\nALBANY, N.Y. (AP) -- ..."}
```

`row` is the row number in the labeling sheet and links an article to its label. `scan_date`
is the day the article was collected; the prompt uses it to turn "yesterday" into a date.

**`data/human_labels.json`**: the answer key, one object per article.

```json
{"row": 6, "article_id": "20161230170000-2179", "useful": true, "needs_relook": false,
 "items": [{"kind": "cases", "strain": null, "number": 658, "status": null, "total_or_new": "total",
            "city": null, "state": "New York", "country": "USA",
            "start_date": null, "end_date": "2016-12-30", "words": null,
            "evidence": ["Some 658 flu-related hospitalizations in New York have been reported so far this flu season."]}]}
```

`useful` is `true`, `false`, or `null` when the sheet has no label (rows 109 and 152).
`needs_relook` marks the 20 rows the labeler is unsure about. Each item has the same fields as
the model's items, so the two can be compared field by field.

**The model's reply** (one JSON object; its format is defined in the system prompt):

```json
{"useful": true, "borderline": false, "reason": "one sentence",
 "items": [{"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null,
            "city": null, "state": "New York", "country": "USA",
            "start_date": "2016-12-30", "end_date": "2016-12-30",
            "words": "widespread and prevalent", "evidence": ["exact quote from the article"]}],
 "findings": []}
```

| Field | Meaning |
|---|---|
| `useful` | true if the article has a current human flu statement |
| `borderline` | the model finds the decision hard |
| `kind` | `cases`, `deaths`, `hospitalized` or `trend` |
| `strain`, `number` | e.g. `"H1N1"`, `658`; null when not stated |
| `status` | `"confirmed"`, `"suspected"` or null |
| `total_or_new` | `"total"`, `"new"` or null |
| `city`, `state`, `country` | null or a real place; the prompt writes the country as e.g. `"USA"` |
| `start_date`, `end_date` | `YYYY-MM-DD` or null |
| `words` | only for `trend` items: the words that describe the trend; null otherwise |
| `evidence` | non-empty list of exact quotes from the article |
| `findings` | statements about when a flu season starts, peaks or ends: `[{"country": ..., "finding": "<sentence copied from the article>"}]` |

**Solved examples** (`prompts/examples_*.json`): a list of objects with `example`, `source_row`,
`teaches`, `scan_date`, `link`, `article` and `answer` (same shape as a model reply). Only
`scan_date`, `link`, `article` and `answer` are sent to the model. `teaches` is a note for people.
`source_row` is the article's row in the labeling sheet: those rows are never scored.

**One log line** (`raw_results.jsonl`):

```json
{"row": 6, "article_id": "...", "model": "nvidia/nemotron-3.5-lightning-30b-a3b",
 "finish_reason": "stop", "prompt_tokens": 28225, "completion_tokens": 198, "seconds": 6.1,
 "raw_reply": "{\"useful\": true, ...}", "parsed": {...the reply as an object...},
 "parse_error": null, "api_error": null}
```

`finish_reason` is `stop` when the model finished and `length` when it hit `max_tokens` (the
reply is then incomplete and is not parsed). Both the raw text and the parsed object are kept,
so parsing or scoring can change later without new model calls. JSONL (one object per line) is
used so that lines can be appended safely and nothing is lost if a run is interrupted.

**`data/place_lookups.json`**: saved answers of the place check. Key `"city: allahabad"`, value
`{"found": true, "top_match": "Prayagraj, Allahabad, ...", "checked_on": "2026-10-18"}`.

## 4. Commands

### `run_extraction.py`: ask the model

| Option | Meaning |
|---|---|
| `--rows 1-20,47` | run exactly these rows, even rows that are normally excluded (see section 7) |
| `--limit N` | run only the first N of the selected rows |
| `--exclude-file FILE` | extra rows to leave out, one number per line (`#` starts a comment); ignored when `--rows` is given |
| `--workers N` | requests at the same time (default 3). Lower it if you see rate-limit errors |
| `--run-dir DIR` | continue an existing run folder: rows that already have a reply are skipped |

Each run writes a new folder `results/run_<date>_<time>/`. With `--run-dir`, only rows whose call
**failed with an API error** are retried. A row whose reply was invalid JSON counts as done: to
retry it, delete its line from `raw_results.jsonl`. Records are written in the order they finish,
not in row order.

### `evaluate_run.py RUN_DIR`: score a run

| Option | Meaning |
|---|---|
| `--offline` | do not look up place names online; use only the saved answers. Names that were never looked up are reported as "could not be checked" |

Writes `report.md`, `row_results.csv` and `item_comparison.csv` into the run folder, and prints a
short summary. New place names are looked up online, about one per second, and saved.

### `inspect_row.py RUN_DIR ROW`: read one article field by field

| Option | Meaning |
|---|---|
| `--article` | also print the article text |
| `--offline` | do not look up place names online |

Prints the call details, the usefulness verdict (human vs model), and every item with **all** its
fields, human and model side by side, each flagged `same` or `DIFFERENT`. Items are labeled
`EXACT MATCH`, `NOT EXACT` (same kind and place, with the differing fields named), `MISSING FROM
MODEL` or `EXTRA FROM MODEL`. It also prints both sides' evidence quotes and any rule violations.
It uses the same scoring code as the reports, so what it shows is what gets counted.

### `scripts/build_data_files.py`: refresh `data/` from the capstone files

```bash
python scripts/build_data_files.py                     # rewrites data/articles.json and data/human_labels.json
python scripts/build_data_files.py --capstone-dir /path/to/capstone
python scripts/build_data_files.py --with-prompts      # ALSO overwrites the active files in prompts/
```

`data/` is a snapshot of the capstone labeling files (Jahnavi's sheets). Run this only when the
labels change. It is the only code that knows where the capstone folder is. By default it leaves
`prompts/` alone; `--with-prompts` overwrites the active prompt files with prompt v2.0, taken from
`prompt_versions/llm_extraction_prompt_v2.0.md` and from the capstone examples file
(`Project Documents /llm_extraction_examples_v2.0.jsonl`, which is not copied into this project).

## 5. Configuration

Secrets and overrides go in `.env` (copy `.env.example`). Everything else is in
`flu_extractor/config.py`.

| Setting | Where | Default |
|---|---|---|
| `NVIDIA_API_KEY` | `.env` (required) | none |
| `NVIDIA_MODEL_ID` | `.env` (optional) | `nvidia/nemotron-3.5-lightning-30b-a3b` |
| `NVIDIA_BASE_URL` | `.env` (optional) | `https://integrate.api.nvidia.com/v1` |
| `RESULTS_DIR` | `.env` (optional) | `llm-extractor/results` |
| `SYSTEM_PROMPT_PATH`, `EXAMPLES_PATH` | `config.py` | `prompts/system_prompt_v2.0.txt`, `prompts/examples_v2.0.json` |
| `ARTICLES_PATH`, `HUMAN_LABELS_PATH`, `PLACE_CACHE_PATH` | `config.py` | `data/articles.json`, `data/human_labels.json`, `data/place_lookups.json` |
| `TEMPERATURE`, `MAX_TOKENS` | `config.py` | 0, 4000 |
| `REQUEST_TIMEOUT_SECONDS`, `MAX_RETRIES` | `config.py` | 300, 4 |
| `EXTRA_BODY` | `config.py` | `{"chat_template_kwargs": {"enable_thinking": False}}` |

Other tuning points: the places check pace and retries are at the top of `flu_extractor/places.py`;
the item matching rules are at the top of `flu_extractor/metrics.py`.

## 6. Prompt versions

**`prompts/` always holds the active version**, meaning the two files the code actually reads:
the system prompt (`.txt`, instructions only) and the examples (`.json`). They are named in
`config.py` (`SYSTEM_PROMPT_PATH`, `EXAMPLES_PATH`); no other file in `prompts/` is read.

**`prompt_versions/` is the archive**: the full prompt documents, one file per version, for
tracking drafts and older versions. No code reads it, except `scripts/build_data_files.py
--with-prompts`, which can regenerate the active v2.0 files from `llm_extraction_prompt_v2.0.md`.

| File | What it is |
|---|---|
| `prompt_versions/llm_extraction_prompt_v1.0.md` | prompt v1.0, the full document (earlier version, 14 solved examples) |
| `prompt_versions/llm_extraction_prompt_v2.0.md` | prompt v2.0, the full document: notes, instructions, 43 solved examples, reply schema, scoring notes. **This is the active version.** Its instructions are `prompts/system_prompt_v2.0.txt` and its examples are `prompts/examples_v2.0.json` |

A full document holds more than the model is sent (change notes, the reply schema, scoring
advice). The model receives only the instructions and the examples, as split into `prompts/`.
Add each new draft to `prompt_versions/` with its version in the file name.

To make a new version active:
1. Create its two files and put them in `prompts/`: the instructions as a plain `.txt` file (for
   v2.0 this is the text inside the code fence under "## 1. Instructions") and the examples as a
   `.json` file. The project only automates this for v2.0 (`build_data_files.py --with-prompts`);
   for any other version you make the two files yourself. The previous active files are not kept
   in `prompt_versions/` (it holds full documents), so keep a copy somewhere if you need them.
2. If the file names changed, update the two paths in `config.py`.
3. The examples file must keep the fields listed in section 3. Its `source_row` values decide
   which rows are never scored, so changing the examples changes the excluded rows automatically.
4. Try `python run_extraction.py --rows 6` first, then a full run.

Two things to know:
- `run_config.json` in each run folder records the **file names** used, not their contents. If you
  edit a file without renaming it, older runs can no longer be traced to the exact text. Keep each
  version in `prompt_versions/`.
- The model's replies vary a little from run to run even at `temperature=0` (the same article gave
  different items on two runs). A small change in a score between two prompt versions may be noise;
  compare on the full set.

## 7. Which rows are run

Without `--rows`, a run covers every row of `human_labels.json` except:
- rows with no human label (`useful` is null: rows 109 and 152),
- rows marked `needs_relook` (the 20 rows the labeler is unsure about),
- the rows whose solved answers are inside the prompt (the `source_row` values of the examples file;
  scoring them would be cheating, because the model has seen their answers),
- rows in `--exclude-file`, if given.

For prompt v2.0 that leaves **257 rows (48 useful)**. `--rows` bypasses these exclusions and runs
exactly the rows named. There is no separate test split yet: the same Jahnavi data is used for
both tuning and scoring.

## 8. How results are scored

**Usefulness.** Positive class = *useful*, the human label is the truth. The report gives a
confusion table and precision, recall, F1 and accuracy.

**Items.** The model's `items` for an article are compared with the human items of the same
article. Every scored article counts, so items written for a not-useful article are extras.
**Evidence is never compared**: the model and the labeler may quote different sentences for the
same fact.

*Exact item match (the headline).* A model item is an exact match when `kind`, `strain`, `number`,
`status`, `total_or_new`, `city`, `state`, `country`, `start_date`, `end_date` and `words` all agree
with a human item. Upper/lower case and repeated spaces are ignored; nothing else is; null equals
null. Each human item can be matched once. Then:
- **matched** = exact matches (TP); **extra** = model items with no exact human counterpart (FP);
  **missing** = human items with no exact model counterpart (FN);
- precision = matched / model items; recall = matched / human items; F1 = 2·TP / (2·TP + FP + FN);
  per kind and pooled.

*Item set per article.* Is the model's whole item list identical to the human's? Six mutually
exclusive outcomes:

| Outcome | Meaning |
|---|---|
| exact set match | same number of items and every item matches exactly |
| exact set match, no items on either side | the human and the model both found no items |
| model has extra items only | every human item matched, and the model wrote more |
| model is missing items only | every model item matched, and the human wrote more (includes the model returning nothing) |
| some items match; others are missing or extra | a mix |
| items on both sides, none match | e.g. one item each, but they differ |

The report gives the exact-set-match rate overall and again only for articles where the human
found items, because "no items on either side" is easy and flatters the overall figure.

*Looser comparisons* (diagnosis only): (1) kind, place, strain and dates agree, with how often
`number` also agrees; (2) kind, place and strain agree (dates ignored). A big gap to the exact table
shows which kind of field is going wrong.

`item_comparison.csv` lists every item. Where a human item and a model item have the same kind
and place but are not an exact match, they share one line, with `differing_fields` naming what
differs and the two values side by side.

**Findings** (the `findings` list in the reply) are not scored, only checked (rule a).

## 9. Automatic checks

Reply format errors make a row `malformed` (not scored): missing keys, `useful` not true/false,
a kind other than the four, an invalid date, a place that is not text or null, evidence that is
not a non-empty list of text, malformed `findings`. Rule violations do **not** stop a row from
being scored; they are reported so you can read those rows with care:

| Rule | Check |
|---|---|
| (a) | every evidence quote and finding sentence is an exact piece of the article |
| (b) | `words` is null unless the kind is `trend` |
| (d) | `city`, `state`, `country` are null or a real place of that kind |
| (e) | `start_date` is not after `end_date` |
| (f) | no two items of the same kind, strain and place with overlapping dates |
| (g) | if `useful` is false, `items` is empty |

(There is no rule (c): the "only four kinds" rule is a reply-format error.) Rule (f) is my reading
of "no overlapping items": items without an end date are never flagged.

### Rule (a): evidence is copied from the article

Only line breaks and repeated spaces are ignored. Each failure gets one of three reasons, counted
separately in `report.md`:

| Reason | Meaning |
|---|---|
| not found in the article | reworded, shortened (for example with "..."), joined from separate places, or invented |
| differs only in quote or dash characters | the words are the article's, but curly quotes or dashes were changed to plain ones |
| empty | the quote is blank |

It proves the text exists in the article, not that the quote supports the item, and a very short
quote passes trivially.

### Rule (d): places are real

There is no list of names in the code. For each non-null place field, `PlaceChecker.is_known`
asks OpenStreetMap's free geocoder (Nominatim) one question per field:
`country=...`, `state=...` or `city=...`. A field is checked only against its own kind: "India" is
not a state, "California" is not a country, and "Southern Hemisphere", "Europe", "Global",
"Northern India" and "Central Coast" are not found. Empty answer = not found.

- **Answers are saved** in `data/place_lookups.json` with the best match and the date. Each name is
  looked up once; later runs give the same answers without internet and can be committed to repeat
  a result exactly. New names are looked up at about one per second (Nominatim's usage policy;
  do not lower `MIN_SECONDS_BETWEEN_REQUESTS` in `places.py`).
- **If the service is unreachable** the value is reported as "could not be checked". It is never
  guessed and nothing is saved, so the next run asks again.
- The 83 distinct place values in the labels and the prompt examples were all found.

Limits: a match means a place with that name exists *somewhere* ("Harmanli" matched villages in
Turkey); the geocoder forgives misspelled cities ("Mumbay" matched Mumbai, "Sidney" matched Sydney,
while misspelled states and countries were rejected); each field is checked alone, so a city is not
checked against its stated state or country; map data changes over time (the saved `checked_on`
dates show how old an answer is; delete a line to ask again).

Place data: © OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright).
Keep this credit if you share results that include `data/place_lookups.json`.

## 10. Output files

Per run, in `results/run_<date>_<time>/` (the `results/` folder is ignored by git):

| File | Content |
|---|---|
| `raw_results.jsonl` | one line per article: raw reply, parsed reply, finish reason, token counts, seconds, errors |
| `run_config.json` | model, prompt file names, temperature, max tokens, start time of the run |
| `report.md` | section 1 usefulness; 2 item correctness (2.1 exact, 2.2 item sets, 2.3 looser); 3 rule checks, with the evidence summary; 4 coverage (rows not scored and why) |
| `row_results.csv` | per article: `status`, human and model usefulness, `borderline`, `human_items`, `model_items`, `items_exact_matched`, `items_missing`, `items_extra`, `item_set_outcome`, `rule_violations`, `problems`, the model's `reason` |
| `item_comparison.csv` | one line per item. `outcome`: `exact match`, `same kind and place` (not exact; `differing_fields` names what differs), `missing from model` (human item only) or `extra from model` (model item only). Shared columns: kind, strain, city, state, country. Side by side (`human_…`, `model_…`): number, status, total_or_new, start_date, end_date, words, evidence |

Read `report.md` in this order: section 4 (how many rows could not be scored), section 3 (rule
violations), section 1 (usefulness), section 2 (items). Then open `item_comparison.csv` or
`inspect_row.py` to see why items fail.

## 11. Testing

```bash
python -m unittest discover tests
```

Needs no API key and no internet (the place check uses a fake geocoder).

| File | Covers |
|---|---|
| `tests/test_checks.py` | rule (a) exact-quote check, findings, shape errors |
| `tests/test_metrics.py` | exact item matching, the six item-set outcomes, F1 and the usefulness table |
| `tests/test_places.py` | the place cache, offline mode, an unreachable service, rule (d) |

Not covered by tests: the live API call, `report.py`, and the command-line scripts. Check those by
running a single row (section 1) and reading it with `inspect_row.py`.

## 12. Layout

```
prompts/           ACTIVE prompt: system prompt (.txt) and solved examples (.json)
prompt_versions/   archive: the full prompt documents (v1.0, v2.0, ...), not read by the extractor
data/              articles.json, human_labels.json, place_lookups.json
results/           one folder per run (ignored by git)
scripts/
  build_data_files.py   refresh data/ from the capstone files (prompts/ only with --with-prompts)
tests/             unit tests (section 11)
flu_extractor/
  config.py        paths and model settings
  data_loading.py  read articles and human labels
  prompt.py        build the chat messages (system prompt, example turns, article)
  llm_client.py    the only code that calls the model API
  extractor.py     one article -> one log record (parsing the reply, never crashing)
  checks.py        reply format check and the automatic rule checks
  places.py        asks the geocoder whether a city/state/country exists; saves the answers
  metrics.py       precision/recall/F1, usefulness scoring, item matching, item-set outcomes
  evaluation.py    score a whole run against the labels; choose the default rows
  report.py        write report.md and the two CSV files
run_extraction.py  command-line tool: ask the model
evaluate_run.py    command-line tool: score a run
inspect_row.py     command-line tool: one article, human vs model, field by field
```

## 13. Known limitations

- **No held-out test set yet.** Tuning and scoring use the same Jahnavi rows, so scores from
  repeated prompt tweaks will be optimistic. Reserve a test split before reporting results.
- **Run-to-run variation.** The hosted model does not return identical output for identical input,
  even at `temperature=0`. One run is a noisy measurement.
- **Examples are sent as chat turns.** The v2.0 prompt document allows this, or pasting the examples
  as text inside the system message. Runs made in the text form (the earliest smoke tests) are not
  directly comparable.
- **Date convention (review these rows by hand).** The prompt dates articles by scan date; the human
  sheets prefer the printed date, then the link date, then the scan date. For an article published
  before the day it was scanned, relative dates ("yesterday", "on Tuesday") are counted from
  different days, so item dates can differ for that reason alone. Known rows from the project
  handoff: **40, 47 and 90**. In rows 47 and 90 the human item dates end one day before the scan
  date; in row 47 the link date is the day before the scan date. The list was made by hand and may
  be incomplete. The code treats these rows like any other.
- **Invalid JSON.** The model can put an unescaped `"` inside an evidence string, which breaks the
  JSON (seen once, before the chat-turn layout). Such rows are reported as not scored. Structured
  output, as the prompt document suggests, is the planned fix; it has not been tried.
- **Exact matching is demanding on `words`.** For trend items the human `words` is sometimes a short
  summary and sometimes a quote (the prompt notes 9 of 64 are summaries), and a model can phrase it
  differently. Such items count as missing and extra even when they describe the same thing; see
  `differing_fields` in `item_comparison.csv`. To ignore more than case and repeated spaces, edit
  `_normalise` in `flu_extractor/metrics.py`.
- **Garbled characters.** 15 source articles contain broken characters such as `â`. The prompt tells
  the model to copy evidence "as printed", so this is expected, not a bug in this code.
- **Human evidence.** One human quote (row 86) does not occur word for word in its article; it
  appears to join two separate lines.
- **Cost and speed.** A full run is about 257 calls of roughly 28,000-30,000 prompt tokens each. Hosted
  API quotas and latency are not guaranteed.
