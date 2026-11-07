# flu_signal

Written for: the capstone team, to see how the LLM replies become weekly signals for change-point detection.

## What is built so far

Step 1: two tables, written to `output/` (gitignored).

- `articles.csv`: one row per pool article (50,640). It says where the answer came from (`gold`, `llm`
  or `not_sent`), whether the article is useful, and which country-seasons it counts in.
- `items.csv`: one row per item about a cohort country (19,129).
- `tables_report.json`: the counts below.

## Country rule

An article can mention several countries. The two signals count it differently.

- **Frequency signal:** the article counts in a country-season when the season's window holds the article's
  date AND the article's GDELT locations mention that country. Column `frequency_seasons`.
  `country_seasons` in `repo/output/pool/season_assignments.jsonl` alone is not enough: it lists every window
  holding the date, mentioned or not. The mentions come from `locations` in `pooled_articles.jsonl`.
- **Content signal:** each item counts toward its own `country` field, in that country's season whose
  window holds the article's scan date. Column `content_seasons`. Items about other countries are left out.

Example: an Indian article says "flu cases rising in Kerala; the US CDC also reports a severe season".
It counts for IND and USA in both signals. It does not count for AUS just because it names an Australian company.

## Numbers

| | Articles |
| --- | --- |
| Pool (one per story) | 50,640 |
| Answer from gold | 1,120 |
| Answer from the LLM pool run | 39,248 |
| Not sent (keyword filter drop, counted as not useful) | 10,272 |
| Useful | 9,688 |

Items kept: 19,129. Left out: 2,479 about other countries, 674 dated outside their country's window.

| Country | Frequency articles | Articles with items | Items |
| --- | --- | --- | --- |
| USA | 40,693 | 7,310 | 16,619 |
| AUS | 4,115 | 604 | 1,104 |
| IND | 4,964 | 536 | 1,334 |
| BRA | 920 | 42 | 58 |
| KEN | 238 | 5 | 8 |
| IDN | 448 | 6 | 6 |

BRA, KEN and IDN have almost no content (0–4 articles per season, except BRA-2023 with 35). So the main
lead-time comparison uses USA, AUS and IND (22 seasons). A second table covers all 38 seasons, with no
content signal counted as "not detected".

## Step 2: weekly signals (`build_weekly.py`)

`output/weekly_signals.csv`: 12 rows per season (weeks -10 to +1; week 0 starts on the FluNet onset date;
the window's last day, onset + 14, goes into week +1). Each row has the split (`calibration` up to 2021,
`held_out` from 2022) and `headline` (USA, AUS, IND). The columns count articles, not items: an article
adds 1 to a column in the week of its scan date if at least one of its items for that season passes the test.

| Column | An article counts when |
| --- | --- |
| `freq_articles` | it counts for the season (date in window, country mentioned). The baseline. |
| `content_articles` | it has any item for the season |
| `seasonal_articles` | it has a seasonal item: the strain is not bird flu (H5, H7, H9, H10, "avian") or a swine variant ("v") |
| `activity_articles` | a seasonal item is a count (cases, deaths, hospitalized) or a trend that is present, moderate, high or rising |
| `rising_articles` | a seasonal item is a trend that is rising or high |
| `avian_articles` | it has a bird flu or variant item. A check, not a candidate. |

Bird flu is left out because prompt rule 1.3 makes items for animal outbreaks linked to food. They are not
a sign of the seasonal epidemic (IND-2021 has 42 avian articles in week -3).

## Step 3: change-point detectors (`bcp.py`, `bocpd.py`, `run_detectors.py`)

Both work on Anscombe-transformed counts, 2·sqrt(x + 3/8), so that count noise is about the same at 3 or
300 articles a week. Both look only for a rise.

- **BCP** (Barry & Hartigan, as in Ganser et al. 2022). Every split of the 12 weeks into blocks
  (2,048 splits) is weighed exactly, so there is no MCMC. Priors p0 = w0 = 0.2 as in R `bcp`.
  A small within-block floor stops splits that fit repeated counts perfectly (0, 0, 0) from winning.
  - retrospective: the whole window at once, as Ganser did;
  - prospective: rerun on the weeks seen so far, each week.
- **BOCPD** (Adams & MacKay 2007), online by design, so prospective only. Normal-Gamma model; the prior
  comes from the first 3 weeks, and no alarm is raised in them. A Poisson model was planned, but news
  counts vary far more than Poisson allows, so it would alarm almost every week.

An alarm needs the posterior probability to reach the cut-off (default 0.5, tuned in step 4). On random
flat series, the false-alarm rate at 0.5 is 1-11% depending on the count level and the extra noise.

