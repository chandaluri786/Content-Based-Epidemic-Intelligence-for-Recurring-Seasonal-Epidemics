# Flu news LLM extractor

Runs a large language model over human-influenza news articles, extracts structured
facts, and scores the result against human labels. For each article the model says:

- whether the article is **useful** (does it contain a current human flu statement?), and
- the **items** it reports: `cases`, `deaths`, `hospitalized` or `trend`, with place, dates,
  numbers and the quoted evidence.

The model is **NVIDIA Nemotron 3.5 Lightning 30B-A3B**, called through NVIDIA's hosted,
OpenAI-compatible API. The prompt is a system prompt plus solved examples that are sent with
every request (few-shot prompting). Everything the extractor reads is inside this folder
(`prompts/` and `data/`), so it does not depend on where the capstone files are on disk.

The data is the team's 1,200 hand-labeled articles (four labelers), split into **dev** (397
articles, tune the prompt on these) and **test** (803 articles, run once at the end). The split is
frozen in `repo-sampling/sampling/split/dev_test_split.csv`. Runs use dev unless you ask for test.

## Contents

1. [Quick start](#1-quick-start)
2. [How it works](#2-how-it-works)
3. [Data formats](#3-data-formats)
4. [Commands](#4-commands)
5. [Configuration](#5-configuration)
6. [Prompt versions](#6-prompt-versions)
7. [Which articles are run](#7-which-articles-are-run)
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
python run_extraction.py --ids 20161230170000-2179     # 2. ONE API call; prints the run folder name
python evaluate_run.py results/run_<timestamp>         # 3. score it, write the reports
python inspect_row.py results/run_<timestamp> 20161230170000-2179   # 4. read that article field by field
python run_extraction.py                               # 5. all dev articles (373 API calls with prompt v2.2)
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
| 1 | `load_articles` (`data_loading.py`) | `data/articles.json` | `{article_id: Article}` |
| 2 | `load_human_labels` (`data_loading.py`) | `data/human_labels.json` | `{article_id: HumanLabel}` |
| 3 | `load_examples` (`prompt.py`) | the examples JSON file | list of example dicts |
| 4 | `default_ids_to_run` (`evaluation.py`) or `parse_id_spec` | labels, split, example IDs; or the `--ids` text | sorted list of article IDs |
| 5 | `check_test_guard` | the chosen IDs, the examples, `--final` | stops the run if it would touch test articles without `--final`, or with examples from test |
| 6 | `ids_already_done` | an existing `raw_results.jsonl` (when resuming) | set of article IDs to skip |
| 7 | `load_system_prompt`, `build_prefix_messages` (`prompt.py`) | system prompt file, examples | the shared part of every request (see below) |
| 8 | `create_client` (`llm_client.py`) | settings from `config.py` and the API key | an `OpenAI` client |

Then, for each article (up to `--workers` at the same time), `extract_article` (`extractor.py`) runs:

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
   message with the human answer as JSON (24 pairs for prompts v2.1 and v2.2). This is how the model
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
`enable_thinking: False` (a Nemotron setting: answer directly) and a 300 s timeout. Timeouts,
dropped connections and server errors are retried 4 times (2, 4, 8, 16 s apart).

**Pacing** (`pacing.py`): the API sends no rate-limit headers, so the run keeps under the limit
itself. At most `--calls-per-minute` calls (default 10) start in any 60 s, shared by all workers.
After a 429 every worker pauses together (60 s, doubling up to 5 min), the rate halves (never below
2 per minute), and the same article is tried again, so a rate limit no longer leaves `api_error`
records behind. If 15 minutes pass with no successful call, the run stops, prints `STOPPED` and how
to resume, and exits with code 2. Articles that were not finished are not logged, so `--run-dir`
runs them.

### Step 2: `evaluate_run.py` (scores a run)

| # | Function | Input | Output |
|---|---|---|---|
| 1 | `read_run_records` (`evaluation.py`) | `raw_results.jsonl` | `{article_id: record}` (a later line replaces an earlier one) |
| 2 | `load_articles`, `load_human_labels` | the data files | as in step 1 |
| 3 | `PlaceChecker(cache, offline)` (`places.py`) | `data/place_lookups.json`, `--offline` flag | the place checker |
| 4 | `evaluate_run` (`evaluation.py`) | records, articles, labels, place checker | an `Evaluation` |
| 5 | `write_report` (`report.py`) | the `Evaluation`, the run folder | `report.md`, `row_results.csv`, `item_comparison.csv` |

Inside `evaluate_run`, each article that has a human label gets a **status**:

| Status | Meaning |
|---|---|
| `api_error` | the call failed after all retries |
| `unparseable` | the reply was not valid JSON, or was cut off at `max_tokens` |
| `malformed` | valid JSON that breaks the reply format (`find_shape_errors`) |
| `scored` | everything is fine; the article enters the numbers |

Articles that are not `scored` are left out of every score and listed in section 4 of `report.md`.
Articles that are scored then get the rule checks (`find_rule_violations`), exact item matching
(`match_items` with `EXACT_KEY_FIELDS`), and their contribution to the usefulness and item tallies.

## 3. Data formats

**`data/articles.json`**: a list with one object per article (1,200), ordered by `article_id`.
The fields are already separated, so nothing has to be parsed from text at run time.

```json
{"article_id": "20161230170000-2179", "labeler": "Jahnavi", "split": "test", "scan_date": "2016-12-30",
 "link": "http://cbs6albany.com/news/local/influenza-forcing-ny-hospitals-to-adjust-visitation-rules",
 "article": "Influenza forcing NY hospitals to adjust visitation rules\nALBANY, N.Y. (AP) -- ..."}
```

`article_id` links an article to its label, to the run log and to the prompt examples. `labeler`
is who owns the article's label, and `split` is `dev` or `test`. `scan_date` is the day the article
was collected; the prompt uses it to turn "yesterday" into a date.

**`data/human_labels.json`**: the answer key, one object per article.

```json
{"article_id": "20161230170000-2179", "labeler": "Jahnavi", "split": "test", "useful": true,
 "items": [{"kind": "cases", "strain": null, "number": 658, "status": null, "total_or_new": "total",
            "city": null, "state": "New York", "country": "USA",
            "start_date": null, "end_date": "2016-12-30", "words": null,
            "evidence": ["Some 658 flu-related hospitalizations in New York have been reported so far this flu season."]}]}
```

`useful` is `true` or `false` (311 of the 1,200 are useful). Each item has the same fields as the
model's items, so the two can be compared field by field. The labels follow the rulebook in
`repo-sampling/sampling_and_labeling_guide.md`.

**The model's reply** (one JSON object; its format is defined in the system prompt):

```json
{"useful": true, "borderline": false, "reason": "one sentence",
 "items": [{"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null,
            "city": null, "state": "New York", "country": "USA",
            "start_date": "2016-12-30", "end_date": "2016-12-30",
            "words": "widespread and prevalent", "evidence": ["exact quote from the article"]}]}
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

Prompt v2.0 also asks for `findings` (season start and peak sentences). The rulebook dropped them,
so the key is no longer required and is ignored when a reply still has it.

**Solved examples** (`prompts/examples_*.json`): a list of objects with `example`, `article_id`,
`teaches`, `scan_date`, `link`, `article` and `answer` (same shape as a model reply). Only
`scan_date`, `link`, `article` and `answer` are sent to the model. `teaches` is a note for people.
`article_id` names the labeled article the example comes from: those articles are never scored.
New examples must come from dev. (The v2.0 examples also keep `source_row`, their row in Jahnavi's
sheet.)

**One log line** (`raw_results.jsonl`):

```json
{"article_id": "20161230170000-2179", "split": "dev", "model": "nvidia/nemotron-3.5-lightning-30b-a3b",
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
| `--ids ID1,ID2` or `--ids @FILE` | run exactly these articles (a file has one ID per line, `#` starts a comment), even examples |
| `--split dev\|test` | the split to run when `--ids` is not given (default `dev`) |
| `--final` | allow test articles. Use it once, for the final test run (see section 7) |
| `--limit N` | run only the first N of the selected articles |
| `--exclude-file FILE` | extra article IDs to leave out, one per line; ignored when `--ids` is given |
| `--workers N` | requests at the same time (default 3) |
| `--calls-per-minute N` | at most N calls start in any 60 s (default 10, or `CALLS_PER_MINUTE` in `.env`); halves by itself after a 429 |
| `--run-dir DIR` | continue an existing run folder: articles that already have a reply are skipped |

Each run writes a new folder `results/run_<date>_<time>/`. With `--run-dir`, only articles whose call
**failed with an API error** are retried. An article whose reply was invalid JSON counts as done: to
retry it, delete its line from `raw_results.jsonl`. Records are written in the order they finish.
A resume with another prompt or labels file than the run was made with is refused (the names are in
`run_config.json`).

### `evaluate_run.py RUN_DIR`: score a run

| Option | Meaning |
|---|---|
| `--offline` | do not look up place names online; use only the saved answers. Names that were never looked up are reported as "could not be checked" |
| `--labels FILE` | score against another labels file (for example `data/human_labels_jahnavi.json`); the reports go to a sub-folder `vs_<file name>/` and the run's own reports are left alone |

A run is scored against the labels file it was made with. If `HUMAN_LABELS_PATH` names another one,
scoring is refused unless `--labels` is given, so a run is never scored against the wrong set by
accident.

Writes `report.md`, `row_results.csv` and `item_comparison.csv` into the run folder, and prints a
short summary. New place names are looked up online, about one per second, and saved.

### `inspect_row.py RUN_DIR ARTICLE_ID`: read one article field by field

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
python scripts/build_data_files.py --sampling-dir /path/to/repo-sampling
python scripts/build_data_files.py --with-prompts      # ALSO overwrites the active files in prompts/
python scripts/build_data_files.py --labeling-dir ../../repo-sampling/sampling/output/labeled-data-reviewed-by-jahnavi \
    --labels-out data/human_labels_jahnavi.json        # a second label set; writes only that file
```

`data/` is a snapshot of the `repo-sampling` worktree: the article texts from
`sampling/output/sample_1200.jsonl`, the four labelers' sheets in `sampling/output/labeling/`
(`<Name>_labels.csv` and `<Name>_items.csv`), and the split in `sampling/split/dev_test_split.csv`.
Each article's answer comes from the labeler who owns it; the round-1 check rows are skipped.
Evidence cells are split into quotes at `||`. Run it only when a label changes. It is the only code
that knows where those files are.

Before writing anything it checks that the three sources fit together and stops with a list of
problems if not: 1,200 articles in each, every `useful` is yes or no and agrees with the split,
every `yes` has items and every `no` has none, and every item has a valid kind, status,
total_or_new, a country, `YYYY-MM-DD` dates, a whole `number` and no empty quote.

With `--labeling-dir` and `--labels-out` it reads another copy of the four sheets (such as
Jahnavi's reviewed set) and writes only that labels file. Each article keeps its split from the
frozen split file but takes `useful` from those sheets, so only the "agrees with the split" check is
skipped. It never overwrites `data/human_labels.json`.

By default it leaves `prompts/` alone. `--with-prompts` overwrites the active prompt files with
prompt v2.0, taken from `prompt_versions/llm_extraction_prompt_v2.0.md` and from the capstone
examples file (`Project Documents /llm_extraction_examples_v2.0.jsonl` under `--capstone-dir`, not
copied into this project). That file has no `article_id`, so add it again if you ever use this.

## 5. Configuration

Secrets and overrides go in `.env` (copy `.env.example`). Everything else is in
`flu_extractor/config.py`.

| Setting | Where | Default |
|---|---|---|
| `NVIDIA_API_KEY` | `.env` (required) | none |
| `NVIDIA_MODEL_ID` | `.env` (optional) | `nvidia/nemotron-3.5-lightning-30b-a3b` |
| `NVIDIA_BASE_URL` | `.env` (optional) | `https://integrate.api.nvidia.com/v1` |
| `RESULTS_DIR` | `.env` (optional) | `llm-extractor/results` |
| `PROMPT_VERSION` | environment or `.env` (optional) | `v2.2`; sets `SYSTEM_PROMPT_PATH` = `prompts/system_prompt_<version>.txt` and `EXAMPLES_PATH` = `prompts/examples_<version>.json` |
| `HUMAN_LABELS_PATH` | environment or `.env` (optional) | `data/human_labels.json` (relative to `llm-extractor/`) |
| `ARTICLES_PATH`, `PLACE_CACHE_PATH` | `config.py` | `data/articles.json`, `data/place_lookups.json` |
| `TEMPERATURE`, `MAX_TOKENS` | `config.py` | 0, 4000 |
| `REQUEST_TIMEOUT_SECONDS`, `MAX_RETRIES`, `RETRY_BASE_SECONDS` | `config.py` | 300, 4, 2 (timeouts and server errors only) |
| `CALLS_PER_MINUTE` | environment or `.env` (optional) | 10 |
| `MIN_CALLS_PER_MINUTE`, `RATE_LIMIT_FIRST_PAUSE_SECONDS`, `RATE_LIMIT_MAX_PAUSE_SECONDS`, `RATE_LIMIT_GIVE_UP_SECONDS` | `config.py` | 2, 60, 300, 900 |
| `EXTRA_BODY` | `config.py` | `{"chat_template_kwargs": {"enable_thinking": False}}` |

Other tuning points: the places check pace and retries are at the top of `flu_extractor/places.py`;
the item matching rules are at the top of `flu_extractor/metrics.py`.

## 6. Prompt versions

**`prompts/` always holds the active version**, meaning the two files the code actually reads:
the system prompt (`.txt`, instructions only) and the examples (`.json`). They are named in
`config.py` (`SYSTEM_PROMPT_PATH`, `EXAMPLES_PATH`); no other file in `prompts/` is read.

**`prompt_versions/` is the archive**: the full prompt documents, one file per version, plus the
example selection for each version from v2.1 on.

| File | What it is |
|---|---|
| `prompt_versions/llm_extraction_prompt_v1.0.md` | prompt v1.0, the full document (earlier version, 14 solved examples) |
| `prompt_versions/llm_extraction_prompt_v2.0.md` | prompt v2.0 (43 examples, the old rules, `findings`). Its files `prompts/system_prompt_v2.0.txt` and `prompts/examples_v2.0.json` are kept |
| `prompt_versions/llm_extraction_prompt_v2.2.md` | prompt v2.2, **the active version**: v2.1 plus the wording fixes from Jahnavi's feedback that the labels already follow (its first table lists them) |
| `prompt_versions/llm_extraction_prompt_v2.1.md` | prompt v2.1: the rules copied from the rulebook (`repo-sampling/sampling_and_labeling_guide.md`), what changed since v2.0, the example table, the reply schema and how to tune |
| `prompt_versions/examples_v2.1_selection.json` | which 24 dev articles are the v2.1 examples (v2.2 uses the same 24 in `examples_v2.2_selection.json`), with `teaches`, `reason`, and the lines kept for trimmed articles |
| `prompt_versions/llm_extraction_prompt_v4.1.md` | Jahnavi's track: her v4.0 instructions word for word plus 24 examples (`examples_v4.1_selection.json`) whose answers come from her labels. Not the active version |

**Jahnavi's track.** Jahnavi's reviewed sheets and her prompt are run separately from the team's,
on the same frozen dev split. Her labels are `data/human_labels_jahnavi.json`; nothing from her
track's dev errors goes into the team's rulebook or prompts. Her v4.0 was written from errors on all
1,200 articles, test included, so its scores are not held-out scores.

```bash
python scripts/build_prompt_files.py v4.1 --labels data/human_labels_jahnavi.json
PROMPT_VERSION=v4.1 HUMAN_LABELS_PATH=data/human_labels_jahnavi.json python run_extraction.py
PROMPT_VERSION=v4.1 HUMAN_LABELS_PATH=data/human_labels_jahnavi.json python evaluate_run.py results/run_X
python evaluate_run.py results/run_X --labels data/human_labels.json     # the same run against the team's labels
```

A full document holds more than the model is sent (change notes, the reply schema, tuning
advice). The model receives only the instructions and the examples, as built into `prompts/`.

To make a new version (for example v2.2):
1. Copy the document and the selection file to the new version number and make the change in them.
   A rule wording changes only when the rulebook already says it.
2. Run `python scripts/build_prompt_files.py v2.2`. It writes `prompts/system_prompt_v2.2.txt` (the
   code fence under "## 1. Instructions") and `prompts/examples_v2.2.json`. Each answer is copied
   from `data/human_labels.json` (or the file given with `--labels`), so it always equals the human label. It stops, writing nothing,
   if an example is a test article, is chosen twice, loses an evidence quote to trimming, or the
   useful / not-useful mix is uneven. It prints the example count and the prompt size.
2. If the file names changed, update the two paths in `config.py`.
3. The examples file must keep the fields listed in section 3. Its `article_id` values decide
   which articles are never scored, so changing the examples changes the excluded articles
   automatically. Take examples from dev only; a test article among them blocks the final test run.
4. Try `python run_extraction.py --limit 1` first, then a full run.

Two things to know:
- `run_config.json` in each run folder records the **file names** used, not their contents. If you
  edit a file without renaming it, older runs can no longer be traced to the exact text. Keep each
  version in `prompt_versions/`.
- The model's replies vary a little from run to run even at `temperature=0` (the same article gave
  different items on two runs). A small change in a score between two prompt versions may be noise;
  compare on the full set.

## 7. Which articles are run

Without `--ids`, a run covers every article of one split (`--split`, default `dev`) except:
- the articles whose solved answers are inside the prompt (the `article_id` values of the examples
  file; scoring them would be cheating, because the model has seen their answers),
- articles in `--exclude-file`, if given.

| Split | Articles | Useful | What it is for |
|---|---|---|---|
| dev | 397 | 106 | tuning: read the errors, change the prompt, pick examples |
| test | 803 | 207 | the final score: run once, after tuning, and do not tune on what it shows |

Both splits keep the natural share of useful articles (about 26%), so precision on test means what
it will mean on real news. For prompts v2.1 and v2.2 a dev run covers **373 articles (94 useful)**: its 24
examples are left out. (For v2.0 it was 383 articles, without its 14 dev examples.)

`--ids` bypasses the exclusions and runs exactly the articles named. Test articles, whether from
`--split test` or named in `--ids`, need `--final`. Even with `--final`, the run stops if any
prompt example is a test article, because the model would have seen that answer. Prompt v2.0 has
29 test articles among its 43 examples, so it can be scored on dev but never on test. The final
test score must come from a prompt (v2.1 or later) whose examples all come from dev.

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

**Strain names.** The rulebook writes the strain as the article names it and matches names up when
scoring. `STRAIN_SYNONYMS` in `metrics.py` maps a few names to one spelling before comparing:
"swine flu", "2009 H1N1" and "influenza A/H1pdm" count as "H1N1"; "bird flu", "bird flue" and
"avian influenza" count as "avian flu"; "A(H5N2)" counts as "H5N2". Subtype codes such as H5N1 are
never merged with "bird flu", because the rulebook asks for the code when the article gives both.

## 9. Automatic checks

Reply format errors make an article `malformed` (not scored): missing keys, `useful` not true/false,
a kind other than the four, an invalid date, a place that is not text or null, evidence that is
not a non-empty list of text. Rule violations do **not** stop an article from
being scored; they are reported so you can read those articles with care:

| Rule | Check |
|---|---|
| (a) | every evidence quote is an exact piece of the article |
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
- The 83 distinct place values in Jahnavi's labels and the prompt examples were all found. The four
  sheets hold 183 distinct place values, and about 100 of them are not saved yet, so the first full
  evaluation looks them up online (roughly two minutes).

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
| `report.md` | section 1 usefulness; 2 item correctness (2.1 exact, 2.2 item sets, 2.3 looser); 3 rule checks, with the evidence summary; 4 coverage (articles not scored and why) |
| `row_results.csv` | per article: `article_id`, `labeler`, `split`, `status`, human and model usefulness, `borderline`, `human_items`, `model_items`, `items_exact_matched`, `items_missing`, `items_extra`, `item_set_outcome`, `rule_violations`, `problems`, the model's `reason` |
| `item_comparison.csv` | one line per item, with `article_id`, `labeler` and `split`. `outcome`: `exact match`, `same kind and place` (not exact; `differing_fields` names what differs), `missing from model` (human item only) or `extra from model` (model item only). Shared columns: kind, strain, city, state, country. Side by side (`human_…`, `model_…`): number, status, total_or_new, start_date, end_date, words, evidence |

Read `report.md` in this order: section 4 (how many articles could not be scored), section 3 (rule
violations), section 1 (usefulness), section 2 (items). Then open `item_comparison.csv` or
`inspect_row.py` to see why items fail.

## 11. Testing

```bash
python -m unittest discover tests
```

Needs no API key and no internet (the place check uses a fake geocoder).

| File | Covers |
|---|---|
| `tests/test_checks.py` | rule (a) exact-quote check, shape errors, `findings` no longer required |
| `tests/test_metrics.py` | exact item matching, strain names, the six item-set outcomes, F1 and the usefulness table |
| `tests/test_places.py` | the place cache, offline mode, an unreachable service, rule (d) |
| `tests/test_evaluation.py` | which articles a run covers, the guard on test articles, `--ids` parsing |
| `tests/test_build_prompt_files.py` | trimming, and the checks on a prompt version's examples |
| `tests/test_build_data_files.py` | reading the four sheets (owner rows only, both `\|\|` styles) and every data check |
| `tests/test_second_label_set.py` | `PROMPT_VERSION` / `HUMAN_LABELS_PATH`, the run-settings guard, a second label set's data build, example answers from another labels file |
| `tests/test_pacing.py` | the calls-per-minute window, the shared pause after a 429, giving up, and retries of server errors |

Not covered by tests: the live API call, `report.py`, and the command-line scripts. Check those by
running a single article (section 1) and reading it with `inspect_row.py`.

## 12. Layout

```
prompts/           ACTIVE prompt: system prompt (.txt) and solved examples (.json)
prompt_versions/   the full prompt documents (v1.0, v2.0, v2.1, v2.2, and v4.1 for Jahnavi's track) and each version's example selection
data/              articles.json, human_labels.json (1,200 each, tagged dev or test), human_labels_jahnavi.json, place_lookups.json
results/           one folder per run (ignored by git)
scripts/
  build_data_files.py   refresh data/ from repo-sampling (prompts/ only with --with-prompts)
  build_prompt_files.py build prompts/ for one prompt version from prompt_versions/
tests/             unit tests (section 11)
flu_extractor/
  config.py        paths and model settings
  data_loading.py  read articles and human labels
  prompt.py        build the chat messages (system prompt, example turns, article)
  llm_client.py    the only code that calls the model API
  pacing.py        keeps the run under the rate limit (calls per minute, shared pause after a 429)
  extractor.py     one article -> one log record (parsing the reply, never crashing)
  checks.py        reply format check and the automatic rule checks
  places.py        asks the geocoder whether a city/state/country exists; saves the answers
  metrics.py       precision/recall/F1, usefulness scoring, item matching, item-set outcomes
  evaluation.py    score a whole run against the labels; choose the default articles
  report.py        write report.md and the two CSV files
run_extraction.py  command-line tool: ask the model
evaluate_run.py    command-line tool: score a run
inspect_row.py     command-line tool: one article (by ID), human vs model, field by field
```

## 13. Known limitations

- **Dev scores are optimistic.** The prompt is tuned by reading dev errors, so dev scores rise
  partly because of that. Report the one-time test score. Prompt v2.0 cannot have one (section 7).
- **Run-to-run variation.** The hosted model does not return identical output for identical input,
  even at `temperature=0`. One run is a noisy measurement.
- **Examples are sent as chat turns.** The v2.0 prompt document allows this, or pasting the examples
  as text inside the system message. Runs made in the text form (the earliest smoke tests) are not
  directly comparable.
- **Date convention (review these articles by hand).** The prompt dates articles by scan date; the human
  sheets prefer the printed date, then the link date, then the scan date. For an article published
  before the day it was scanned, relative dates ("yesterday", "on Tuesday") are counted from
  different days, so item dates can differ for that reason alone. The code treats these articles
  like any other; check the dates first when an item differs only in them.
- **Invalid JSON.** The model can put an unescaped `"` inside an evidence string, which breaks the
  JSON (seen once, before the chat-turn layout). Such articles are reported as not scored. Structured
  output, as the prompt document suggests, is the planned fix; it has not been tried.
- **Exact matching is demanding on `words`.** For trend items the human `words` is sometimes a short
  summary and sometimes a quote (the prompt notes 9 of 64 are summaries), and a model can phrase it
  differently. Such items count as missing and extra even when they describe the same thing; see
  `differing_fields` in `item_comparison.csv`. To ignore more than case and repeated spaces, edit
  `_normalise` in `flu_extractor/metrics.py`.
- **Garbled characters.** 49 of the 1,200 articles contain broken characters such as `â`. The prompt tells
  the model to copy evidence "as printed", so this is expected, not a bug in this code.
- **Cost and speed.** A full dev run with prompt v2.1 is 373 calls of about 19,000-22,000 prompt tokens each (v2.0 sent about 28,000-30,000). Measured on 2026-10-19 with 24 dev articles and `--workers 6`: no rate-limit, timeout or server errors, 1-24 s per call (mean 4 s), 33 s for all 24. A full dev run should take about 5-10 minutes, so Nemotron stays the model; DeepSeek V4 Flash is the fallback if limits appear. Later the same day the key returned 429 after 10-15 calls, even with one worker, and the server sends no rate-limit headers; runs are now paced (section 2, Pacing), which makes a dev run take about 40 minutes at 10 calls per minute. Hosted
  API quotas and latency are not guaranteed.
