# Flu news LLM extractor

Runs a large language model over human-influenza news articles with **prompt v5.2**, and scores
its replies against the **v5.2 labels** (the gold labels). For each article the
model answers two tasks:

1. **Useful or not**: does the article report current human flu activity in a real place?
2. **Items**: every `cases`, `hospitalized`, `deaths` or `trend` finding, with number, count
   type, status, strain, place, dates, trend word and the quoted evidence.

The model is **DeepSeek V4.1 Flash** (`deepseek-ai/deepseek-v4.1-flash`), called through NVIDIA's
OpenAI-compatible API. NVIDIA lists only the 4.1 build of DeepSeek V4 Flash. No human labels are used anywhere: gold is the v5.2 labels only.

## Recent changes (2026-11-05 to 2026-11-06)

- **Prompt v5.2 and the v5.2 labels (6 Nov):** gold is now `data/chain_of_thought/<Name>_labels_v5.2.jsonl`
  for all four sets (Jahnavi, Aditya, Manoj, Thanya), labeled with prompt v5.2 (2). After removing the 80
  shared articles: 1,120 articles, 1,098 sent. The prompt files are `prompts/*_v5.2.*`; the few-shot
  examples are the 22 of the labels' own `fewshot_examples_v5.2.json` (14 useful, 8 not useful), with
  their place names in the agreed form. The rule checks add v5.2's G4 and
  G5 (5.5). The chain-of-thought v2 records and the v5.1 prompt files were removed from `data/` and
  `prompts/` (they are in git history).

- **Model:** DeepSeek V4.1 Flash on NVIDIA, with greedy decoding, a fixed seed and thinking off (4.2).
- **Data:** gold is only the label records (v2 until 6 Nov, now v5.2); no human labels; every article that is in more
  than one labeling set is removed; the input files are validated before a build is written and before
  a run starts (2).
- **Every article is sent** (1,098 with the v5.2 labels), none decided by code; the few-shot examples
  are left out (3).
- **Checks:** three layers matched to the prompt (5.5). The format check now covers every fixed value (kind,
  count type, status, trend word, strain, number of at least 1, the place chain, dates, `useful` against
  the items) and, with the evidence check, decides whether a reply is sent back to the model (4.4). The
  place check asks the geocoder for the whole city-state-country chain.
- **Place names (6 Nov, approved):** prompt v5.1 and v5.2 section 5.1 now say every city, state and country
  has one agreed form, its English name in OpenStreetMap. The code turns every place, in gold and in model
  replies, into that form before checking, matching and scoring (5.6), for any place, with no name tables.
- **Scoring:** pairs need similarity 0.8 and are locked best partners first; every metric is computed
  per article and summarised over articles; article outcome buckets; four charts (5).
- **Changes are settings:** `PROMPT_VERSION`, `RECORDS_SUFFIX`, `EXAMPLES_PATH`, `NVIDIA_MODEL_ID` and
  friends; how to change data, prompt, examples or model is in section 8.
- **One example set:** `prompts/examples_<PROMPT_VERSION>.json` only; `select_examples.py` writes that one file (8.3).
- **Place answers saved afresh:** `data/place_lookups.json` was started again from empty, since the old
  answers did not record the kind of place; it holds only answers of the current lookup (5.5).
- **Data in agreed place form (6 Nov):** the records and the examples were rewritten to the agreed form
  (USA -> United States and 15 others; backups in `data_backups/2026-11-06_before_place_names/`); empty
  place fields were never filled. Australian towns recorded as administrative suburbs (Mornington) count
  as cities (5.6).
- **Removed:** the handoff document, the old scoring example, the v2.0 prompt pair, the human labels,
  the dev sample, the obsolete build scripts, the k4/k8/k12 example candidates.

## Contents

