# Sampling: bucketing the articles and drawing the 1,200 to label

This folder puts every eligible article into a bucket with word rules, then draws 1,200 articles to label (600 likely useful, 600 likely not useful). A bucket only decides which articles people read. It is never the label.

It reads the de-duplicated pool built by `prepare_pool.py` on the `data-extraction-pipline` branch. An article is eligible only if it is assigned to a country-season (`sampling_season`), and only one article is kept per near-duplicate group, so the same story can't be drawn twice.

The rules and the reasons behind them are in `sampling_algorithm.md` in the team's Project Documents folder (not in this repo). The labeling rules are in [`../sampling_and_labeling_guide.md`](../sampling_and_labeling_guide.md).

## Files

| File                   | What it does                                                                                                                                        |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `patterns.py`          | The word patterns (regular expressions), built from reading the 36,508 stored articles and extended after reading the ones the first version missed |
| `bucketing.py`         | Gives one article one bucket, checking the rules in order; the first match wins                                                                     |
| `run_sampling.py`      | Reads the pool, buckets the eligible articles, draws the sample, saves the files                                                                    |
| `test_run_sampling.py` | Tests for reading the pool and drawing (`pytest sampling/`)                                                                                         |
| `make_label_packets.py` | Splits the sample into one labeling packet per team member (see [Labeling packets](#labeling-packets))                                             |
| `test_make_label_packets.py` | Tests for the split: even mix, round-1 picks, check rotation, same seed gives same packets                                                    |
| `HOW_TO_LABEL.md`      | Short instructions for labelers, copied into every packet folder                                                                                    |
| `make_dev_test_split.py` | Splits the 1,200 labeled articles into dev (about 400) and test (about 800) (see [Dev/test split](#devtest-split))                              |
| `test_make_dev_test_split.py` | Tests for the dev/test split: sizes, useful share, same-story groups, rule coverage, same seed gives same split                             |
| `split/`               | The frozen split (`dev_test_split.csv`) and its report (`split_report.md`); kept in git                                                            |

## How to run

You need Python 3.10 or newer. No extra packages.

```bash
python sampling/run_sampling.py --pool-dir /path/to/output/pool
```

`--pool-dir` is the `prepare_pool.py` output folder. It must hold `pooled_articles.jsonl`, `season_assignments.jsonl`, `near_dup_groups.jsonl` and `season_windows.json`. Other options: `--out-dir` (default `sampling/output`), `--seed` (default 42; the same seed and pool give the same sample).

Saved in `output/`:

| File                       | Contents                                                                                                                                                                 |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `sample_1200.csv`          | The sample: id, link, scan date, country, season, phase, year, bucket, reason, near-duplicate group and its size                                                         |
| `sample_1200.jsonl`        | The same plus the article text and GDELT's place mentions (`locations`: name, country code, offset), one per line. Give this to the LLM; labelers get the packets below.                                                                      |
| `all_articles_buckets.csv` | Every eligible article and its bucket, for checking the rules                                                                                                            |
| `bucket_sizes.json`        | How many eligible articles each bucket held, overall and by country. The sample takes a fixed number per bucket, so use these to turn sample rates into pool-wide rates. |

## Labeling packets

```bash
python sampling/make_label_packets.py
```

Reads `output/sample_1200.jsonl` and writes `output/labeling/` (options: `--sample`, `--out-dir`, `--seed`, default 42). The labelers are listed in `LABELERS` in the script.

- **Split.** Every bucket is dealt evenly across the four labelers, so each gets 300 articles with the same mix (about 150 likely useful). Likely-useful articles need extraction and take much longer. Giving each person their own buckets would make the work uneven, and nobody would see every kind of article.
- **Round 1.** Each labeler's first 20 rows are their own (10 likely useful, 10 not, spread over the buckets). The next 20 are the following labeler's round-1 articles, labeled blind: Jahnavi checks Thanya, Thanya checks Manoj, Manoj checks Aditya, Aditya checks Jahnavi. That gives 80 double-labeled articles for the agreement check. Round 2 is the remaining 280.
- **No buckets in the packets.** A bucket is a guess, and seeing `P_…` would push labelers toward "useful". Only `assignment_key.csv` holds the buckets. It is for the coordinator and should not be shared with labelers.

| File | Contents |
|---|---|
| `<name>_texts.txt` | The articles to read, numbered to match the label sheet. Each header shows the scan date, the tagged country and season, the places GDELT found, and the link. |
| `<name>_labels.csv` | One row per article: `useful`, `disease`, `strain`, `causes`, `symptoms`, `labeler`, `notes` (blank, to fill in) |
| `<name>_items.csv` | One row per extracted statement, linked by `article_id` (header only, to fill in) |
| `assignment_key.csv` | Every article's owner, whether it is in round 1, who checks it, and its bucket |
| `HOW_TO_LABEL.md` | The labeler instructions |

## Dev/test split

Once every sheet follows `sampling_and_labeling_guide.md`, the 1,200 labeled articles are split once into dev (one third) and test (two thirds):

```bash
python sampling/make_dev_test_split.py
```

It reads `output/sample_1200.jsonl` and the four labelers' `output/labeling/<name>_{labels,items}.csv`, and writes `split/dev_test_split.csv` (`article_id, split, labeler, useful, bucket, country, year, story_group, tags`) and `split/split_report.md`.

- **Natural mix.** Dev and test both keep the real share of useful articles (about 26%), so dev scores predict test scores. The prompt's few-shot examples are picked from dev only, at about half useful, and are then left out of dev scoring.
- **Stratified.** Quotas are taken one level at a time: useful or not, then bucket, then labeler, then country.
- **Same story, same set.** Articles whose texts share at least 30% of their 5-word phrases, share an evidence sentence, or report the same figure (same kind, a number of at least 10, same place, end dates within 3 days) form one story group, and a group goes to one set.
- **Every rule in dev.** Each article is tagged with the rules it exercises (from its items, its bucket and the harmonising notes). Matched story groups are then swapped until every tag has min(3, half its total) dev articles.
- **Frozen.** The split is in git. The script refuses to overwrite it; use `--force` only before prompt tuning starts. Never look at model errors on test while tuning.

The first split (seed 42): dev 397 articles (104 useful), test 803 (208 useful); 21 story groups; 6 swaps; every tag met. The 3 round-1 check rows that still disagree with the owner are listed in the report, and the owner's label is used. After the label corrections of 2026-10-19 (check rows settled, two fixes while choosing prompt examples, the second rulebook audit) it is dev 107 useful, test 211 useful, with every tag still met; the report lists each correction.

## How it works

1. **Read.** `run_sampling.py` keeps the pool articles that have a `sampling_season`, then picks one at random from each near-duplicate group. Each article gets its country and season from the pool, and a phase from its date: `early` (10 to 6 weeks before onset), `late` (5 to 1 weeks before) or `post` (onset week to 2 weeks after).
2. **Bucket.** `bucketing.py` checks, in order:
   1. Junk: spam or blocked page (`X_spam_stub`), under 300 characters (`X_too_short`), index page (`X_listing_garbled`).
   2. No flu word (`N_no_flu_text`).
   3. Mostly bird or animal flu (`N_animal_flu`), or `Z_zoonotic_human` if a sentence reports a human case.
   4. Stomach flu, dog flu and similar (`N_flu_idiom`).
   5. Another disease mentioned more than flu (`N_other_disease`).
   6. A current case count (`P_A1_counts` with a number, `P_A2_case_event` without one).
   7. A trend, quiet-season or health-response statement (`P_B_trend_response`).
   8. History only (`N_history_only`), research (`N_research`), business or policy (`N_business_policy`), vaccine or prevention wording (`N_awareness`).
   9. Anything else that mentions flu (`N_other_flu_mention`).

   To judge steps 6 and 7, it looks only at sentences that mention flu (or sit next to one) and skips animal-only sentences, other diseases and research results. These are the kinds of wording that count:

   | Kind                        | Examples it catches                                                                                     | Patterns               |
   | --------------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------- |
   | Number next to a case word  | "12 cases", "influenza-associated pediatric deaths", "92 pediatric deaths"                              | `COUNT_A`, `COUNT_B`   |
   | Verb before the number      | "killed more than 800 people", "sickened 40 children"                                                   | `COUNT_C`              |
   | Part of a group is sick now | "20 percent of students and staff are sick with flu"                                                    | `SICK_NOW`             |
   | Case event without a number | "first infection", "flu cases were confirmed", "died of", "tested positive"                             | `EVENT_C`              |
   | One person's illness        | "treated for the flu", "rushed to hospital with the flu", "battling the flu"                            | `INDIVIDUAL`           |
   | How flu is changing         | "influenza is widespread", "flu is spreading", "early arrival of the flu season", "sporadic", "minimal" | `TREND_NEAR`, `STATUS` |
   | Health response             | "school closures", "screening of people", "task force"                                                  | `RESPONSE`             |

   Sentences are ignored for counting when they:
   - are about the past (last year, 1918, a year two or more before the scan), unless they only compare with it ("outpacing the numbers at this time last year", pattern `COMPARE`)
   - are a rate, an annual or yearly statistic, or a vaccine-benefit sentence, unless they say "now" (this week, so far, this season, this year)
   - are advice or a "what if" (`ADVICE`, `HYPO`), such as "avoid people who are sick with flu"

   "Centers for Disease Control and Prevention" is not treated as vaccine or prevention wording.

3. **Draw.** `QUOTAS` in `run_sampling.py` sets how many to take from each bucket. Inside a bucket, articles are grouped by country, season and phase and taken one group at a time in turn, so every country-season and every part of the window is covered, and Kenya and Indonesia are not hidden behind the USA.
4. **Save.**

To change how many are drawn from a bucket, edit `QUOTAS`. To change what a bucket means, edit its pattern in `patterns.py` or its rule in `bucketing.py`.

## Adding or changing patterns

1. Find articles in the wrong bucket in `output/all_articles_buckets.csv`.
2. Add the wording to the matching pattern in `patterns.py`, or add a new pattern and use it in `bucketing.py`.
3. Rerun and check three things: the example now lands in the right bucket, the bucket counts did not jump, and a fresh random read of the bucket (about 25 articles) is still mostly correct.

## First run (seed 42, 36,508 articles from 2015–2017, repeats included)

| Bucket              | Articles |
| ------------------- | -------- |
| N_no_flu_text       | 6,535    |
| N_other_flu_mention | 4,841    |
| X_spam_stub         | 3,964    |
| N_animal_flu        | 3,545    |
| N_awareness         | 3,512    |
| X_too_short         | 3,466    |
| P_A1_counts         | 2,717    |
| N_other_disease     | 2,700    |
| P_A2_case_event     | 1,702    |
| P_B_trend_response  | 1,094    |
| N_history_only      | 665      |
| N_research          | 600      |
| N_flu_idiom         | 567      |
| N_business_policy   | 289      |
| X_listing_garbled   | 244      |
| Z_zoonotic_human    | 67       |

Counts include the repeated copies. On the 21,506 unique texts, the new patterns moved about 540 articles from "other flu mention" into the useful buckets and left the numbers bucket at about 83% correct in a fresh read of 25.

The sample has 1,200 articles: 600 from the useful buckets (numbers 240, trend 200, events 130, bird flu in people 30) and 600 from the not-useful buckets. By country: USA 301, India 267, Australia 240, Brazil 178, Indonesia 124, Kenya 90. By year: 2015 373, 2016 504, 2017 323.

## Things to know

- **The shared sample is the official one.** The `sample_1200.csv` and `sample_1200.jsonl` given to the team were drawn on 2026-10-10 by a version of `run_sampling.py` from just before commit 2c3111e. Rerunning the committed script on the same pool with seed 42 gives the same eligible articles and bucket sizes but a different 1,200. Labeling uses the shared files, so keep a copy of them (`output/` is not in git) and don't redraw. The `locations` field was added to the shared `sample_1200.jsonl` afterwards by looking each article up in the pool, without changing anything else.

- **Repeats.** Exact repeats are removed by `prepare_pool.py dedup`; near-copies (the same wire story on many sites) by keeping one article per near-duplicate group. The first run, on raw folders, had 89 repeated texts out of 1,200.
- The rules were checked by reading small samples: about 83 to 88% of `P_A1_counts` and about half of `P_B_trend_response` were really useful. Expect fewer than 600 useful articles after labeling.
- **One story can fill a bucket.** In the first run, the 2016 news about Prince having the flu appeared in about 370 of the 1,300 unique articles in `P_A2_case_event`. Near-duplicate groups now catch copies of one wire story, but different write-ups of the same news are separate articles, so still watch for single stories.
- Single-person illness ("treated for the flu", "battling the flu") counts as useful. About half of those matches are real; the rest are old anecdotes or advice. Labelers decide.
- There is no `P_C_symptoms_only` bucket. Nothing in the data matched it convincingly.
- The development and test split is made after labeling by `make_dev_test_split.py` (see [Dev/test split](#devtest-split)).
- Page text was downloaded in 2026, so some pages no longer match what was published.
