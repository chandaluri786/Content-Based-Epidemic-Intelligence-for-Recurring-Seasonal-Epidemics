# Flu news LLM extractor

Runs a large language model over human-influenza news articles, extracts structured
findings with **prompt v5.1**, and scores the result against the chain-of-thought gold records.
For each article the model says:

- whether the article is **useful** (does it report current human flu activity in a real place?), and
- the **items** it reports: `cases`, `hospitalized`, `deaths` or `trend`, with number, count type,
  status, strain, place, dates, trend word and the quoted evidence.

The model is **NVIDIA Nemotron 3.5 Lightning 30B-A3B**, called through NVIDIA's hosted,
OpenAI-compatible API. The prompt is the v5.1 rules as a system message, plus optional solved
examples sent as chat turns (few-shot). Everything the extractor reads is inside this folder
(`prompts/` and `data/`), so it does not depend on where the capstone files are on disk.

The plan this code follows is in
[HANDOFF_thanya_evaluation_fewshot.md](HANDOFF_thanya_evaluation_fewshot.md), Sections 3-5.

## Contents

1. [Status and what comes next](#1-status-and-what-comes-next)
2. [Quick start](#2-quick-start)
3. [How it works](#3-how-it-works)
4. [Data formats](#4-data-formats)
5. [Commands](#5-commands)
6. [Configuration](#6-configuration)
7. [Prompt versions](#7-prompt-versions)
8. [Which articles are run: one set](#8-which-articles-are-run-one-set)
9. [Choosing the few-shot examples](#9-choosing-the-few-shot-examples)
10. [How results are scored](#10-how-results-are-scored)
11. [Automatic checks](#11-automatic-checks)
12. [Output files](#12-output-files)
13. [Testing](#13-testing)
14. [Layout](#14-layout)
15. [Known limitations](#15-known-limitations)

---

## 1. Status and what comes next

**Done in code (handoff Section 3):**

- Everything is keyed by `article_id`, because row numbers collide across the four labeling
  sets (row 41 is four different articles). The 1,280 rows give 1,200 unique articles.
- `scripts/build_gold_files.py` reads all four sets and writes `data/articles.json` (with `split`
  and `passes_keyword_gate`), `data/gold_labels.json`, `data/human_labels.json`, and the v5.1
  system prompt.
- The request uses the v5.1 rules and the v5 input names (`scan_date`, `link`, `article`).
  `MAX_TOKENS` is 8000.
- The keyword gate (Rule 1) runs in code: an article that fails it gets the exact Rule 1 reply and
  no API call.
- The checks follow the v5 schema (`summary`, `reasoning`, `useful`, `reason`, `items`; 12 item
  fields; `count_type`). The old overlap rule is gone, because G5 requires overlapping counts.
- Scoring has exact, strict, relaxed and weekly tiers, agreement by field, scores by country,
  with/without gated and inactive-only articles, 95% bootstrap intervals by article, and a
  `useful` comparison against the human labels.
- `run_config.json` stores SHA-256 hashes of the prompt and examples files, so a run can be
  traced to the exact text it used.
- 99 unit tests pass, with no API calls and no internet.

**Done with the data (2026-11-02):**

- `data/` is built from the three dev record files in `../labeled_data_chain_of_thought/` (960
  records, 920 unique articles) and the article texts. All 1,397 gold evidence quotes were found
  word for word in the article texts.
- **Every article that appears in more than one labeling set is removed** (80 articles: the 40
  double-labelled dev articles, 20 Jahnavi/Aditya and 20 Aditya/Manoj, and the 40 dev articles
  repeated as Thanya rows 1-40). That leaves **840 dev articles: 240 useful, 600 not useful**
  (280 per labeler: Jahnavi 81 useful, Aditya 71, Manoj 88), and 280 test articles with no gold yet.
- **One set, no dev/test split.** Runs score every labelled article except the 8 few-shot
  examples: **832 articles (235 useful, 597 not useful)**, 44 of them decided by the keyword gate.
  The `split` field is kept in the data for reference only.
- **Few-shot, favouring hard cases.** The 8 active examples (section 9) are the records the labelers
  marked `hard_case` and articles the model got wrong in earlier runs, still covering all 12 slots
  and all three labeled sets. None is a shared article.
- **Every reply is validated** (section 3): repaired if only stray quotes break the JSON, otherwise
  asked again with a note naming the problem, up to 2 times.
- The dev sample D (`data/dev_sample_200.txt`, now 181 articles) was used only for the first
  zero-shot and few-shot comparison (`results/run_k0_D`, `results/run_k8_D`).

**Still to do, in this order:**

| # | Step | Who / where |
|---|---|---|
| 1 | NVIDIA API key in `llm-extractor/.env` (done 2026-11-02) | key holder |
| 2 | One-article smoke run (done 2026-11-02: exact match, 2 of 2 items) | section 2 below |
| 3 | Zero-shot and first few-shot runs on D (done 2026-11-02: `results/run_k0_D`, `results/run_k8_D`) | section 9 |
| 4 | Few-shot run on all 832 articles with the hard-case examples (done 2026-11-02: `results/run_full_k8`; `useful` F1 81.0%, per-article partial-credit F1 30.7%) | section 8 |
| 5 | Decide whether the headline keeps or filters inactive-only articles | section 10 |
| 6 | Thanya's chain-of-thought records, if her 280 articles should be scored too, then rebuild `data/` | handoff Section 2 |
| 7 | Run-to-run variation measured on 60 articles (done: large, see section 3); decide on voting over repeated runs | section 3 |

The human `useful` answers in `data/human_labels.json` come from older copies of the label sheets
(blank for Jahnavi, Aditya and Thanya). Rebuild with the current sheets (`--labeling-dir`) before
reporting the human comparison.

## 2. Quick start

Requirements: Python 3.11 or newer (tested on 3.12.3 on Linux and 3.11.9 on Windows), an NVIDIA
API key with access to the model (https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b),
and internet access.

```bash
# one-time setup
cd llm-extractor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env          # then edit .env and put your key after NVIDIA_API_KEY=
chmod 600 .env                # only you can read it

# once, and whenever the labels change (needs the capstone labeling folder)
python scripts/build_gold_files.py

# every session: activate the environment, then
python -m unittest discover tests                            # 1. the logic works (no API, no internet)
python run_extraction.py --ids Jahnavi:6                     # 2. ONE API call; prints the run folder
python inspect_row.py results/run_<timestamp> Jahnavi:6 --reasoning   # 3. read the reply
python run_extraction.py --ids-file data/dev_sample_200.txt  # 4. few-shot (k = 8) on D (~190 calls, at least 5 min)
python evaluate_run.py results/run_<timestamp>               # 5. score it, then read report.md
```

`data/dev_sample_200.txt` is already drawn (`scripts/make_dev_sample.py` refuses to redraw it).

All commands run from the `llm-extractor` folder with the virtual environment active.
The API key is read from `.env` and never printed.

## 3. How it works

```
 prompts/system_prompt_v5.1.txt ─┐
 prompts/examples_v5.1.json ─────┼─► run_extraction.py ─► results/run_<time>/raw_results.jsonl
 data/articles.json ─────────────┘   (keyword gate in code;   (one line per article: reply,
                                      one API call for each    tokens, timing, errors)
                                      article that passes)               │
 data/gold_labels.json ──────────────────────────────────────────────────┼─► evaluate_run.py ─► report.md
 data/human_labels.json (useful only, a second comparison) ──────────────┤                      scores.json
 data/place_lookups.json (saved place answers; geocoder if new) ─────────┘                      row_results.csv
                                                                                                item_comparison.csv
```

The two steps are separate on purpose: scoring can be repeated, or changed, without paying for
new model calls.

### Step 1: `run_extraction.py` (calls the model)

| # | Function (module) | Input | Output |
|---|---|---|---|
| 1 | `load_articles` (`data_loading.py`) | `data/articles.json` | `{article_id: Article}` |
| 2 | `load_gold_labels` (`data_loading.py`) | `data/gold_labels.json` | `{article_id: GoldLabel}` |
| 3 | `load_examples` (`prompt.py`) | the examples JSON file | list of example dicts |
| 4 | `default_articles_to_run` (`evaluation.py`), or `--ids` / `--ids-file` | split, example ids, exclusions | sorted list of article ids |
| 5 | `ids_already_done` | an existing `raw_results.jsonl` (when resuming) | ids to skip |
| 6 | `load_system_prompt`, `build_prefix_messages` (`prompt.py`) | system prompt file, examples | the shared part of every request |
| 7 | `create_client` (`llm_client.py`) | settings from `config.py` and the API key | an `OpenAI` client |

Then, for each article (up to `--workers` at the same time), `extract_article` (`extractor.py`):

| # | Function | Input | Output |
|---|---|---|---|
| a | keyword gate | `Article.passes_keyword_gate` | if false: the Rule 1 reply, no API call, `gated: true` |
| b | `build_messages` (`prompt.py`) | the shared messages and one `Article` | the full list of chat messages |
| c | `ask_model` (`llm_client.py`) | client, messages | `ModelReply`: text, finish reason, token counts, seconds |
| d | `parse_reply` (`extractor.py`) | the reply text | the reply as a dict, or an error message |

The record is appended to `raw_results.jsonl` as soon as it is done. A failed call never stops
the run: the error is stored in the record.

**The keyword gate.** v5.1 Rule 1 tells the model the flu keyword check has already happened, so
it must happen in code. `build_gold_files.py` runs `is_flu_related` from
`../flu_bucketing/flu_keywords.py` on each article and stores `passes_keyword_gate`. A failing
article gets the Rule 1 reply from `extractor.RULE_1_REPLY` (`useful: false`, no items).

**What the model receives.** One request is a list of chat messages:

1. a `system` message: the v5.1 rules (`system_prompt_v5.1.txt`), followed, **only when examples
   are sent**, by the few-shot guide (`fewshot_guide_v5.1.txt`, section 9);
2. for each solved example, a `user` message with the example article, then an `assistant`
   message with the answer as JSON (`summary`, `reasoning`, `useful`, `reason`, `items`);
3. a final `user` message with the article to process.

Every article block, in the examples and for the real article, uses the input names of the v5.1
prompt (`format_article` in `prompt.py`):

```
scan_date: 2016-12-30
link: http://cbs6albany.com/news/local/...
article:
<article text>
```

The messages in 1 and 2 are the same for every article and are built once per run. The GDELT
header lines of the labeling files (tagged country, places mentioned) are never sent; the
prompt forbids using them (5.6).

**Model call settings** (`llm_client.py`, values in `config.py`): `temperature=0`,
`max_tokens=8000` (the longest gold reply is 15,683 characters, roughly 4,000-5,000 tokens),
`extra_body` with `enable_thinking: False` (v5 puts its reasoning inside the JSON reply), a
300 s timeout, and up to 4 retries on rate-limit (429), timeout, connection and server (5xx)
errors, waiting for the server's `Retry-After` if it sends one, otherwise 5, 10, 20, 40 s. Other
errors (for example a request over the context limit) are not retried.

**Rate limit: 40 requests per minute.** The API allows 40 requests per minute, and every request
counts, retries included. One `RateLimiter` (`llm_client.py`) is shared by all worker threads:
before any request, including a retry, it waits until fewer than 40 requests have started in the
last 61 seconds (one second of margin for clock differences). The OpenAI library's own retries are
switched off (`max_retries=0`), because they would bypass the limiter. So the limit holds for any
`--workers` value, and a 200-article run takes at least 5 minutes. Change it with
`NVIDIA_REQUESTS_PER_MINUTE` in `.env`.

**Every reply is validated before it is accepted** (`extractor.py`). A reply is accepted only if
it is complete (not cut off at `max_tokens`), parses as one JSON object, and passes the reply format
check (`find_shape_errors`). Otherwise:

1. **Repair.** The usual break is an article quotation copied with its double quotes unescaped
   (`"pension spiking"` inside a JSON string). `repair_json_strings` escapes a double quote that
   cannot end a string (the next character is not `,` `:` `}` `]`) and raw line breaks inside
   strings. Nothing else is changed, so evidence still matches the article. The record notes
   `repaired: true`.
2. **Ask again.** If repair is not enough, or the reply was cut off or malformed, the article is sent
   again with a short note after it naming the problem (for example "your previous reply was not
   valid JSON (...). Inside every JSON string, write a double quote as \""). Up to
   `MAX_VALIDATION_RETRIES` = 3 times; every request goes through the rate limiter. The record keeps
   `validation_retries` and `validation_problems`.
3. **Last attempt, compact.** Re-asking at temperature 0 tends to repeat the same mistake, so the
   last attempt asks for a compact reply (at most 12 reasoning steps, no article text inside
   `reasoning`, article text only in `evidence`) at `LAST_RETRY_TEMPERATURE` = 0.3.
4. Only if all 4 replies are invalid is the article reported as unparseable or malformed (the
   record's `invalid` field says why). `--retry-invalid` reruns such articles when resuming.

In the full run (832 articles, `results/run_full_k8`) **every article ended with a valid reply**:
48 replies were valid only after quote repair, 37 articles were asked again, and the remaining few
were completed with `--retry-invalid`.

**Why not the API's JSON mode.** `response_format={"type": "json_object"}` is accepted, but in a
test it turned an unescaped quote into a reply that filled the rest of the 8,000 tokens with blank
lines (the decoder closes the string at the quote and allows only whitespace after it). Repair plus
re-asking fixed the same articles without that cost, so JSON mode is not used.

**Repeatability.** `temperature=0` and a fixed `seed` (`SEED` in `config.py`) are sent with every
request, but they do **not** make this hosted model repeatable. Measured on 60 articles sent twice
(`results/run_repeat60`): the reply text was identical for 1 of 53 compared articles, the `useful`
answer flipped for 4 of 53, and among the 17 articles with items the item lists were identical for
1. Two identical requests with `top_p` = 1e-6 as well still differed from the first sentence. The
variation is on the server side (a mixture-of-experts model batched with other requests); no
request setting removes it. Reduce it by voting over repeated runs, or use a model served with
deterministic decoding.

**Quota stop.** The free key has a daily quota. After `STOP_AFTER_CONSECUTIVE_API_ERRORS` = 5 API
failures in a row, the run stops instead of failing every remaining article. Finished work is kept;
resume with `python run_extraction.py --run-dir results/<run>`.

**Request size.** The v5.1 rules are about 66,000 characters (roughly 16,500 tokens at 4
characters per token). Each example adds roughly 1,500 tokens. The longest article adds about
35,000 more. Articles are never cut: a request over the model's context limit fails and is
reported as an API error (unscored). Check the model's limit before the first full run.

### Step 2: `evaluate_run.py` (scores a run)

| # | Function | Input | Output |
|---|---|---|---|
| 1 | `read_run_records` (`evaluation.py`) | `raw_results.jsonl` | `{article_id: record}` (a later line replaces an earlier one) |
| 2 | `load_articles`, `load_gold_labels`, `load_human_useful` | the data files | as above |
| 3 | `PlaceChecker(cache, offline)` (`places.py`) | `data/place_lookups.json`, `--offline` | the place checker |
| 4 | `evaluate_run` (`evaluation.py`) | records, articles, gold, human answers, place checker | an `Evaluation` |
| 5 | `write_report` (`report.py`) | the `Evaluation`, the run folder | `report.md`, `scores.json`, two CSV files |

Each record with a gold label gets a **status**:

| Status | Meaning |
|---|---|
| `api_error` | the call failed after all retries, or with an error a retry cannot fix (e.g. a request over the context limit) |
| `unparseable` | the reply was not valid JSON, or was cut off at `max_tokens` |
| `malformed` | valid JSON that breaks the reply format (`find_shape_errors`) |
| `scored` | everything is fine; the row enters the numbers |

Rows that are not `scored` are left out of every score and listed in section 4 of `report.md`.

## 4. Data formats

All four files in `data/` are written by `scripts/build_gold_files.py`.

**`data/articles.json`**: one object per article (1,120: 840 dev and 280 test; the 80 articles in more than one labeling set are removed).

```json
{"article_id": "20161230170000-2179", "scan_date": "2016-12-30",
 "link": "http://cbs6albany.com/news/local/influenza-forcing-ny-hospitals-to-adjust-visitation-rules",
 "split": "dev", "passes_keyword_gate": true, "sources": ["Jahnavi:6"],
 "article": "Influenza forcing NY hospitals to adjust visitation rules\nALBANY, N.Y. (AP) -- ..."}
```

`sources` gives the labeling set and row of the article (the 80 articles that appeared in two
sets are removed by default; `build_gold_files.py --keep-shared` keeps one copy of each). `split` is `dev` or `test` (section 8). `scan_date` is the day GDELT collected the
article; the prompt treats it as the publication date.

**`data/gold_labels.json`**: one object per article that has a chain-of-thought record, taken
from `<Name>_chain_of_thought_v2.jsonl`. When an article is in two sets, both records must agree,
or the build stops.

```json
{"article_id": "20161230170000-2179", "split": "dev", "useful": true, "labelers": ["Jahnavi"],
 "items": [{"kind": "hospitalized", "number": 658, "count_type": "cumulative_region",
            "status": "confirmed", "strain": null, "city": null, "state": "New York",
            "country": "USA", "start_date": null, "end_date": "2016-12-30", "words": null,
            "evidence": ["Some 658 flu-related hospitalizations in New York have been reported so far this flu season."]}]}
```

**`data/human_labels.json`**: the labelers' own `useful` answers, kept as a second comparison.

```json
{"article_id": "20161230170000-2179", "useful": true, "by_labeler": {"Jahnavi": true}}
```

`useful` is null when the sheet has no answer, or when two labelers of an overlap article disagree.

**The model's reply** (one JSON object; defined in the v5.1 prompt, "Your reply" and 2.1-2.2):

```json
{"summary": "one line about the article",
 "reasoning": ["Step 0 (summary): ...", "Step 1 (Rule 1): ...", "Step 2 (2.3, 4.3, 5.3): ..."],
 "useful": true, "reason": "one short sentence",
 "items": [{"kind": "trend", "number": null, "count_type": null, "status": null, "strain": null,
            "city": null, "state": "New York", "country": "USA",
            "start_date": "2016-12-30", "end_date": "2016-12-30",
            "words": "high", "evidence": ["exact quote from the article"]}]}
```

| Field | Meaning |
|---|---|
| `kind` | `cases`, `hospitalized`, `deaths` or `trend` |
| `number` | whole number of people; counts only |
| `count_type` | `new`, `cumulative_region` or `cumulative_subset`; counts only |
| `status` | `confirmed` or `suspected`; counts only |
| `strain` | e.g. `H1N1`, `influenza A`, `avian influenza`; null when none is named |
| `city`, `state`, `country` | where the event happened; country is required (G1) |
| `start_date`, `end_date` | `YYYY-MM-DD`; end date required (G2), within the 30 days ending on the scan date (4.7) |
| `words` | trends only: one of `rising`, `falling`, `high`, `moderate`, `low`, `inactive`, `present` |
| `evidence` | non-empty list of exact quotes; the sentence stating the event first, then article order |

**Solved examples** (`prompts/examples_v5.1.json`): a list. Each entry:

```json
{"article_id": "...", "source": "Jahnavi:47", "slots": [6, 7, 10], "scan_date": "...", "link": "...",
 "article": "...",
 "answer": {"summary": "...", "reasoning": ["Step 0 ...", "..."], "useful": true, "reason": "...", "items": []}}
```

Only `scan_date`, `link`, `article` and `answer` are sent. `answer` comes straight from the gold
record, with `rules_used`, `hard_case` and `source_rows` left out. `article_id` decides which
articles are never scored. **The extractor runs few-shot**: the active file holds the k = 8 set
(a copy of `examples_v5.1_k8.json`); `examples_v5.1_k4.json` and `_k12.json` are the other sizes.

**One log line** (`raw_results.jsonl`):

```json
{"article_id": "...", "model": "nvidia/nemotron-3.5-lightning-30b-a3b", "gated": false,
 "finish_reason": "stop", "prompt_tokens": 17012, "completion_tokens": 1450, "seconds": 21.4, "attempts": 1,
 "raw_reply": "{\"summary\": ...}", "parsed": {...the reply as an object...},
 "parse_error": null, "api_error": null}
```

`finish_reason` is `stop` when the model finished and `length` when it hit `max_tokens` (the
reply is then incomplete and is not parsed). `attempts` is the number of requests sent for this
reply (more than 1 after a retry); `seconds` includes rate-limit waits and retries. For a gated
article, `gated` is true, `parsed` is the Rule 1 reply and the call fields are null.

**`data/place_lookups.json`**: saved answers of the place check. Key `"city: allahabad"`, value
`{"found": true, "top_match": "Prayagraj, Allahabad, ...", "checked_on": "2026-10-18"}`.

## 5. Commands

Articles can be named by `article_id` or by set position, such as `Jahnavi:6` or `Thanya:120`.

### `run_extraction.py`: ask the model

| Option | Meaning |
|---|---|
| `--ids Jahnavi:6,Manoj:12` | run exactly these articles, bypassing the split and all exclusions |
| `--ids-file FILE` | run the articles listed in FILE, one per line (`#` starts a comment), e.g. `data/dev_sample_200.txt`. Example articles are still left out |
| `--split all\|dev\|test` | articles to run when no ids are given (default `all`: every labelled article as one set) |
| `--limit N` | run only the first N of the selected articles |
| `--exclude-file FILE` | extra articles to leave out, one per line |
| `--workers N` | requests in flight at the same time (default 3). The 40-per-minute limit holds whatever N is |
| `--run-dir DIR` | continue an existing run folder: articles that already have a reply are skipped |
| `--retry-invalid` | with `--run-dir`: also rerun articles whose reply was still invalid after the retries |

Each run writes a new folder `results/run_<date>_<time>/`. With `--run-dir`, only articles whose
call **failed with an API error** are retried. Invalid replies are already repaired or asked again
during the run (section 3); one that is still invalid after that counts as done: to retry it,
delete its line from `raw_results.jsonl`. Records are written in the order they finish.

### `evaluate_run.py RUN_DIR`: score a run

| Option | Meaning |
|---|---|
| `--offline` | do not look up place names online; use only the saved answers. Names never looked up are reported as "could not be checked" |

Writes `report.md`, `scores.json`, `row_results.csv` and `item_comparison.csv` into the run
folder, and prints a short summary. New place names are looked up online, about one per second,
and saved.

### `inspect_row.py RUN_DIR ARTICLE`: one article, gold vs model, field by field

| Option | Meaning |
|---|---|
| `--article` | also print the article text |
| `--reasoning` | also print the model's summary and reasoning steps |
| `--offline` | do not look up place names online |

Prints the call details, the usefulness verdict (gold vs model, with the human label), and every
item with **all** its fields, gold and model side by side, each flagged `same` or `DIFFERENT`.
Items are labeled `EXACT MATCH`, `NOT EXACT` (same kind and place, with the differing fields
named), `MISSING FROM MODEL` or `EXTRA FROM MODEL`, followed by any rule violations. It uses the
same scoring code as the reports.

### `compare_runs.py RUN_DIR...`: scores of several runs side by side

```bash
python compare_runs.py results/run_k0_D results/run_k4 results/run_k8 results/run_k12
python compare_runs.py results/run_test1 results/run_test2 results/run_test3   # mean and range
```

Reads each folder's `scores.json` and `run_config.json` and prints k (example count), the examples
hash, and usefulness, exact, strict, relaxed and weekly F1, then the mean and range of each.
`--variant all_articles` or `--variant without_inactive` compares the other score sets.

### `scripts/build_gold_files.py`: refresh `data/` and the system prompt

```bash
python scripts/build_gold_files.py                                  # default capstone layout
python scripts/build_gold_files.py --capstone-dir /path/to/capstone
python scripts/build_gold_files.py --labeling-dir DIR --records-dir DIR
```

Defaults: the capstone folder is two levels up, the labeling files are in
`<capstone>/labeling/labeling/`, the records in `data/chain_of_thought/` if it exists, else in
`../labeled_data_chain_of_thought/`. It reads all four
`<Name>_texts.txt`, `<Name>_labels.csv` and `<Name>_chain_of_thought_v2.jsonl` (a missing or
partial records file is fine: those articles get no gold yet). It stops with an error if an
article is in both splits, or if two copies of an article or of its record differ. It also
rewrites `prompts/system_prompt_v5.1.txt` from the v5.1 document, and creates
`prompts/examples_v5.1.json` as `[]` only if it does not exist. It prints article, gate and gold
counts per split. It is the only code that knows where the capstone folder is.

### `scripts/make_dev_sample.py`: draw the dev sample D

Draws 200 dev articles with gold, stratified by labeler and gold `useful`, seed 20261101, and
writes them to `data/dev_sample_200.txt`. It refuses to overwrite an existing file, because D
must stay identical across the runs it compares.

### `scripts/select_examples.py`: choose the few-shot candidates

```bash
python scripts/select_examples.py [--records-dir DIR]
```

Builds the candidate pool from the three dev record files and picks 12 nested candidates (section
9). Writes `prompts/examples_v5.1_k4.json`, `_k8.json`, `_k12.json` and the review sheet
`few_shot_selection.md`. It never touches the active `prompts/examples_v5.1.json`. Deterministic:
the same records give the same picks.

`scripts/build_data_files.py` is the old v2.0 converter. It is obsolete: it writes the old row-keyed
format the code no longer reads. Do not run it.

## 6. Configuration

Secrets and overrides go in `.env` (copy `.env.example`). Everything else is in
`flu_extractor/config.py`.

| Setting | Where | Default |
|---|---|---|
| `NVIDIA_API_KEY` | `.env` (required) | none |
| `NVIDIA_MODEL_ID` | `.env` (optional) | `nvidia/nemotron-3.5-lightning-30b-a3b` |
| `NVIDIA_BASE_URL` | `.env` (optional) | `https://integrate.api.nvidia.com/v1` |
| `RESULTS_DIR` | `.env` (optional) | `llm-extractor/results` |
| `EXAMPLES_PATH` | `.env` (optional) | `prompts/examples_v5.1.json`; set to e.g. `prompts/examples_v5.1_k8.json` for the k comparison |
| `SYSTEM_PROMPT_PATH`, `FEWSHOT_GUIDE_PATH` | `config.py` | `prompts/system_prompt_v5.1.txt`, `prompts/fewshot_guide_v5.1.txt` |
| `ARTICLES_PATH`, `GOLD_LABELS_PATH`, `HUMAN_LABELS_PATH` | `config.py` | `data/articles.json`, `data/gold_labels.json`, `data/human_labels.json` |
| `DEV_SAMPLE_PATH`, `PLACE_CACHE_PATH` | `config.py` | `data/dev_sample_200.txt`, `data/place_lookups.json` |
| `TEMPERATURE`, `MAX_TOKENS` | `config.py` | 0, 8000 |
| `NVIDIA_REQUESTS_PER_MINUTE` | `.env` (optional) | 40 (every request and retry counts; window 61 s, `RATE_WINDOW_SECONDS`) |
| `REQUEST_TIMEOUT_SECONDS`, `MAX_RETRIES` | `config.py` | 300, 4 |
| `MAX_VALIDATION_RETRIES`, `LAST_RETRY_TEMPERATURE` | `config.py` | 3, 0.3 (requests repeated when a reply is cut off, not valid JSON or malformed; the last one compact, at 0.3) |
| `SEED` | `config.py` | 20261101 (sent with every request, with `TEMPERATURE` 0) |
| `STOP_AFTER_CONSECUTIVE_API_ERRORS` | `config.py` | 5 (stop a run when the quota is used up) |
| `EXTRA_BODY` | `config.py` | `{"chat_template_kwargs": {"enable_thinking": False}}` |

Other tuning points: the place check pace and retries are at the top of `flu_extractor/places.py`;
the item matching tiers are at the top of `flu_extractor/metrics.py`; the recency window
(`RECENT_DAYS = 30`) is in `flu_extractor/checks.py`.

## 7. Prompt versions

**`prompts/` holds the files the code reads**, named in `config.py`:

| File | What it is |
|---|---|
| `prompts/system_prompt_v5.1.txt` | **active.** The v5.1 rules, from `## Task` to the end of `llm_extraction_prompt_v5.1.md`, word for word. Generated by `build_gold_files.py` |
| `prompts/examples_v5.1.json` | **active.** The few-shot examples: the k = 8 set (section 9) |
| `prompts/fewshot_guide_v5.1.txt` | **active.** How to learn from the examples' reasoning and evidence. Added after the rules only when examples are sent (section 9) |
| `prompts/examples_v5.1_k4.json`, `_k8.json`, `_k12.json` | candidate example sets for the k comparison, written by `select_examples.py`. Not active |
| `prompts/system_prompt_v2.0.txt`, `prompts/examples_v2.0.json` | the old v2.0 pair, kept as the record of the v2.0 runs. Old schema: do not reuse |

**`prompt_versions/` is the archive** of full prompt documents. No code reads it except
`build_gold_files.py`, which takes the system prompt from the v5.1 file.

| File | What it is |
|---|---|
| `llm_extraction_prompt_v1.0.md` | v1.0 (14 solved examples, old schema) |
| `llm_extraction_prompt_v2.0.md` | v2.0 (43 solved examples, old schema with `total_or_new`, `borderline`, `findings`) |
| `llm_extraction_prompt_v5.1.md` | **v5.1, the active version.** Generated from `prompt_rules.md` (rules version `prompt_rules 2026-11-01`). Rule numbers are the same as v5.0 |

The v5.1 document holds no examples: they go in chat turns, never pasted into the rules. The rule
text is unchanged; how to use the examples is in the separate guide file, which keeps the rules as
the authority. If the zero-shot run shows a repeated misreading of a rule, change the rule through
the normal protocol on dev data only, before the freeze, as a new version file.

**Freezing.** Before the test runs, the prompt, the guide, the examples, the model and the
settings are frozen. `run_config.json` in each run folder records the file names and their SHA-256
hashes, so every run can be traced to the exact text it used. All three test runs must show the
same hashes.

## 8. Which articles are run: one set

All labelled articles are one set; there is no dev/test split. Without `--ids` or `--ids-file`, a
run covers every article with a gold record except the few-shot examples (the model has seen their
answers) and articles in `--exclude-file`:

| | Useful | Not useful | Total |
|---|---|---|---|
| Labelled articles (no shared articles) | 240 | 600 | 840 |
| Few-shot examples, left out | 5 | 3 | 8 |
| **Scored** | **235** | **597** | **832** |

Gated articles (44) are included: they cost no API call, and the report scores them separately.
Thanya's 280 articles have no gold records yet, so they are not scored. The `split` field and
`--split dev|test` remain for running one part on its own.

```text
1. python -m unittest discover tests
2. python run_extraction.py --ids Jahnavi:6        one-article smoke run; read the reply
3. python run_extraction.py                        all 832 articles (about 790 API calls)
4. python evaluate_run.py results/run_<timestamp>
5. Repeat 3-4 to measure run-to-run variation; compare_runs.py gives the mean and range
```

## 9. Choosing the few-shot examples

The examples are chosen from the three labelled record files by `scripts/select_examples.py`, using
each record's `rules_used`, items and `hard_case`, and **favouring hard cases**. The 12 candidates
are listed, with why each is hard and up to 3 alternates per slot, in
[few_shot_selection.md](few_shot_selection.md).

### 9.1 How the examples were chosen

1. **No shared articles.** The 80 articles that appear in more than one labeling set are not in
   `data/` at all; the selection script also excludes them on its own.
2. **Candidate pool:** the whole labelled set (no split, no D). Left out: articles failing the
   keyword gate, articles over 6,000 characters (10,000 for a `hard_case` record), replies over
   5,000 characters, garbled text, and inactive-only records except for the food-link slot.
3. **Slots.** Each record is tagged with the slots below from its `rules_used` and items (e.g. slot
   6 = G4 or G5 with two or more counts; slot 12 = a `cumulative_subset` or `suspected` count).
4. **Hardness.** +2 for a `hard_case` note (a judgement call the labeler recorded), plus the share
   of the earlier runs (`run_k0_D`, `run_k8_D`) in which the model got the article wrong (wrong
   `useful`, or per-article partial-credit F1 under 50%).
5. **Greedy, nested pick.** Each pick adds the most new slots (10 points each), hardness (6 points
   per unit), rarely used rules, new countries and new kinds, minus about 1 point per 1,000 tokens.
   At every size the three labeled sets are all present and about one third are not useful.

**The active 8** (`prompts/examples_v5.1.json`), each hard:

| Example | Useful | Why it is hard |
|---|---|---|
| Jahnavi 83 | yes | items wrong in both earlier runs (Turkey, deaths and cases over a period) |
| Aditya 307 | yes | `hard_case`: a monitoring statement from a general CDC update |
| Jahnavi 311 | no | `useful` wrong in both earlier runs (H5N1 in livestock, no human item) |
| Manoj 79 | yes | items wrong in both earlier runs (infant deaths, Silchar) |
| Jahnavi 320 | no | `hard_case`: China's "normal flu" claim, which the letter rejects |
| Manoj 162 | yes | items wrong in an earlier run (present fallbacks for 7 countries) |
| Aditya 142 | yes | items wrong in both earlier runs (6 countries) |
| Manoj 60 | no | `useful` wrong in both earlier runs (Yanomami crisis) |

The third `hard_case` (Jahnavi 308) is example 9, in the k = 12 set.

| k | Slots covered | Rules covered (of 68 in the pool) | Not useful | Jahnavi / Aditya / Manoj | Extra tokens per call |
|---|---|---|---|---|---|
| 4 | 10 of 12 | 36 | 1 | 2 / 1 / 1 | ~7,400 |
| 8 | 12 of 12 | 40 | 3 | 3 / 2 / 3 | ~12,600 |
| 12 | 12 of 12 | 46 | 4 | 4 / 4 / 4 | ~17,300 |

| # | Slot | Rules | Kind of example |
|---|---|---|---|
| 1 | Flu named, but no current activity | 1.2, 9.5 | routine vaccine advice or company news, no item |
| 2 | Flu in animals only | 1.3 | poultry outbreak, no item |
| 3 | Past or forecast | 4.1, 4.7, 9.3.8 | old total or a coming season, no item |
| 4 | Food link fallback | 1.3, 9.7 | price rise gives inactive |
| 5 | Stages for one person | 2.4, 4.3 | case, admission, death on stated days |
| 6 | Overlapping counts | G4, G5 | a total plus a weekly count, the same event told twice |
| 7 | Count and trend together | 2.3, 9.3 | "rising" plus a number |
| 8 | Fallback present, per place | 9.3.5, 9.7 | several places, no level word |
| 9 | Trend with a strain | 9.6 | general plus dominant strain gives two items |
| 10 | Place from context | 5.3.6, 5.4, 5.5 | no place in the sentence, home area vs hospital |
| 11 | Relative dates | 4.3-4.6 | weekday, "past week", "since X" |
| 12 | Subset vs region, suspected | 6.3, 7.2 | a school outbreak, pending samples |

### 9.2 How many examples

**Active: k = 8.** The extractor always runs few-shot. k = 8 is the smallest set that covers all 12
slots, with 3 of 8 not useful, for about 12,600 extra tokens per call (the whole prefix is then
about 30,000 tokens). k = 4 leaves slots 2 and 4 uncovered; k = 12 adds the third `hard_case` and 6
more rules for about 4,700 more tokens on every call. To try another size, set
`EXAMPLES_PATH=prompts/examples_v5.1_k12.json` (or `_k4`) in `.env`, run, and compare with
`compare_runs.py`.

### 9.3 Learning from the reasoning and evidence

Each assistant turn keeps the record's full `reasoning` and every item's `evidence`. The few-shot
guide (`prompts/fewshot_guide_v5.1.txt`), added after the rules only when examples are sent, tells
the model how to use them:

- learn the step-by-step method from `reasoning` (statements, each field with its rule ID, G3-G5,
  the per-place fallback check, the `useful` decision) and reason through the new article the same way;
- learn evidence selection from `evidence` (the event sentence first, then every sentence that
  supplied a field, in article order, copied exactly);
- learn what gets no item from the not-useful examples, and not look for items because examples
  have them;
- the rules decide when an example and a rule seem to differ;
- never reuse an example's places, dates, numbers, strains or quotes.

The v5.1 rule text is unchanged. Handoff 4.5 asks for no line telling the model to copy the
examples; the guide asks the model to learn the method, not to copy, and keeps the rules as the
authority. Its effect is part of what the k comparison measures. To measure it alone, run k = 8
once more with the guide file renamed.

### 9.4 Notes

1. **No separate approval step.** If a record is corrected, correct it in its `v2.jsonl`, rebuild
   `data/` and rerun `select_examples.py` (or swap in an alternate from `few_shot_selection.md`).
2. Examples are ordered with not useful and useful mixed, ending on a not-useful one, so the last
   turn does not push the model toward items.
3. Hard examples were picked partly from the model's mistakes on the dev sample D; they are then
   left out of scoring like every example, so no scored article was seen by the model.
4. **No example is an article labelled in more than one set.**

## 10. How results are scored

**Gold is the chain-of-thought records** (`data/gold_labels.json`). The human `useful` answers are
a second comparison (report section 6).

**Usefulness.** Positive class = *useful*. Confusion table, precision, recall, F1 and accuracy.
`useful` is read from the items (`bool(items)`), as v5.1 Section 11 defines it.

**Items: scored article by article, then averaged.** Each article gets its own item scores, and the
report averages those over articles (macro average). Every article counts once: an article with 20
items does not outweigh twenty articles with one item, as it would if all items were pooled.
Evidence is never compared. Upper/lower case and repeated spaces are ignored; null equals null.

For each article:

| Per-article score | How it is computed |
|---|---|
| exact matches | model items whose kind, number, count_type, status, strain, city, state, country, start_date, end_date and words all agree with a gold item (each gold item matched once) |
| exact precision / recall / F1 | matches / model items; matches / gold items; 2 x matches / (gold items + model items) |
| partial credit | each model item is aligned with its most similar gold item of the same kind and country (each item used once). A pair scores the share of its fields that agree: counts compare number, count_type, status, strain, city, state, start_date, end_date (8); trends compare words, strain, city, state, start_date, end_date (6). Missing and extra items score 0 |
| partial-credit precision / recall / F1 | the same formulas with the sum of the pair scores in place of the number of exact matches |

Then, over articles (report section 2.1, each with a 95% bootstrap interval resampling articles):

| Average | Over |
|---|---|
| **F1, exact and partial credit** (the headline) | articles with items on either side |
| F1 | articles where gold has items |
| precision | articles where the model wrote items |
| recall | articles where gold has items |

Articles with no items on either side are left out of the item averages (nothing to extract,
nothing extracted, so any score would be arbitrary); the `useful` confusion table counts them as
true negatives. The report also shows how many articles are fully right, partly right or fully
wrong (2.2), and the **accuracy of each field on aligned items** (2.3), which shows where misses
come from. `row_results.csv` has every article's six scores.

**Why both exact and partial credit.** Exact match is all or nothing: one day off in a date turns a
correct item into one missing and one extra. Partial credit shows how close the model is; exact
match shows how often it is fully usable. Report both; exact is the stricter number.

**Pooled scores (reference only, report 2.4).** All items of all articles added together, in four
tiers: exact; strict (kind, place, strain, dates); relaxed (kind, place, strain); weekly (kind,
strain, country, ISO week of end_date). Kept for comparison with earlier runs and because the weekly
tier is closest to what the weekly signal needs.

**Comparing runs.** `compare_runs.py` lists `useful` precision, recall and F1, per-article exact and
partial-credit F1, and the pooled exact and weekly F1. Unscored rows (cut-off or invalid replies)
drop out of a run's averages, so check that runs scored the same articles before comparing them.

**Score variants** (report section 5):

| Variant | Articles |
|---|---|
| Reached the model (headline) | scored articles that passed the keyword gate |
| All | including gated articles, which code decides; this inflates `useful` accuracy |
| Inactive-only filtered | an article whose only items are `inactive` trends counts as having no items, on both sides |

Jahnavi wants inactive-only articles filtered from the weekly signal. So far: Jahnavi 71, 241,
248, 310; Aditya 17, 239, 241, 307, 310, 320; Manoj 9, 13, 37, 255. **Ask her which variant is
the headline before the test run**, and decide it before seeing the score.

## 11. Automatic checks

Every reply is validated during the run (section 3), so a reply with shape errors is asked for
again before it can reach scoring. **Shape errors** that remain after 2 retries make a row
`malformed` (not scored): a missing top-level key (`summary`,
`reasoning`, `useful`, `reason`, `items`), `useful` not true/false, `reasoning` not a non-empty list
of text, an item missing one of the 12 fields, a kind other than the four, an invalid date, a place
that is not text or null, a number that is not a whole number, evidence that is not a non-empty
list of text.

**Rule violations** do **not** stop a row from being scored; they are reported so you can read
those rows with care:

| Rule | Check | Prompt |
|---|---|---|
| (a) | every evidence quote is an exact piece of the article | 10.1 |
| (b) | a trend has one of the seven words and null number, count_type, status | 2.2, 9.2 |
| (c) | a count has a number, a valid count_type and status, and null words | 2.2 |
| (d) | city, state, country are null or a real place of that kind | 5.1 |
| (e) | start_date is not after end_date | 4.2 |
| (f) | no two items identical except evidence | G3 |
| (g) | `useful` equals `bool(items)`, both ways | Section 11 |
| (h) | a country and an end date are present | G1, G2 |
| (i) | the end date is on or before the scan date and within 30 days of it | 4.7 |
| (j) | evidence after the first part is in article order (a warning) | 10.1 |
| (k) | `reasoning` begins with Step 0 | How to work |

Two items of the same kind and place with overlapping dates are **not** flagged: G5 requires them
("50 and 17", "856 and 591").

### Rule (a): evidence is copied from the article

Only line breaks and repeated spaces are ignored. Each failure gets one of three reasons, counted
separately in `report.md`:

| Reason | Meaning |
|---|---|
| not found in the article | reworded, shortened (for example with "..."), joined from separate places, or invented |
| differs only in quote or dash characters | the words are the article's, but curly quotes or dashes were changed |
| empty | the quote is blank |

It proves the text exists in the article, not that the quote supports the item.

### Rule (d): places are real

There is no list of names in the code. For each non-null place field, `PlaceChecker.is_known`
asks OpenStreetMap's free geocoder (Nominatim) one structured question: `country=...`,
`state=...` or `city=...`. A field is checked only against its own kind: "India" is not a state,
"California" is not a country, and "Southern Hemisphere" or "Europe" are not found.

- **Answers are saved** in `data/place_lookups.json` with the best match and the date. Each name is
  looked up once; later runs give the same answers without internet. New names are looked up at
  about one per second (Nominatim's usage policy; do not lower `MIN_SECONDS_BETWEEN_REQUESTS`).
- **If the service is unreachable** the value is reported as "could not be checked". It is never
  guessed and nothing is saved.

Limits: a match means a place with that name exists *somewhere*; the geocoder forgives misspelled
cities; each field is checked alone, so a city is not checked against its state or country.

Place data: © OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright).
Keep this credit if you share results that include `data/place_lookups.json`.

## 12. Output files

Per run, in `results/run_<date>_<time>/` (the `results/` folder is ignored by git):

| File | Content |
|---|---|
| `raw_results.jsonl` | one line per article: gated flag, raw reply, parsed reply, finish reason, token counts, seconds, errors |
| `run_config.json` | model, base URL, prompt and examples file names with SHA-256 hashes, example count, temperature, max tokens, extra body, split or ids file, start time |
| `report.md` | 1 usefulness confusion table; 2 items article by article (2.1 per-article exact and partial-credit scores, 2.2 how articles are spread, 2.3 field accuracy on aligned items, 2.4 pooled scores for reference, 2.5 by country); 3 rule checks and the evidence summary; 4 coverage (gated and unscored rows); 5 score variants with intervals; 6 against the human labels |
| `scores.json` | `useful` precision, recall and F1, per-article exact and partial-credit F1, and the pooled F1 scores, for each variant; read by `compare_runs.py` |
| `row_results.csv` | per article: `sources`, `status`, `gated`, gold, human and model usefulness, item counts, exact matches, missing, extra, per-article exact and partial-credit precision, recall and F1, item-set outcome, rule violations, problems, the model's `reason` |
| `item_comparison.csv` | one line per item: `exact match`, `same kind and place` (with `differing_fields`), `missing from model` or `extra from model`. Gold and model values side by side for number, count_type, status, dates and words, plus both sides' evidence |

Read `report.md` in this order: section 4 (what could not be scored), section 3 (rule
violations), section 1 (usefulness), section 2 (items). Then open `item_comparison.csv` or
`inspect_row.py` to see why items fail.

## 13. Testing

```bash
python -m unittest discover tests
```

99 tests. They need no API key and no internet (the place check uses a fake geocoder).

| File | Covers |
|---|---|
| `tests/test_checks.py` | the v5 reply shape, rule (a) exact quotes, and rules (b), (c), (e)-(k) |
| `tests/test_metrics.py` | per-article exact and partial-credit scores, item alignment, macro averages, exact and weekly matching, the six item-set outcomes, F1, usefulness table, inactive-only filter, bootstrap interval |
| `tests/test_llm_client.py` | the 40-per-minute limiter (40 at once, the 41st waits for the window, the window slides, the limit holds across threads), retries counted against the limit, `Retry-After` and back-off, giving up after `MAX_RETRIES`, no retry for errors a retry cannot fix |
| `tests/test_places.py` | the place cache, offline mode, an unreachable service, rule (d) |
| `tests/test_pipeline.py` | the v5 article format and chat turns, the keyword gate (no API call), reply parsing, choosing articles by split, scoring with gated and unparseable rows, `build_gold_files.py` (overlaps merged, Thanya 41+ in test, header lines not sent), the few-shot guide sent only with examples, and the slot tagging and prompt order of `select_examples.py` |

Not covered by tests: the live API call, the report text and the command-line wrappers. Check
those with a one-article run (section 2) and `inspect_row.py`.

## 14. Layout

```
prompts/           ACTIVE prompt: system_prompt_v5.1.txt, fewshot_guide_v5.1.txt, examples_v5.1.json;
                   candidates examples_v5.1_k4/k8/k12.json; old v2.0 pair kept
prompt_versions/   archive: the full prompt documents (v1.0, v2.0, v5.1)
data/              articles.json, gold_labels.json, human_labels.json, place_lookups.json,
                   dev_sample_200.txt (the gold record sources are in ../labeled_data_chain_of_thought/)
results/           one folder per run (ignored by git)
scripts/
  build_gold_files.py   refresh data/ and the system prompt from the capstone files
  make_dev_sample.py    draw the dev sample D once
  select_examples.py    choose the few-shot candidates (k = 4, 8, 12) and write the review sheet
  build_data_files.py   OBSOLETE v2.0 converter; do not run
tests/             unit tests (section 13)
flu_extractor/
  config.py        paths and model settings
  data_loading.py  read articles, gold labels and human answers; resolve "Jahnavi:6" to an id
  prompt.py        build the chat messages (system prompt, example turns, article)
  llm_client.py    the only code that calls the model API
  extractor.py     one article -> one log record (keyword gate, parsing the reply, never crashing)
  checks.py        reply shape check and the automatic rule checks (a)-(k)
  places.py        asks the geocoder whether a city/state/country exists; saves the answers
  metrics.py       F1, usefulness scoring, item matching tiers, item-set outcomes, bootstrap
  evaluation.py    score a whole run against gold; choose the default articles
  report.py        write report.md, scores.json and the two CSV files
run_extraction.py  command-line tool: ask the model
evaluate_run.py    command-line tool: score a run
inspect_row.py     command-line tool: one article, gold vs model, field by field
compare_runs.py    command-line tool: several runs side by side (k comparison, test mean and range)
few_shot_selection.md  review sheet of the 12 example candidates and their alternates
HANDOFF_thanya_evaluation_fewshot.md   the plan: Thanya's set, extractor changes, examples, evaluation
```

## 15. Known limitations

State these in the write-up (handoff 5.4):

- **Gold is LLM-written.** The records were written by Claude from the v5 rules and reviewed by
  Jahnavi on flips and big clashes, not line by line. A model scored against them partly measures
  agreement with Claude. That is why the human comparison stays in the report.
- **Records vs human labels on `useful`** (records yes and human yes / records yes and human no /
  records no and human yes / both no): Jahnavi 82 / 9 / 0 / 229, Aditya 70 / 9 / 4 / 237, Manoj
  82 / 15 / 4 / 219. These differences have not been broken down by cause yet; do that before the
  write-up.
- **Read depth.** Aditya and Manoj rows were read once. Jahnavi's rows 1-226 had a second full read.
- **Sample mix.** The 1,200 articles were drawn half from likely useful and half from likely not
  useful, so the useful rate is higher than in the full pool. Scores do not carry over directly to
  raw news.
- **Rule edits during Aditya and Manoj.** Dev scores are optimistic. Only the test score is a fair
  estimate.

Other limits:

- **Run-to-run variation is large.** The hosted model does not return identical output for identical
  input, even at `temperature=0` with a fixed seed and `top_p` near 0: 4 of 53 repeated articles
  flipped `useful`, and item lists matched for 1 of 17 (section 3). Single-run differences of a few
  points between settings are within this noise.
- **Context length.** Not yet checked against the model's limit. A request that is too long fails as
  an API error and is reported as unscored, never cut.
- **Invalid JSON.** The model often copies article quotations with unescaped `"`. Such replies are
  repaired or asked again (section 3); the API's JSON mode was tried and not used, because it turns
  the same mistake into a reply padded with blank lines up to `max_tokens`.
- **Exact matching is demanding.** A one-day date difference or a different `count_type` makes an
  item missing plus extra. The strict, relaxed and weekly tiers and `differing_fields` in
  `item_comparison.csv` show which field went wrong.
- **Garbled characters.** Some source articles contain broken characters such as `â`. The prompt
  tells the model to copy evidence as stored, so this is expected.
- **Cost and speed.** Each call sends about 16,500 tokens of rules plus about 1,500 per example.
  Hosted API quotas and latency are not guaranteed.