1. [Quick start](#1-quick-start)
2. [The data](#2-the-data)
3. [Which articles are sent](#3-which-articles-are-sent)
4. [How a request works](#4-how-a-request-works)
5. [How the results are measured](#5-how-the-results-are-measured)
6. [Commands](#6-commands)
7. [Configuration](#7-configuration)
8. [Making changes](#8-making-changes): new labels, a new prompt version, new examples, another model
9. [Output files](#9-output-files)
10. [Testing](#10-testing)
11. [Layout](#11-layout)
12. [Known limitations](#12-known-limitations)

---

## 1. Quick start

Requirements: Python 3.11 or newer, an NVIDIA API key with access to
`deepseek-ai/deepseek-v4.1-flash` (https://build.nvidia.com), and internet access.

```bash
cd llm-extractor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env          # put your key after NVIDIA_API_KEY=
chmod 600 .env

python -m unittest discover tests                     # 1. the logic works (no API, no internet)
python run_extraction.py --ids Jahnavi:192            # 2. one article; prints the run folder
python inspect_row.py results/run_<time> Jahnavi:192 --reasoning  # 3. read the reply
python run_extraction.py                              # 4. all 1,098 articles (see section 3)
python evaluate_run.py results/run_<time>             # 5. score it; then read report.md
```

All commands run from the `llm-extractor` folder with the virtual environment active. The key
is read from `.env` and never printed.

A full run is long. On 2026-11-05 the NVIDIA queue for this model answered a 15-token test
request in 153 s, so a full run takes hours, not minutes. If it stops (quota, network), resume it:
`python run_extraction.py --run-dir results/run_<time>`.

## 2. The data

`data/` holds only what the pipeline reads:

| File | Content |
|---|---|
| `chain_of_thought/<Name>_labels_v5.2.jsonl` | the gold source: the v5.2 labels of Jahnavi, Aditya, Manoj and Thanya (1,280 records, 1,200 unique articles), one line per packet entry |
| `articles.json` | built: one record per article that is scored (1,120): `article_id`, `scan_date`, `link`, `sources`, `article` |
| `gold_labels.json` | built: one record per article (1,120): `article_id`, `useful`, `labelers`, `items` |
| `place_lookups.json` | the saved answers of the place lookups (sections 5.5, 5.6), so each place chain is asked online only once and later runs give the same names. It is **not a list of allowed places**: a chain not in it is asked online and added |

Rebuild `articles.json` and `gold_labels.json` whenever the label records change:

```bash
python scripts/build_gold_files.py
```

It reads every `*_labels_v5.2.jsonl` in `data/chain_of_thought/` (`RECORDS_SUFFIX` in
`config.py`), takes the article texts from `<capstone>/labeling/labeling/<Name>_texts.txt` (the records
do not contain the text), and also refreshes `prompts/system_prompt_v5.2.txt` from
`prompt_versions/llm_extraction_prompt_v5.2.md` (`PROMPT_VERSION` in `config.py`).

**Two record layouts are read** (`data_loading.read_label_records`): the v5.2 labels are *flat* (one line
per packet entry: `pos`, `tag`, `article_id`, `scan_date`, `split`, then the reply `summary`,
`reasoning`, `useful`, `reason`, `items`); the older chain-of-thought records are *nested* (`source_rows`,
`output: {useful, reason, items}`, `rules_used`). A flat record takes its labeler from the file name, its
row from `pos`, and its `rules_used` from the rule IDs its reasoning cites. The labels' `split` field
(dev/test) is not used: there is no separate dev or test set, every article except the examples is sent.

**Where the v5.2 labels come from.** They were written by Claude (Opus 5.5) agents in batches, following
`llm_extraction_prompt_v5.2.md` as it was on 5 Nov (before the 6 Nov place-name wording; nothing else
differs), each agent reading the full prompt and its batch (source folder:
`<capstone>/labeling_final_completed/labeling_final/v5.2_labels/`, with its own README). They are model
labels, not human labels: section 12 says what that means for the scores.

**Duplicate articles are removed completely.** An article that appears in more than one labeling
set is dropped with every copy and its gold record: the 40 articles labelled in two sets
(Jahnavi/Aditya, Aditya/Manoj) and the 40 articles repeated as Thanya rows 1-40 (in the v5.2 labels
both copies have the same reply; they are still removed, so no article can count twice). Result:

| | Useful | Not useful | Articles | Gold items |
|---|---|---|---|---|
| All v5.2 labels | 348 | 852 | 1,200 | 1,005 |
| **After removing shared articles** | 328 | 792 | **1,120** | 963 |

**The input data is validated** (`flu_extractor/data_checks.py`), with the same code that checks the
model's replies (section 5.5):

| File | Checked |
|---|---|
| `articles.json` | every record has `article_id`, `scan_date` (YYYY-MM-DD), `link`, `sources`, a non-empty `article`; no article twice |
| `gold_labels.json` | every record has `article_id`, `useful`, `labelers`, `items`, belongs to an article in `articles.json`, and its items pass the format check and the evidence check (every quote is in the article) |
| the examples file | every example has `article_id`, `scan_date`, `link`, `article`, `answer`; the answer passes the format and evidence checks and starts with Step 0 and a Step 1 citing Rule 1; its article text is the same as in `articles.json` |

`build_gold_files.py` writes nothing if its output fails, and `run_extraction.py` stops before any API
call if the files it would use fail. The build also stops if two copies of an article differ or two
records of one article disagree. All current files pass.

Gold record format (`gold_labels.json`):

```json
{"article_id": "20161230170000-2179", "useful": true, "labelers": ["Jahnavi"],
 "items": [{"kind": "hospitalized", "number": 658, "count_type": "cumulative_region",
            "status": "confirmed", "strain": null, "city": null, "state": "New York",
            "country": "USA", "start_date": null, "end_date": "2016-12-30", "words": null,
            "evidence": ["Some 658 flu-related hospitalizations in New York have been reported so far this flu season."]}]}
```

## 3. Which articles are sent

Without `--ids` or `--ids-file`, a run sends **every article in `gold_labels.json` except the
few-shot examples** (the model sees their answers in the prompt):

| | Useful | Not useful | Articles |
|---|---|---|---|
| Labelled articles | 328 | 792 | 1,120 |
| Few-shot examples (k = 22), left out | 14 | 8 | 22 |
| **Sent to the model and scored** | **314** | **784** | **1,098** |

Every one of the 1,098 is sent, including articles that never mention flu: prompt Rule 1 tells the
model the exact reply for them, so no article is decided by code.

## 4. How a request works

### 4.1 Messages

1. `system`: the v5.2 rules (`prompts/system_prompt_v5.2.txt`), then the few-shot guide
   (`prompts/fewshot_guide_v5.2.txt`), which says how to learn from the examples' reasoning and evidence;
2. for each of the 22 examples (`prompts/examples_v5.2.json`): a `user` turn with the article and an
   `assistant` turn with the gold answer as JSON (`summary`, `reasoning`, `useful`, `reason`, `items`);
3. a final `user` turn with the article:

```
scan_date: 2016-12-30
link: http://...
article:
<article text>
```

The GDELT header lines of the labeling files are never sent (the prompt forbids using them, 5.6).
**The v5.2 examples** are the 22 chosen with the v5.2 labels (`fewshot_examples_v5.2.json` in the labels'
folder; its README says why): all from the labels' dev split, 14 useful and 8 not useful, 4 easy, 6 medium
and 4 hard, covering all kinds, count types, statuses and trend words. Each entry keeps the label file's
reply, with place names in the agreed form (items and reasoning outside quoted text), plus its
`difficulty` and `why_chosen` notes (not sent). Three of them break a rule the checks report (5.5):
evidence after the first quote out of article order in Jahnavi:50, Manoj:51 and Manoj:80, and Manoj:80
also records the 2 child deaths inside the 730 deaths (G4). They are kept as delivered.
[few_shot_selection.md](few_shot_selection.md) is the earlier selection for v5.1 (8 examples from the v2
records); it no longer describes the active set.

**How the model learns from the examples.** Each assistant turn is the example's full answer:
the `reasoning` steps in the order of the prompt's "How to work" (summary; Rule 1 and the list of
flu statements; each statement checked for human flu, count or trend, number, dates, place, status,
count type, strain or word, evidence; G3-G5; the per-place fallback check; the `useful` decision),
each step citing its rule IDs, and the `items` with their `evidence`. The few-shot guide
(`prompts/fewshot_guide_v5.2.txt`) says that the v5.2 rules decide every reply and the examples only
show how they are applied (an example that seems to disagree with a rule loses to the rule); that the
model learns from two parts of each example, `reasoning` (how the rules are applied, step by step,
with rule IDs) and `evidence` (the event sentence first, then every sentence that gave a field, in
article order, copied exactly); and that each new article is decided from its own text and
`scan_date` alone, never reusing an example's places, dates, numbers, strains or quotes. It says
nothing about how many examples are useful, so it does not push the model either way. The examples
are sent in the order of the labels' `fewshot_examples_v5.2.json`. Every example passes the format and
evidence checks (section 2); the rule checks report three of them (section 4.1, "The v5.2 examples").

### 4.2 Decoding settings: as little variation as possible

Every request, retries included, uses the same settings (`flu_extractor/config.py`):

| Setting | Value | Why |
|---|---|---|
| `temperature` | 0 | greedy decoding: always the most likely next token |
| `top_p` | 1 | no extra sampling cut-off (irrelevant at temperature 0, sent so the server does not apply its own default) |
| `seed` | 20261101 | fixes any sampling left on the server |
| `extra_body` | `{"chat_template_kwargs": {"thinking": false}}` (NVIDIA); `{"thinking": {"type": "disabled"}}` on DeepSeek's own API, set with `EXTRA_BODY_JSON` (8.4) | no hidden thinking pass: the v5 reply carries its reasoning in the JSON, and thinking adds tokens, time and variation (verified on NVIDIA: 0 reasoning tokens). The switch depends on the API: DeepSeek's own API ignores NVIDIA's and thinks by default |
| `max_tokens` | 8000 | the longest gold reply is about 5,000 tokens |
| no penalties | defaults | presence and frequency penalties are 0 |

An earlier version raised the temperature to 0.3 for the last retry; that is removed, so no
request is ever sampled. **Hosted models are still not guaranteed to be bit-for-bit
repeatable**: the server batches requests with other users. To measure the remaining
variation, run the same articles twice and compare with `compare_runs.py`.

### 4.3 Rate limit: at most 40 requests per minute

One `RateLimiter` (`llm_client.py`) is shared by all worker threads. Before **every** request,
including each retry, it waits until fewer than 40 requests have started in the last 61 seconds (one
second of margin). The OpenAI library's own retries are switched off, because they would bypass
the limiter. The limit therefore holds for any `--workers` value. Because a reply takes minutes,
the default is 16 requests in flight. Change the limit with `NVIDIA_REQUESTS_PER_MINUTE` in `.env`.

API errors worth retrying (429, timeouts, lost connections, 5xx) are retried up to 4 times, waiting for the
server's `Retry-After` if it sends one, otherwise 5, 10, 20, 40 s. After 5 API failures in a row the run
stops (usually the daily quota) and can be resumed with `--run-dir`.

### 4.4 Every reply is validated

A reply is accepted only if it is complete (not cut off at `max_tokens`), parses as one JSON
object, passes the **format check** (`checks.find_format_errors`: every key, field and fixed value
of section 5.5, layer 1) and quotes **every evidence passage exactly from the article**
(`checks.find_evidence_errors`, layer 2). Otherwise:

1. **Repair**: a double quote copied from the article inside a JSON string is escaped, and raw line breaks
   inside strings become `\n`. Nothing else changes, so evidence still matches the article.
2. **Ask again** with a note after the article naming the problems (for example "item 2 status must be
   one of confirmed, suspected" or "these evidence quotes are not exact copies of the article: ..."), up
   to 3 times. The last time asks for a compact reply (at most 12 reasoning steps, article text only in
   `evidence`). The decoding settings never change.
3. If all 4 replies are invalid, the record keeps the reason in `invalid`. A reply that still breaks
   the format is reported as `unparseable` or `malformed` and not scored. A reply whose only problem is
   a quote not copied exactly is scored, and the quote is reported as rule (a). Rerun such articles with
   `python run_extraction.py --run-dir results/<run> --retry-invalid`.

A test on the 832 replies of an earlier full run (v5.1 data, another model, older validation) showed what
the format check now catches and sends back: a city with no state (44 items), a count with no number
(44) or a number of 0 (9), a missing status (30) or count type (16), no end date (29), "swine flu" as
a strain instead of H1N1 (27), a count with a trend word (19), and "elevated" as a trend word (15).

## 5. How the results are measured

Scoring is a separate step (`evaluate_run.py`), so it can be repeated without new API calls.

### 5.1 Task 1: useful or not

One cell of a confusion table per article: gold `useful` against the model's `useful`.
The report gives precision, recall, F1 (with a 95% bootstrap interval) and accuracy. Under the
rules (Section 11) `useful` is true exactly when the reply has items. The rule checks report any reply
where the two disagree.

### 5.2 Task 2: the items

**Step 1: places in their agreed form, then normalize.** Every city, state and country of a gold or
model item is replaced by its agreed form, its English name in OpenStreetMap (section 5.6), so
"Bangalore" and "Bengaluru", or "USA" and "United States", are the same value. Then
(`normalization.py`, `norm_v3`) only harmless differences are removed: case, spaces, curly vs straight
quotes and dashes. A different number, period, count type or place stays different.

**Step 2: similarity of a gold item and a model item.** The share of the gold kind's fields that
agree, every field weighing the same. Counts have 10 fields (kind, number, count_type, status, strain,
city, state, country, start_date, end_date), trends 8 (kind, words, strain, city, state, country,
start_date, end_date). Evidence is not compared. **A hit's similarity is also its accuracy**: the
same fields, compared the same way.

**Step 3: pairing** (`matching.py`, `matching_v3`), inside each article, one to one:

1. allowed pairs: the same country and the same kind (or two counts with the same number, a kind
   confusion), and similarity **at least 0.8** (at most 2 of a count's 10 fields, or 1 of a trend's 8,
   may disagree);
2. **best partners first**: lock the allowed pair with the highest similarity among the items not yet
   paired; both items are then used up. Repeat until no allowed pair is left. A strong pair is never
   given up to make room for more, weaker pairs, so each pair is the closest match still available to
   both of its items;
3. **ties** at the highest similarity: lock the pair whose two items have the fewest other allowed
   partners still available (this leaves more good pairs for the others), then article order (first gold
   item, then first model item), so the result is always the same;
4. same-kind pairs first, kind-confusion pairs only among the items left after that.

Example (G = gold, I = model; pairs under 0.8 not allowed):

| | I1 | I2 | I3 |
|---|---|---|---|
| G1 | 0.8 | 0.9 | 0 |
| G2 | 0.6 | 0.6 | 1.0 |
| G3 | 0.7 | 0.8 | 0.9 |

G2-I3 (1.0) is locked first, then G1-I2 (0.9). G3's remaining option, I1 at 0.7, is not allowed, so
G3 is a miss and I1 an extra: 2 hits, accuracy 0.95. (Pairing for the most pairs would have given
G1-I1, G2-I3, G3-I2, pushing G1 onto its weaker partner.) The three examples are unit tests.

A pair is a **hit**, a gold item left alone a **miss**, a model item left alone an **extra**.

**Step 4: score each article.** Every task 2 metric is first computed inside one article. A metric
that has no meaning for an article is left blank for it (never set to 0 or 1), and that article is
left out of that metric's summary:

| Metric | Calculation inside one article | Articles it covers | What it says | Good |
|---|---|---|---|---|
| **Recall** | hits / gold items | gold has items | did the model catch the article's real events? Low = it misses outbreaks | near 1 |
| **Precision** | hits / model items | the model wrote items | are the events it wrote real? Low = false alarms | near 1 |
| **F1** | 2 x hits / (2 x hits + misses + extras) | either side has items | both together; low if either is low | near 1 |
| **Accuracy** | mean similarity of the article's hits | the article has a hit | how right the details of the found events are; never below 0.8, the pairing threshold | near 1 |
| **Exact rate** | hits with every field right / hits | the article has a hit | how many found events are completely right | near 1 |
| **Field accuracy** (one per field) | hits with that field right / hits that have the field | the article has a hit with that field | which detail goes wrong: dates, number, place... | near 1 for every field |

Accuracy and field accuracy read the same grid (one row per hit, one column per field) in two
directions: accuracy averages each hit's row, field accuracy each field's column. Misses and extras
count only in recall, precision and F1; accuracy, exact rate and field accuracy look only at hits, so
no mistake is counted twice. Two items that describe the same event but agree on under 80% of their
fields count as one miss and one extra.

**Step 5: combine the articles.** Each metric is summarised over the articles it covers, every article
weighing the same, so an article with 10 items does not count more than an article with 1:

| Summary | Calculation | What it says |
|---|---|---|
| **Mean** (the headline) | sum of the article values / articles covered | the score of a typical article |
| **95% interval of the mean** | the mean recomputed on 1,000 resamples of the articles (fixed seed) | how certain the mean is; two runs whose intervals overlap a lot may differ only by noise |
| **Median, 25th-75th percentile** | the middle value, and the range of the middle half of the articles | whether a few very good or very bad articles pull the mean |
| **At 1** | articles with the value 1 / articles covered | how often an article is fully right on this metric |
| **At 0** | articles with the value 0 / articles covered | how often an article fails completely |
| **Articles covered** | count | how many articles the numbers rest on |

Example, F1 of three articles 0.5, 0.67 and 1.0: mean 0.72, median 0.67, at 1 33%, at 0 0%.

**Step 6: article outcomes.** Each article is put in exactly one bucket, and the report gives the count
and share of each:

| Gold | Bucket | Good |
|---|---|---|
| has items | every item found, no extras (and, of these, how many with every detail right) | high |
| has items | some found, with misses or extras | |
| has items | nothing found | low |
| has no items | the model wrote none (correct) | high |
| has no items | the model wrote items (false items) | low |

Articles where both sides are empty are credited here, not given F1 = 1, which would inflate the means.

**Step 7: context, not scores.** The report also gives: the hits, misses and extras added over all
articles; how many extras repeat another model item; misses and extras by kind and country; the
articles that could not be scored; and the mean recall, precision and F1 with inactive-only items
(the 1.3 food and monitoring fallbacks) removed on both sides.

**Duplicates** (`duplicates.py`) are never deleted silently. Two identical gold items each need their own
model item (pairing is one to one). An extra that repeats another model item is still an extra.
Gold candidate groups are listed in `duplicate_candidates.csv` and can be decided in
`data/duplicate_adjudication.json` (`duplicate` keeps only the first item).

### 5.3 Charts

`evaluate_run.py` writes four charts into the run folder (`flu_extractor/plots.py`); the values behind
them are in `article_metrics.csv`.

| Chart | Shows | How to read it |
|---|---|---|
| `plot_article_counts.png` | one stacked bar per article with items on either side: hits, misses, extras | mostly hit-coloured bars = good; many miss segments = it misses events; many extra segments = it over-reports. Articles are sorted by gold items, so problems with long articles stand out |
| `plot_article_metrics.png` | one histogram per metric (recall, precision, F1, accuracy, exact rate) of the per-article values, the mean dashed | a tall bar at 1 = most articles fully right; a bar at 0 = articles that fail completely; the spread shows how uneven the model is |
| `plot_field_accuracy.png` | mean per-article accuracy of each field, lowest first | the shortest bars are the details to fix |
| `plot_article_buckets.png` | the number of articles in each outcome bucket | "all found" and "left empty" high, "nothing found" and "false items" low |

### 5.4 Where errors come from

Report section 5: hits, misses and extras by kind, kind confusions, repeats among the extras, and
misses and extras by country. Section 6: what could not be scored, evidence copied exactly, rule checks.

### 5.5 The checks (`checks.py`)

Every reply, every gold record and every few-shot example is checked against the prompt (v5.2; v5.1
has the same reply format and fixed values) by the same code, in three layers.

**Layer 1: format.** A failure sends the reply back to the model (section 4.4); a reply that still fails
is not scored.

| Check | Prompt |
|---|---|
| one JSON object with `summary` (text), `reasoning` (a non-empty list of steps), `useful` (true/false), `reason` (text), `items` (a list) | "Your reply", 2.1 |
| every item has exactly the 12 fields, no others | 2.2 |
| `kind` is `cases`, `hospitalized`, `deaths` or `trend` | 2.3 |
| a trend: `words` is one of `rising`, `falling`, `high`, `moderate`, `low`, `inactive`, `present`; `number`, `count_type`, `status` are null | 2.2, 9.2 |
| a count: `number` is a whole number of at least 1; `count_type` is `new`, `cumulative_region` or `cumulative_subset`; `status` is `confirmed` or `suspected`; `words` is null | 2.2, Sections 3, 6, 7 |
| `strain` is null, a subtype code in upper case (`H1N1`, `H3N2v`, `H5`), `influenza A`, `influenza B` or `avian influenza` | 8.1 |
| a country is present; a city has a state; place fields are text | G1, 5.1 |
| an end date is present; dates are real `YYYY-MM-DD` dates; the start is not after the end | G2, 4.2 |
| `evidence` is a non-empty list of non-empty quotes | 10.2 |
| `useful` is true exactly when `items` is not empty | Section 11 |

**Layer 2: evidence (rule a).** Every quote is an exact, unbroken piece of the article. Only line breaks
and repeated spaces are ignored; a quote that is reworded, shortened with "...", joined from two places,
invented, or has straight quotes where the article has curly ones fails. A failure sends the reply back;
if the last reply still has one, the reply is scored and the quote is reported.

**Layer 3: rule checks.** Reported in `report.md` section 6 and `article_metrics.csv`; never used to reject
a reply:

| Rule | Check | Prompt |
|---|---|---|
| (d) place real | the whole chain is asked of OpenStreetMap's geocoder (Nominatim): the country; the state *in that country*; the city *in that state and country*. "Victoria, Canada" or "Pune, Gujarat" are not found; "Worldwide" is not a country | 5.1, G1 |
| (d) agreed form | every level that is found is written in its agreed form, its English name in OpenStreetMap; anything else is reported with the agreed form ("city 'Mangalore' is not in its agreed form; write 'Mangaluru'", "country 'USA' … write 'United States'", "state 'NSW' … write 'New South Wales'"). Scoring already uses the agreed form, so this shows how well the reply follows 5.1 | 5.1 |
| (i) recent | the end date is on or before the scan date and within the 30 days before it | 4.7 |
| (j) evidence order | quotes after the first are in article order | 10.1 |
| (k) reasoning | the first step is Step 0 and the second is Step 1 citing Rule 1 | "How to work" |
| (G4) overlapping counts | two counts with the same kind, place fields, start and end date, strain and status count the same people (a count and its part, or one count twice). Counts that differ in any of these (a total and a shorter period, influenza A and B, confirmed among suspected) are allowed | v5.2 G4 |
| (G5) one trend word | two trend items with the same place fields, strain and period have different words | v5.2 G5 |

**The place check is not a fixed list.** Any place on Earth can be checked, because each chain is asked
online. `data/place_lookups.json` only stores the answers already given, so each chain is asked once
and later runs repeat exactly. A chain that is not in it is asked online, at one request per second
(Nominatim's usage policy), and added. With `--offline`, chains not in the file keep their written values
and are reported as "could not be checked", never guessed. Delete the file to ask everything again.

Place data: © OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright).

### 5.6 Place names: one agreed form for every place

Prompt 5.1 (v5.1 and v5.2): every city, state and country has exactly one agreed form, its English
name in OpenStreetMap, the same in every item and every article. The model cannot look this up while
it reads, so the code makes sure of it (`places.agreed_names`, `places.PlaceChecker.with_agreed_names`):

1. For an item, the geocoder is asked for the country, then the state in that country, then the city in
   that state and country (each chain once; answers saved in `data/place_lookups.json`).
2. Each level that is found is replaced by OpenStreetMap's name in `PLACE_NAME_LANGUAGE` (English), or its
   main name if it has none in that language. Two spellings of one place lead to the same OpenStreetMap
   entry, so they get the same name: Bangalore and Bengaluru both become Bengaluru.
3. Only the right kind of OpenStreetMap object answers a level: a city must be a city, town or village
   (never a building, an industrial site or a district inside a city), a state a region-level unit, a
   country a country. Without this, "Vienna" matched "Vienna International Centre" and "Kyiv" matched
   "Old Kyiv". Where a country's OpenStreetMap convention records towns as administrative areas of the
   "suburb" kind (Australia: Mornington, Victoria), such an area answers the city level when no
   settlement does; a loose neighbourhood point never does, and such a value stays not found.
4. A name that is not found is asked again without a level word OpenStreetMap does not use (Province,
   District, Oblast, County, Region, ...: "Dobrich Province" is "Dobrich"). A city that is its own
   first-level unit (Vienna, Kyiv) takes the state's entry.
5. A level that is still not found keeps its written value, and the levels below it are not looked up;
   the rule check reports it. Offline, a chain not in the file, or saved by an older version without the
   kind of place, keeps its written values.

This happens in `evaluation.py` for gold and model items alike, before matching and scoring; the files
in `data/` are never changed. The written values are kept (`raw_gold_items`, `raw_model_items`) for the
rule checks. Any code that combines items into weekly signals should use the same
`with_agreed_names` with the same file, so one place is always one value. The file stores each answer
with its language, OpenStreetMap id, kind of place and the date it was asked.

## 6. Commands

Articles can be named by `article_id` or by labeling set and row, such as `Jahnavi:42`.

| Command | What it does |
|---|---|
| `python run_extraction.py` | send every labelled article except the examples |
| `... --ids Jahnavi:42,Manoj:94` | send exactly these articles |
| `... --ids-file FILE` | send the articles listed in FILE, one per line (`#` starts a comment); examples are still left out |
| `... --limit N` | only the first N of the selected articles |
| `... --exclude-file FILE` | leave out more articles |
| `... --workers N` | requests in flight at once (default 16); the 40-per-minute limit holds for any N |
| `... --run-dir DIR` | resume a run: articles that already have a reply are skipped, API failures are retried |
| `... --retry-invalid` | with `--run-dir`: also rerun articles whose reply was still invalid |
| `python evaluate_run.py RUN_DIR [--offline]` | score a run; writes `report.md` and the files of section 9 |
| `python inspect_row.py RUN_DIR ARTICLE [--article] [--reasoning] [--offline]` | one article, gold vs model, field by field, with the matching shown |
| `python compare_runs.py RUN_DIR...` | headline scores of several evaluated runs side by side; mean and range; with two runs a paired bootstrap difference |
| `python scripts/build_gold_files.py` | rebuild `data/articles.json`, `data/gold_labels.json` and the system prompt |
| `python scripts/select_examples.py --hard-runs RUN...` | re-choose the few-shot examples (writes the one set, `prompts/examples_<PROMPT_VERSION>.json`, and `few_shot_selection.md`; `--k` sets how many, default 8) |

## 7. Configuration

Secrets and overrides go in `.env` (copy `.env.example`). Everything else is in `flu_extractor/config.py`.

| Setting | Where | Default |
|---|---|---|
| `NVIDIA_API_KEY` | `.env` (required) | none |
| `NVIDIA_MODEL_ID` | `.env` | `deepseek-ai/deepseek-v4.1-flash` |
| `NVIDIA_BASE_URL` | `.env` | `https://integrate.api.nvidia.com/v1` |
| `NVIDIA_REQUESTS_PER_MINUTE` | `.env` | 40 (every request and retry counts; window 61 s) |
| `REQUEST_TIMEOUT_SECONDS` | `.env` | 900 |
| `PROMPT_VERSION` | `.env` | `v5.2`: names the prompt files (`prompts/system_prompt_<v>.txt`, `fewshot_guide_<v>.txt`, `examples_<v>.json`) and the document `build_gold_files.py` reads |
| `EXAMPLES_PATH` | `.env` | `prompts/examples_<PROMPT_VERSION>.json` (the one set; 22 examples for v5.2) |
| `RECORDS_SUFFIX` | `.env` | `_labels_v5.2.jsonl`: the gold record files read from `data/chain_of_thought/` |
| `RESULTS_DIR` | `.env` | `results/` |
| `SESSION_AFFINITY` | `.env` | unset; when set, sent as the `x-session-affinity` header on every request (Fireworks: one replica, so the prefix cache is hit) |
| `EXTRA_BODY_JSON` | `.env` | the model's request options as a JSON object; unset = NVIDIA's thinking switch, off (4.2, 8.4) |
| `TEMPERATURE`, `TOP_P`, `SEED`, `MAX_TOKENS` | `config.py` | 0, 1, 20261101, 8000 |
| `MAX_RETRIES`, `MAX_VALIDATION_RETRIES`, `STOP_AFTER_CONSECUTIVE_API_ERRORS` | `config.py` | 4, 3, 5 |
| `PLACE_NAME_LANGUAGE` | `.env` | `en`: the language of the agreed place names (5.6); `PLACE_NAME_SOURCE` in `config.py` is `openstreetmap` |
| match threshold, normalization, recency window | `matching.py`, `normalization.py`, `checks.py` | 0.8, `norm_v3`, 30 days |

## 8. Making changes

Each change below is a change of files and settings; no code needs editing unless the reply format
itself changes. After any change: `python -m unittest discover tests`, then a one-article run.

### 8.1 New or corrected labels (gold)

1. Put the record files in `data/chain_of_thought/` as `<Name><RECORDS_SUFFIX>` (one JSON record per line,
   flat or nested, section 2). For a new label version (for example `_labels_v5.3.jsonl`), set
   `RECORDS_SUFFIX` in `.env` (or the default in `config.py`).
   Remove the old files from the folder if they should no longer count.
2. If a new labeling set is added, add its name to `LABELERS` in `scripts/build_gold_files.py` and put
   its `<Name>_texts.txt` in the labeling folder; set `LABELERS` in `scripts/select_examples.py` if it
   should provide examples.
3. Run `python scripts/build_gold_files.py`. It rebuilds `data/articles.json` and `data/gold_labels.json`,
   removes every article that is in more than one set, and writes nothing if a record fails the checks
   (section 2); fix the record it names and run again.
4. If a chosen few-shot example's record changed, rebuild the examples (8.3): an example must match its
   gold record. To keep the same 8 articles with their new answers, rebuild `examples_<version>.json`
   from the new records for the same `article_id`s (this is how `examples_v5.2.json` was made).
5. Put the place names in their agreed form (5.6) with the place-fix step, then rebuild (step 3).

### 8.2 A new prompt version

1. Put the new prompt document in `prompt_versions/` as `llm_extraction_prompt_<version>.md` (the
   rules from `## Task` to the end are sent).
2. Set `PROMPT_VERSION=<version>` in `.env` (or change the default in `config.py`).
3. Run `python scripts/build_gold_files.py`: it writes `prompts/system_prompt_<version>.txt`.
4. Create `prompts/fewshot_guide_<version>.txt` (copy the current guide and adjust it to the new rules)
   and `prompts/examples_<version>.json` (8.3). A run without examples needs `examples_<version>.json`
   to contain `[]`.
5. **If the reply format changes** (a new field, a new allowed value, a new kind or trend word, a
   renamed field), change the matching constants at the top of `flu_extractor/checks.py`
   (`REPLY_KEYS`, `ITEM_FIELDS`, `KINDS`, `COUNT_TYPES`, `STATUSES`, `TREND_WORDS`, `STRAIN_NAMES`,
   `STRAIN_CODE`, `RECENT_DAYS`) and, for scoring, the field lists in `flu_extractor/normalization.py`
   (`COUNT_FIELDS`, `TREND_FIELDS`, `ALL_FIELDS`). The gold records must then follow the new format too,
   and the tests that name the old values need the new ones.
6. If the prompt's input names change (`scan_date`, `link`, `article`), change `format_article` in
   `flu_extractor/prompt.py`.

### 8.3 New few-shot examples

1. Choose them: `python scripts/select_examples.py [--k 8] [--hard-runs results/<run> ...]`. It picks
   examples from the gold records, favouring `hard_case` records and articles the model got wrong in the
   given runs, checks them, and writes the one example set `prompts/examples_<version>.json` (it
   replaces the current one; back it up first if you may want it back) and the review sheet
   `few_shot_selection.md` (the 12 best picks, coverage at 4, 8 and 12, and alternates).
2. Review the sheet. There is only ever one example set; `EXAMPLES_PATH` in `.env` can point at another
   file if you keep one elsewhere.
3. To write examples by hand, each entry needs `article_id`, `source`, `scan_date`, `link`, `article`
   (the exact text in `data/articles.json`) and `answer` (`summary`, `reasoning`, `useful`, `reason`,
   `items`, in that order). `run_extraction.py` refuses to start if an example fails the checks.
4. Examples are never scored: their articles are left out of every run automatically.
5. To take a ready-made set (as for v5.2, from the labels' `fewshot_examples_v5.2.json`): each entry's
   reply must equal its label record, its article text must equal `data/articles.json`, and its article
   must not be one removed as shared. Then put the place names in their agreed form (5.6).

### 8.4 Another model

1. On the same NVIDIA API: set `NVIDIA_MODEL_ID` in `.env` to the model's id. List the ids your key
   can use with `curl -H "Authorization: Bearer $NVIDIA_API_KEY" https://integrate.api.nvidia.com/v1/models`.
2. On another OpenAI-compatible API (DeepSeek's own, OpenAI, a local server): set `NVIDIA_BASE_URL` to
   its base URL, `NVIDIA_API_KEY` to its key and `NVIDIA_MODEL_ID` to its model name. (The names keep
   the `NVIDIA_` prefix; they work for any such API.)
3. Set the model's own request options in `EXTRA_BODY` in `config.py`, above all how to switch off a
   hidden thinking pass (see the model card); use `{}` if it has none.
4. Set `NVIDIA_REQUESTS_PER_MINUTE` to that API's limit and `REQUEST_TIMEOUT_SECONDS` to its speed.
5. Check that the model's context length holds the prefix (about 49,000 tokens with the 22 v5.2 examples) plus
   the longest article (about 35,000 tokens).
6. Run one article, read the reply with `inspect_row.py`, then run the rest.

**DeepSeek's own API** (cheaper than NVIDIA's queue for a full run: off-peak prices and a prompt cache). In `.env`:

```
NVIDIA_API_KEY=<DeepSeek platform key>
NVIDIA_BASE_URL=https://api.deepseek.com
NVIDIA_MODEL_ID=deepseek-flash
EXTRA_BODY_JSON={"thinking": {"type": "disabled"}}
```

- `deepseek-flash` is DeepSeek V4.1 Flash; the old `deepseek-v4-flash` name routes to the same model.
- **Thinking is on by default there**, so `EXTRA_BODY_JSON` is required; check that `reasoning_tokens` is 0 in
  `raw_results.jsonl` after a one-article run.
- **Prompt cache:** automatic for an identical prefix. Every request starts with the same rules and examples
  (about 48,000 tokens) and puts the article last, so later requests read the prefix from the cache. The
  first article is sent alone (warm-up) before the workers start, so the first wave does not miss the
  cache. Each record logs `cache_hit_tokens` and `cache_miss_tokens`, and the run ends with the totals and
  the hit share.
- **Off-peak:** DeepSeek bills less outside its peak hours; check the hours on its pricing page and
  start the run in that window.

**Fireworks AI** (serverless; checked 2026-11-06 with a 5-article run). In `.env`:

```
NVIDIA_API_KEY=<Fireworks key>
NVIDIA_BASE_URL=https://api.fireworks.ai/inference/v1
NVIDIA_MODEL_ID=accounts/fireworks/models/deepseek-v4p1-flash
SESSION_AFFINITY=flu-extractor-v5.2
EXTRA_BODY_JSON={"reasoning_effort": "none"}
```

- V4 Flash is not on Fireworks serverless; V4.1 Flash is. Prices per 1M tokens: input $0.30, cached
  input $0.006, output $1.20 (a `-spot` router is 30% cheaper but may answer 503 when busy). No off-peak prices.
- **Thinking is on by default** (a test call used 14 thinking tokens). `reasoning_effort: "none"`,
  `{"thinking": {"type": "disabled"}}` and `chat_template_kwargs` all gave 0.
- **The cache works only inside one replica**, so `SESSION_AFFINITY` sends the same `x-session-affinity`
  header on every request. In the 5-article check, requests 2-5 each read 50,046 prompt tokens from the
  cache (`usage.prompt_tokens_details.cached_tokens`). Without cache hits a full run costs about $16
  instead of about $2.

### 8.5 Place names

The agreed form of every place (5.6) comes from OpenStreetMap; no name list is kept in the code.
- To use the names of another language, set `PLACE_NAME_LANGUAGE` in `.env` (for example `fr`); saved
  answers in another language are asked again automatically.
- To refresh the names (OpenStreetMap changes over time), delete `data/place_lookups.json`; the next
  evaluation asks every chain again, at one per second. If you refresh, rerun the data fix too, so the
  gold records keep the same names as the file.
- New data needs no list either: any new place is looked up the first time it is seen.

### 8.6 Scoring settings

The match threshold (`MATCH_THRESHOLD`, 0.8) and the pairing are in `flu_extractor/matching.py`; the
country names in `flu_extractor/normalization.py`; the recency window in `flu_extractor/checks.py`.
Changing them changes every score, so each has a version string (`MATCHING_VERSION`,
`NORMALIZATION_VERSION`) that is written into `evaluation_summary.json`; change it with the setting.
A finished run can be re-scored at any time with `evaluate_run.py`, without new API calls.

## 9. Output files

Per run, in `results/run_<date>_<time>/` (ignored by git):

| File | Content |
|---|---|
| `raw_results.jsonl` | one line per article: model, raw reply, parsed reply, finish reason, tokens (with cache hits, misses and thinking tokens when the API reports them), seconds, requests, validation retries and problems, errors |
| `run_config.json` | model, base URL, decoding settings, prompt, guide and examples files with SHA-256 hashes, rate limit, selection, start time |
| `report.md` | 1 task 1 table; 2 recall, precision, F1; 3 accuracy, exact rate, field accuracy (each as mean, interval, median, quartiles, share at 1 and 0, articles covered); 4 article outcomes; 5 where misses and extras come from; 6 coverage and checks |
| `plot_article_counts.png`, `plot_article_metrics.png`, `plot_field_accuracy.png`, `plot_article_buckets.png` | the charts of section 5.3 |
| `evaluation_summary.json` | the per-article summaries of every metric, the buckets and the counts, for every scored article and with inactive-only items removed, plus the settings and versions (read by `compare_runs.py`) |
| `article_metrics.csv` | per article: status, gold and model `useful`, items, hits, misses, extras, repeated extras, recall, precision, F1, accuracy, exact hits, outcome bucket |
| `matched_items.csv` | per hit: similarity, exact, wrong fields, every field result, gold and model values and evidence |
| `missed_items.csv` | per miss: the gold item, and its closest model item with the similarity (below 0.8, or taken by another gold item) |
| `additional_items.csv` | per extra, with its repeat label |
| `duplicate_candidates.csv` | candidate groups in gold (with the review decision) and in the model items |
| `field_error_summary.csv`, `kind_error_summary.csv`, `error_examples.md` | errors by field, by kind, and examples of each error type |

Read `report.md` section 6 first (what could not be scored), then sections 2-4 and the charts.

## 10. Testing

```bash
python -m unittest discover tests
```

123 tests, no API key and no internet needed (the geocoder is faked). They cover the three check
layers: the format with every fixed value, the evidence, and the rule checks (`test_checks.py`); normalization, the pairing,
the 0.8 threshold, best-partners-first pairing with its tie rule, field results, duplicates, per-article metrics and their summaries, which articles each metric covers,
article outcomes, the charts, bootstrap and evidence checks (`test_evaluation.py`); the 40-per-minute limiter
API retries, the cache and thinking token counts (DeepSeek and OpenAI style), the session-affinity header and `EXTRA_BODY_JSON` (`test_llm_client.py`); the whole-chain place check, the agreed form of any place
(two spellings of one place become one value and score as the same place), the saved answers, offline mode
(`test_places.py`); and the request format, validation retries (format and
evidence problems are sent back), articles without flu being sent, article selection, scoring a run,
the warm-up before the workers, the stop after API errors, the token totals, the data build with duplicate removal, and the real `data/` and `prompts/` files passing the input
checks (`test_pipeline.py`).

The live API is not covered by tests: check it with a one-article run (section 1, step 2).

## 11. Layout

```
data/              chain_of_thought/*_labels_v5.2.jsonl (gold source), articles.json, gold_labels.json, place_lookups.json
prompts/           ACTIVE: system_prompt_v5.2.txt, fewshot_guide_v5.2.txt, examples_v5.2.json (the one example set, k = 22)
prompt_versions/   archive of the full prompt documents (build_gold_files.py reads the active version)
few_shot_selection.md  review sheet of how the active examples were chosen (written by select_examples.py)
results/           one folder per run (ignored by git)
scripts/
  build_gold_files.py   build data/ from the label records and the article texts; refresh the system prompt
  select_examples.py    choose the few-shot candidates
tests/             unit tests
flu_extractor/
  config.py        paths, model and decoding settings
  data_loading.py  read articles, gold labels and label record files (flat or nested); resolve "Jahnavi:42" to an id
  prompt.py        build the chat messages
  llm_client.py    the only code that calls the API; the shared 40-per-minute limiter and retries
  extractor.py     one article -> one validated log record (repair, re-ask, never crash)
  checks.py        the three check layers: format, evidence, rule checks (with v5.2's G4 and G5)
  data_checks.py   input files in the required format (articles, gold, examples)
  places.py        is a city/state/country chain real, and its agreed form (5.1)? (geocoder, answers saved in data/place_lookups.json)
  normalization.py comparable values, fields per kind (norm_v3)
  matching.py      candidates, similarity, one-to-one best-partners-first pairing (matching_v3)
  field_scoring.py field results of a matched pair
  duplicates.py    duplicate groups, duplicate extras, gold adjudication
  evidence.py      evidence checks on model items
  metrics.py       counts, usefulness table, summaries over articles, bootstrap
  evaluation.py    score a run: per article, per population, diagnostics
  report.py        write report.md, evaluation_summary.json and the CSV files
  plots.py         the four charts of the per-article results
run_extraction.py, evaluate_run.py, inspect_row.py, compare_runs.py   the command-line tools
```

## 12. Known limitations

- **Gold is LLM-written.** The v5.2 labels were written by Claude agents from the rules and not
  reviewed line by line, so the score partly measures agreement with Claude. Checked on 6 Nov against
  Jahnavi's reviewed chain-of-thought v3 records (same prompt): `useful` agrees on 98.2% of the 1,200
  articles (Cohen's kappa 0.95); items match exactly in 70% of the articles with items (mean per-article
  F1 0.85). The rule checks report 101 evidence-order problems (j) and 2 overlapping counts (G4) in the
  labels.
- **Slow and quota-limited endpoint.** NVIDIA's queue for this model is slow (minutes per reply)
  and the free key has a daily quota. Runs are resumable.
- **Not fully repeatable.** Greedy settings remove sampling on our side, but a hosted model can
  still return different text for the same request. Measure it with two runs before trusting
  small differences.
- **Context length.** The prefix (rules plus 22 examples) is about 49,000 tokens; the longest
  article adds about 33,000 more, so the longest request is about 90,000 tokens with the reply. A request over the model's limit fails as an API error (not
  scored, never cut).
- **Matching threshold.** 0.8 is set by decision, not yet checked on reviewed pairs. Look at misses whose
  closest model item is just under it (`missed_items.csv`) before trusting small differences.
- **The agreed form depends on OpenStreetMap.** It is OpenStreetMap's choice, even where a common name
  differs (it writes Gurgaon, Bhubaneshwar, Ivory Coast); a value OpenStreetMap does not find keeps its
  written form and is reported. Offline, chains not in the saved answers keep their written values, so
  run the first evaluation of new data online.
- **Sample mix.** The articles were drawn half from likely useful and half from likely not useful,
  so scores do not carry over directly to raw news.