**Sustain rule.** A one-week spike (30, 31, 90, 30, 29) would ring every detector. So a rise must last
`sustain_weeks` weeks (1, 2 or 3, tuned in step 4): each of those weeks must be above the mean of the
weeks before the change. A week-by-week run confirms the alarm only once those weeks are seen, so sustain
2 raises it 1 week later and sustain 3 raises it 2 weeks later. A rise that fails is skipped, and the
search goes on. Sustain 1 gives exactly the old behaviour (checked: the same 300 calibration detections).

The BCP sum is also checked against a second calculation with scipy `quad` (a test). R is not installed,
so there is no direct comparison with R `bcp`.

`run_detectors.py` runs calibration seasons only and writes `output/detections_<split>_sustain<n>.csv`.
`--final` runs the held-out seasons, once, after the signal, cut-off and sustain are frozen.

## Step 4: tuning on calibration (`tune.py`, `scoring.py`)

Every free choice is fixed on the 13 calibration seasons of USA, AUS and IND (2015–2021) before any
held-out season is run.

**Score.** Per season, with the alarm week a (onset = week 0):

- hit: a in weeks −4 to +1;
- false alarm: a before week −4 (too early to be this season's rise);
- miss: no alarm.

A setting's score is hits − false alarms. Ties go to more hits, then fewer false alarms, then an earlier
median alarm week, then the plainer setting (cut-off nearest 0.5, smaller sustain, margin 0).

**Grid.** 5 signals × 3 methods × cut-offs 0.3–0.9 × sustain 1–3 × margin 0 or 1 = 630 settings
(`output/tuning_calibration.csv`). The margin asks the rise to be at least 1 noise unit above the earlier
level. Content and frequency are tuned separately, with the same grid and score. Only the week-by-week
methods can be chosen. BCP retrospective is scored for comparison with Ganser only.
BCP's posterior is cached per series, so the grid takes about 20 s.

**Ties on cut-off.** When neighbouring cut-offs of the winner score the same (a plateau), the middle one is
frozen (decided 2026-11-07). An edge cut-off is the most likely to flip on new seasons: for frequency, going
from 0.4 to 0.3 adds a second false alarm at week −7.

**Result (2026-11-07):**

| | Content | Frequency |
| --- | --- | --- |
| Signal | `rising_articles` | `freq_articles` |
| Method | BCP prospective | BOCPD |
| Cut-off, sustain, margin | 0.4 (plateau 0.3–0.5), 1, 0 | 0.4 (plateau 0.3–0.5), 1, 0 |
| Hits / false alarms / misses | 8 / 0 / 5 | 5 / 1 / 7 |
| Score | 8 | 4 |
| Score at cut-offs 0.3 … 0.9 | 8 8 8 7 7 6 5 | 4 4 4 3 1 0 0 |

Content alarm weeks at 0.4: USA-16 −2, USA-17 0, USA-18 0, USA-19 −1, AUS-17 0, IND-17 +1, IND-18 +1,
IND-21 0; no alarm in AUS-16, AUS-18, IND-15, IND-16, USA-15.

**Read these numbers with care:**

- **Calibration favours content.** Content's winner is the best of 336 settings (4 signals × 84), frequency's
  the best of 84, and only 6 of the 336 reach score 8. So the 8 vs 4 gap is optimistic. Only the held-out
  comparison is a fair test.
- **No alarm can ring before week −7.** The week-by-week detectors need 4 weeks of data first. So false alarms
  can only fall in weeks −7 to −5 (3 weeks), against a hit zone of 6 weeks.
- **Sustain and margin did not matter** for the two winners (sustain 1 and margin 0 won; margin 1 ties).
  Sustain 2 helped only `activity_articles`.

The winners are in `output/frozen_settings.json` with their calibration alarm weeks, the tie-break and the
git commit (`-dirty` when the code was not committed). `tune.py` will not replace that file without
`--force`. `run_detectors.py --final` checks that each frozen setting is one `tune.py` could choose (a
week-by-week method and values from the grid), then runs only those two settings, on the held-out seasons
and on all 20 calibration seasons (for the all-38 table). It refuses to run without the file.

## Inputs

Read only, from the other worktrees: `llm-extractor/results/pool_combined/raw_results.jsonl`,
`llm-extractor/data/gold_labels.json`, `usefulness_filter/output/filter_decisions.csv`,
`repo-sampling/sampling/output/all_articles_buckets.csv`, and `repo/output/pool/season_assignments.jsonl`
and `season_windows.json`. Paths are in `signal_config.py`.

## Use

Run from this folder, with the extractor's venv:

```bash
../llm-extractor/.venv/bin/python -m unittest discover tests   # 65 tests, offline
../llm-extractor/.venv/bin/python build_tables.py
../llm-extractor/.venv/bin/python build_weekly.py
../llm-extractor/.venv/bin/python run_detectors.py --cutoff 0.5 --sustain-weeks 2 --margin 1   # calibration only
../llm-extractor/.venv/bin/python tune.py                       # writes the frozen settings
../llm-extractor/.venv/bin/python run_detectors.py --final      # held-out, once (step 5)
```
