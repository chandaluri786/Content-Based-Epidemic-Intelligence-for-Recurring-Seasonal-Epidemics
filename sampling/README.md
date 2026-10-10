# Sampling: bucketing the articles and drawing the 1,200 to label

This folder puts every stored article into a bucket with word rules, then draws 1,200 articles to label (600 likely useful, 600 likely not useful). A bucket only decides which articles people read. It is never the label.

The rules and the reasons behind them are in `Project Documents /sampling_algorithm.md`. The labeling rules are in `Project Documents /sampling_and_labeling_guide.md`.

## Files

| File | What it does |
|---|---|
| `patterns.py` | The word patterns (regular expressions), built from reading the 36,508 stored articles and extended after reading the ones the first version missed |
| `bucketing.py` | Gives one article one bucket, checking the rules in order; the first match wins |
| `run_sampling.py` | Reads the articles, buckets them, draws the sample, saves the files |

## How to run

You need Python 3.10 or newer. No extra packages.

```bash
cd sampling
python run_sampling.py
```

It takes a few minutes. Options: `--data-dir` (default `../../extracted_articles`), `--out-dir` (default `sampling/output`), `--seed` (default 42; the same seed and data give the same sample).

Saved in `output/`:

| File | Contents |
|---|---|
| `sample_1200.csv` | The sample: id, link, scan date, country, year, bucket, reason |
| `sample_1200.jsonl` | The same plus the article text, one per line. Give this to labelers and the LLM. |
| `all_articles_buckets.csv` | Every article and its bucket, for checking the rules |

## How it works

1. **Read.** `run_sampling.py` reads every `matched_articles.jsonl` and notes which of the six study countries each article is tagged with.
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

   | Kind | Examples it catches | Patterns |
   |---|---|---|
   | Number next to a case word | "12 cases", "influenza-associated pediatric deaths", "92 pediatric deaths" | `COUNT_A`, `COUNT_B` |
   | Verb before the number | "killed more than 800 people", "sickened 40 children" | `COUNT_C` |
   | Part of a group is sick now | "20 percent of students and staff are sick with flu" | `SICK_NOW` |
   | Case event without a number | "first infection", "flu cases were confirmed", "died of", "tested positive" | `EVENT_C` |
   | One person's illness | "treated for the flu", "rushed to hospital with the flu", "battling the flu" | `INDIVIDUAL` |
   | How flu is changing | "influenza is widespread", "flu is spreading", "early arrival of the flu season", "sporadic", "minimal" | `TREND_NEAR`, `STATUS` |
   | Health response | "school closures", "screening of people", "task force" | `RESPONSE` |

   Sentences are ignored for counting when they:
   - are about the past (last year, 1918, a year two or more before the scan), unless they only compare with it ("outpacing the numbers at this time last year", pattern `COMPARE`)
   - are a rate, an annual or yearly statistic, or a vaccine-benefit sentence, unless they say "now" (this week, so far, this season, this year)
   - are advice or a "what if" (`ADVICE`, `HYPO`), such as "avoid people who are sick with flu"

   "Centers for Disease Control and Prevention" is not treated as vaccine or prevention wording.
3. **Draw.** `QUOTAS` in `run_sampling.py` sets how many to take from each bucket. Inside a bucket, articles are grouped by country and year and taken one group at a time in turn, so every country and year is covered. An article's country is the rarest of its study countries, so Kenya and Indonesia are not hidden behind the USA.
4. **Save.**

To change how many are drawn from a bucket, edit `QUOTAS`. To change what a bucket means, edit its pattern in `patterns.py` or its rule in `bucketing.py`.

## Adding or changing patterns

1. Find articles in the wrong bucket in `output/all_articles_buckets.csv`.
2. Add the wording to the matching pattern in `patterns.py`, or add a new pattern and use it in `bucketing.py`.
3. Rerun and check three things: the example now lands in the right bucket, the bucket counts did not jump, and a fresh random read of the bucket (about 25 articles) is still mostly correct.

## Latest run (seed 42, 36,508 articles, repeats included)

| Bucket | Articles |
|---|---|
| N_no_flu_text | 6,535 |
| N_other_flu_mention | 4,841 |
| X_spam_stub | 3,964 |
| N_animal_flu | 3,545 |
| N_awareness | 3,512 |
| X_too_short | 3,466 |
| P_A1_counts | 2,717 |
| N_other_disease | 2,700 |
| P_A2_case_event | 1,702 |
| P_B_trend_response | 1,094 |
| N_history_only | 665 |
| N_research | 600 |
| N_flu_idiom | 567 |
| N_business_policy | 289 |
| X_listing_garbled | 244 |
| Z_zoonotic_human | 67 |

Counts include the repeated copies. On the 21,506 unique texts, the new patterns moved about 540 articles from "other flu mention" into the useful buckets and left the numbers bucket at about 83% correct in a fresh read of 25.

The sample has 1,200 articles: 600 from the useful buckets (numbers 240, trend 200, events 130, bird flu in people 30) and 600 from the not-useful buckets. By country: USA 301, India 267, Australia 240, Brazil 178, Indonesia 124, Kenya 90. By year: 2015 373, 2016 504, 2017 323.

## Things to know

- **Repeats are not removed here.** The code assumes the articles were already de-duplicated. The current `extracted_articles` folder still has about 15,000 exact repeats, and the first run's sample had 89 repeated texts out of 1,200. Point `--data-dir` at the de-duplicated data.
- The rules were checked by reading small samples: about 83 to 88% of `P_A1_counts` and about half of `P_B_trend_response` were really useful. Expect fewer than 600 useful articles after labeling.
- **One story can fill a bucket.** The 2016 news about Prince having the flu appears in about 370 of the 1,300 unique articles in `P_A2_case_event`. Only 19 of the 570 useful-bucket articles in the sample come from it, but watch for other single stories.
- Single-person illness ("treated for the flu", "battling the flu") counts as useful. About half of those matches are real; the rest are old anecdotes or advice. Labelers decide.
- There is no `P_C_symptoms_only` bucket. Nothing in the data matched it convincingly.
- This does not balance the sample by early, middle or late season, and it does not make the development and test split. Those would be separate steps.
- Page text was downloaded in 2026, so some pages no longer match what was published.
