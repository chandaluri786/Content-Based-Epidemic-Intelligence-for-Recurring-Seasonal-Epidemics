# flu_signal

Written for: the capstone team, to see how the LLM replies become weekly signals for change-point detection,
what the test found, and how to check it yourself.

## In short

**Question:** does the *content* of flu news (what the LLM extracted) show a seasonal flu onset earlier than a
plain *count* of flu news? WHO FluNet onset dates are the truth.

| Step | What it does | Script |
| --- | --- | --- |
| 1 | LLM replies become one row per article and one per item | `build_tables.py` |
| 2 | 12 weekly counts per country-season, on ISO weeks, labelled −10 to +1 around the onset | `build_weekly.py` |
| 3 | BCP and BOCPD look for the week the counts jump | `bcp.py`, `bocpd.py`, `run_detectors.py` |
| 4 | Pick the best setting for content and for counts on 2015–2021, and freeze it | `tune.py` |
| 5 | Test the frozen settings once on 2022–2024; leave one season out | `run_detectors.py --final`, `report_results.py`, `loso.py` |
| after | Post-hoc checks, designed after seeing the results | `post_hoc.py`, `transform_check.py` |

**Result:**

- **Main evaluation, leave one season out (LOSO, 22 seasons):** content leads 11 vs 5, but it is not
  significant (wins 9 – 6 – 7, p = 0.61).
- **Pre-registered by-year test (9 held-out seasons):** content is **not** better, 0 vs 3.
- **Content alarms earlier than counts.** With an early limit of −5 or wider it wins most seasons (LOSO p ≈ 0.004).
  But that limit was picked after the results, so it is a description, not a test.
- **The advantage needs the variance stabiliser.** On raw counts frequency wins instead (post-hoc check 4).

**Key terms**

- **Setting:** signal + method (BCP or BOCPD) + cut-off + sustain + margin. Tuning picks one per side, and the
  test uses exactly that one.
- **Cut-off:** how sure the detector must be (the probability that the level just jumped) before it alarms.
  Lower alarms earlier and more often.
- **Sustain** (1, 2 or 3 weeks): how many weeks the rise must stay above the earlier mean. It stops one-week spikes.
- **Margin** (0 or 1): how far above the earlier mean, on the Anscombe scale (1 = one Poisson noise unit). All
  chosen settings use 0.
- **Early limit** (−4): part of the score, not of the detector. An alarm in weeks −4 to +1 is a hit (+1), an
  earlier one a false alarm (−1), no alarm a miss (0). **Score** = hits − false alarms.
- **Wins – losses – ties:** season by season, content against counts (rules in step 5).
- **Pre-set vs post hoc:** rules fixed before the held-out run (the −4 limit, the frozen settings) vs checks
  designed after it. Only the pre-set result is a test.

## Start here (teammates)

`output/` is in git, except `articles.csv` and `items.csv` (big; step 1 rebuilds them). So with git alone you can
run the tests and redo steps 3–5 and the post-hoc checks from `weekly_signals.csv` and `frozen_settings.json`:

```bash
cd repo-llm-v2/flu_signal
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt   # or reuse ../llm-extractor/.venv
.venv/bin/python -m unittest discover tests      # 98 tests, offline
.venv/bin/python tune.py --check                 # the frozen result still holds on today's weekly table
.venv/bin/python report_results.py && .venv/bin/python loso.py && .venv/bin/python post_hoc.py
.venv/bin/python transform_check.py              # about 90 s
git status --short output/                       # nothing listed = you got the same numbers
```

Steps 1–2 need the big gitignored inputs (see Inputs); ask Aditya for them. Please don't:

- run `run_detectors.py --final` again: it appends a second run to `output/held_out_run.json`, which marks the
  one-time test as rerun;
- run `tune.py --force`, or retune with 2022–2024 and call the result a test. Those seasons are spent. Any new
  rule (another limit, another signal) is post hoc and must be labelled so.

`HANDOFF.md` (next to this file) is a short brief for a new Claude Code session.

## Step 1: tables (`build_tables.py`)

Two tables, written to `output/`.

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

`output/weekly_signals.csv`: 12 rows per season. Each row has the split (`calibration` up to 2021,
`held_out` from 2022) and `headline` (USA, AUS, IND).

**Weeks are ISO weeks** (Monday to Sunday), taken from each article's scan date alone: an article of
3 Feb 2016 goes into `2016-W05` (column `iso_week`). A season's weeks are the 12 ISO weeks that lie wholly
inside its window. Only then is each week given a label, −10 to +1, by its position against the ISO week
that holds the FluNet onset (0). FluNet onsets are always ISO week starts (Mondays), so the windows line up.

The window's last day (onset + 14, a Monday) starts a 13th ISO week that has only 1 of its 7 days, so it is
dropped. That is 583 frequency counts and 193 content counts (`weekly_report.json`). Before 2026-11-10 that day
was added to week +1, which then held 8 days. The change touched only week +1 of 32 seasons. The columns count articles, not items: an article
adds 1 to a column in the week of its scan date if at least one of its items for that season passes the test.

| Column | An article counts when |
| --- | --- |
| `freq_articles` | it counts for the season (date in window, country mentioned). The baseline. |
| `content_articles` | it has any item for the season |
| `seasonal_articles` | it has a seasonal item: the strain is not bird flu (H5, H7, H9, H10, "avian") or a swine variant ("v") |
| `activity_articles` | a seasonal item is a count (cases, deaths, hospitalized) or a trend that is present, moderate, high or rising |
| `rising_articles` | a seasonal item is a trend that is rising or high |
| `avian_articles` | it has a bird flu or variant item. A check, not a candidate. |

The signals nest: `content_articles` ⊃ `seasonal_articles` ⊃ `activity_articles` ⊃ `rising_articles`.
`content_articles` keeps bird flu; the three below it leave it out. Prompt v5.2 gives a bird-flu item when
people are infected or tested, or as an "inactive" trend for food or monitoring news. Those items are real, but
they do not follow the seasonal epidemic (IND-2021 has 42 avian articles in week -3).

## Step 3: change-point detectors (`bcp.py`, `bocpd.py`, `run_detectors.py`)

Both work on Anscombe-transformed counts, 2·sqrt(x + 3/8). Both look only for a rise. There is no smoothing (no
moving average): the transform changes each week on its own, and the sustain rule below is a check, not a filter.

**Why the transform.** Both detectors use a Normal model. Bigger counts wiggle more (Poisson: about ±2 at 4 a
week, ±20 at 400). After the transform the wiggle is about ±1 at both levels, so the noise before and after a
rise is about the same. That is what BCP needs: it assumes one noise level for the whole season. BOCPD learns
the noise of each run, so it does not strictly need the transform. It still helps there: content counts of
0–3 a week are skewed and stop at 0, and the square root makes them closer to Normal.

**Real news is noisier than Poisson.** In weeks −10 to −5, `freq_articles` has a variance about 2.7 times its
mean (Poisson: 1 times). So after the transform the noise is about 1 for small series but about 2–4 for the big
USA series. That does not break the detectors. BCP needs only the same noise before and after a change (a series'
overall noise level cancels in its formula), and BOCPD measures it. Only the fixed constants assume a noise of
about 1: margin 1, BCP's floor and BOCPD's variance floor. No chosen setting uses margin 1. Post-hoc check 4
reruns everything on log and raw counts.

The two signals do not need to be on the same scale for a fair comparison. We compare when each one alarms, not
its counts. Both go through the same transform, detectors and settings grid.

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

## Step 5: the held-out run (`evaluate.py`, `report_results.py`, `loso.py`)

These rules were agreed and coded on made-up seasons before any held-out season was run.

- **Headline:** the 9 held-out seasons of USA, AUS and IND (2022–2024), with the two frozen settings.
- **Per season and signal:** hit (alarm in weeks −4 to +1), false alarm (earlier) or miss, as in step 4.
- **Lead time, two ways:**
  - `lead_days` = 7 × (−alarm week): an alarm in week −2 is 14 days early;
  - `lead_days_known` counts from the end of the alarm week, when all its articles are in: week −2 is 7 days early.

  The content − frequency difference is the same either way.
- **Who wins a season:** hit = +1, miss = 0, false alarm = −1. The higher one wins. When both hit, the earlier
  alarm wins. The same week, both missing, or both false is a tie.
- **Content is "better"** when its score (hits − false alarms) is at least frequency's AND it wins more
  seasons than it loses. An exact sign test on wins vs losses is reported too; with 9 seasons it has little
  power, so the result is mostly descriptive.
- **Also reported:** Ganser's "timely" detection (an alarm in weeks −2 to +1), and the all-38 table (every
  season; calibration seasons flagged `tuned_on`).
- **Robustness:** leave one season out over the 22 headline seasons. Each time, the whole step 4 tuning is
  redone on the other 21, and the chosen settings are scored on the one left out.

Order: `run_detectors.py --final` (writes `held_out_run.json`, a record of the one run), then
`report_results.py`, then `loso.py`.

**After the switch to ISO weeks (2026-11-10).** The frozen settings and `detections_*_frozen.csv` were made with
the old folded week +1. `tune.py --check` shows they still hold: tuning on the ISO-week table chooses the same two
settings, and every frozen alarm week is unchanged. So the by-year result did not move. Only their `total` column
still includes the dropped day. LOSO retunes, so it was rerun.

### Results

Two evaluations were planned before the held-out run.

- **Main evaluation: leave one season out (LOSO).** We chose this on 2026-11-10, after the results.
  The news data exist only in season windows, not year round, so the split has to be by season anyway. LOSO
  tests every one of the 22 headline seasons once and tunes on the other 21. The by-year split tunes on only 13
  seasons, and those have a COVID gap (no USA onset in 2020–2021) before the 2022–2024 test seasons.
- **Pre-registered test: by year.** Tune on 2015–2021, test on 2022–2024. This was named the main test before the
  run, and it is reported in full below. It copies real use (tune on the past, test on the future). LOSO doesn't:
  it also trains on seasons that come after the one it tests.

| Early limit −4 (pre-set) | LOSO: 22 folds, tune on 21, test 1 | By year: tune 2015–2021, test 2022–2024 |
| --- | --- | --- |
| Content hits / false / misses | 12 / 1 / 9 | 4 / 4 / 1 |
| Content score | 11 | 0 |
| Frequency hits / false / misses | 7 / 2 / 13 | 4 / 1 / 4 |
| Frequency score | 5 | 3 |
| Wins – losses – ties (content) | 9 – 6 – 7 | 4 – 3 – 2 |
| Sign test p | 0.61 | 1.0 |
| Content "better" by the rule | yes | no |

**LOSO.** 21 of 22 folds pick `content_articles`, BCP, cut-off 0.3, sustain 3. For frequency, 20 of 22 pick
`freq_articles`, BCP, cut-off 0.5, sustain 1. On the 9 held-out seasons alone, LOSO content scores 6 vs 3.

Before the switch to ISO weeks, LOSO gave 11 vs 3 (wins 11 – 6 – 5, p = 0.33). Dropping the extra day changed
frequency's tuning in some folds: 2 fewer false alarms and 2 more misses. Content did not change.

**By year (held-out run of 2026-11-07, code `9a76851`, frozen settings `891318b`): content is not better.**
Content scored 0 (4 hits − 4 false alarms), frequency 3 (4 hits − 1 false alarm). Content wins 4 seasons,
frequency 3, with 2 ties (sign test p = 1.0).

| Season | Content alarm | Frequency alarm | Winner |
| --- | --- | --- | --- |
| AUS-2022 | −5 (false) | none (miss) | frequency |
| AUS-2023 | 0 (hit) | none (miss) | content |
| AUS-2024 | −4 (hit) | −3 (hit) | content |
| IND-2022 | −1 (hit) | 0 (hit) | content |
| IND-2023 | −6 (false) | −5 (false) | tie |
| IND-2024 | none | none | tie |
| USA-2022 | −5 (false) | −2 (hit) | frequency |
| USA-2023 | −5 (false) | −3 (hit) | frequency |
| USA-2024 | −3 (hit) | none (miss) | content |

Content misses 1 season, frequency 4. Both are timely (weeks −2 to +1) in 2 seasons. When both hit, content
was 7 days earlier (median of 2 seasons).

**Why content lost by year: most of its "false alarms" are real early rises, not noise.**

- In USA-2022, the rising articles in weeks −7 to −1 go 1, 4, **6, 13, 33, 57, 134** (alarm at week −5).
- In USA-2023, weeks −7 to −3 go 5, 12, **15, 62, 81** (alarm at week −5).

These rises last, and they start about 5 weeks before the FluNet onset. The −4 limit, set before the run, counts
them as false. AUS-2022 is different: a short blip (5 in week −5, then 2 and 0), which sustain 1 lets through.
The rule is not changed after the fact. Looser limits are in the post-hoc checks below, labelled as such.

**All 38 seasons** (frozen settings): content 12 hits / 4 false / 22 misses, frequency 11 / 3 / 24 (both score 8).
In the 25 seasons not tuned on: content 4 / 4 / 17 (score 0), frequency 6 / 2 / 17 (score 4). BRA, KEN and IDN
give content no hits at all (0 of 16 seasons); frequency gets 2.

**The two evaluations disagree, and the disagreement is the finding.** The settings tuned on 2015–2021 did not
carry over to 2022–2024. Post-COVID seasons rose earlier and more steeply in the news, so the 2015–2021 choice
(sustain 1, `rising_articles`) rang too early. When the tuning also sees seasons like 2022–2024, content does
better than frequency. Neither p-value is small. With 9 and 22 seasons, no result here is statistically strong.

### Post-hoc checks (`post_hoc.py`)

Checks 1–3 were designed on 2026-11-07, and check 4 on 2026-11-10, all **after** the held-out results were
seen. They describe how much the result depends on our choices. They do not replace the pre-set result, and
nothing here changes the frozen settings. All numbers are on the ISO-week table.

**1. The early limit.** The hit window starts at week −4 because we set it that way. Here it starts at −2 to −7
instead. At each limit, the settings are retuned on 2015–2021 with that limit and then tested, so tuning and
testing use the same rule. Week −7 is the earliest week a week-by-week detector can alarm, because it needs 4
weeks of history. So the −7 row is the same as "every week before onset counts". In that row a false alarm is
impossible, so the score only counts whether the detector rang at all: it cannot fail, which is why it is not
the main rule.

| Early limit | By year: content vs frequency score | Wins – losses – ties | p | LOSO: content vs frequency score | Wins – losses – ties | p |
| --- | --- | --- | --- | --- | --- | --- |
| −2 | −4 vs 0 | 2 – 5 – 2 | 0.45 | −2 vs −1 | 7 – 6 – 9 | 1.0 |
| −3 | −2 vs 2 | 3 – 5 – 1 | 0.73 | 3 vs 4 | 6 – 8 – 8 | 0.79 |
| **−4 (pre-set)** | **0 vs 3** | **4 – 3 – 2** | **1.0** | **11 vs 5** | **9 – 6 – 7** | **0.61** |
| −5 | 6 vs 5 | 7 – 1 – 1 | 0.07 | 13 vs 4 | 14 – 2 – 6 | 0.004 |
| −6 | 5 vs 5 | 6 – 1 – 2 | 0.13 | 14 vs 4 | 16 – 3 – 3 | 0.004 |
| −7 (whole window) | 9 vs 6 | 7 – 0 – 2 | 0.02 | 18 vs 13 | 12 – 5 – 5 | 0.14 |

- With a narrow window (−2, −3), content loses: it rings early, and early counts as false.
- From −5 on, content wins most seasons in both evaluations. Its median lead grows too (by year: 28 days at
  −5, 35 at −7, against 21 for frequency).
- At −5, LOSO picks the same setting as the frozen one (`rising_articles`, BCP, 0.4, sustain 1) in 20 of 22 folds.
- The by-year score is not steady: content leads at −5 and −7 but only ties at −6. The early limit we pick
  decides the winner. In plain words: content alarms earlier than frequency; whether that counts as a success
  depends on how much early warning you call useful.

**2. Every content signal on 2022–2024** (limit −4). Each signal uses its own best 2015–2021 setting and is
compared with the frozen frequency setting (score 3). This is a description, not a new choice of winner:
picking the best of these afterwards would be choosing on the test seasons.

| Signal | Content hits / false / misses | Score | Wins – losses – ties | Bird-flu share |
| --- | --- | --- | --- | --- |
| `content_articles` (≈ useful = yes) | 4 / 4 / 1 | 0 | 3 – 4 – 2 | 46% |
| `seasonal_articles` (useful, no bird flu) | 3 / 3 / 3 | 0 | 3 – 4 – 2 | 0% |
| `activity_articles` | 4 / 3 / 2 | 1 | 4 – 4 – 1 | 0% |
| `rising_articles` (the frozen one) | 4 / 4 / 1 | 0 | 4 – 3 – 2 | 0% |
| `avian_articles` (negative control) | 3 / 1 / 5 | 2 | 3 – 3 – 3 | 100% |

No content signal beats frequency at −4. The negative control, bird-flu news alone, scores about as well as the
content signals. Its 3 "hits" (AUS-2024, USA-2023, USA-2024) are bird-flu news that happened to rise near the
seasonal onset (in USA-2024, the H5N1 outbreak in US dairy cattle). That shows how easily 9 seasons can be matched by chance.

**3. Bird flu inside `content_articles`.** `content_articles` counts any flu item, bird flu included. Over the
held-out seasons 46% of it is bird flu, and in USA-2024 it is 79% (1,952 of 2,468 articles). The other three
content signals leave bird flu out. Keeping it in `content_articles` is by design: the prompt gives bird-flu
items when people are affected. Of the 5,032 bird-flu items, 3,371 count people (cases, hospitalised, deaths)
and 1,287 are "inactive" food or monitoring trends. But FluNet's onset follows seasonal flu, so for this
question bird-flu news is mostly noise.

To see what bird flu itself changes, LOSO was locked to one signal: `content_articles` (with bird flu) and
`seasonal_articles` (the same articles minus bird flu). The frequency side is retuned as usual.

| Early limit | LOSO locked to `content_articles`: content vs counts | LOSO locked to `seasonal_articles`: content vs counts |
| --- | --- | --- |
| −4 | 11 vs 5 (wins 9 – 6 – 7) | 10 vs 5 (wins 8 – 6 – 8) |
| −5 | 13 vs 4 (wins 12 – 4 – 6) | 10 vs 4 (wins 10 – 5 – 7) |
| −6 | 7 vs 4 (wins 9 – 6 – 7) | 14 vs 4 (wins 13 – 4 – 5) |
| −7 | 18 vs 13 (wins 12 – 5 – 5) | 15 vs 13 (wins 10 – 8 – 4) |

- **Bird flu does not explain content's LOSO win.** Without it, content still beats counts at every limit
  from −4 on. Bird flu helps at some limits and hurts at −6, with no steady direction.
- At −4 both locked runs hit 12 seasons. The 1-point gap is one false alarm fewer with bird flu (USA-2022: week
  −2 instead of −6), from a different tuned setting. 10 of the 22 seasons change, in both directions.
- A third run let the tuning choose among the bird-flu-free signals only (seasonal, activity, rising). At −4 it
  scores 3 vs 5, because most folds pick `rising_articles` (cut-off 0.6). That drop comes from the choice of
  signal, not from leaving bird flu out. (An earlier version of this README said the LOSO win depended on bird
  flu; the locked runs show it does not.)

**4. The transform (`transform_check.py`).** The whole procedure is rerun with log(x + 1) and with raw counts
in place of the Anscombe transform, at the pre-set limit −4. Both evaluations retune for each transform.

| Transform | By year: content vs frequency | Wins – losses – ties | p | LOSO: content vs frequency | Wins – losses – ties | p |
| --- | --- | --- | --- | --- | --- | --- |
| **Anscombe (the method)** | **0 vs 3** | **4 – 3 – 2** | **1.0** | **11 vs 5** | **9 – 6 – 7** | **0.61** |
| log(x + 1) | −1 vs 2 | 3 – 3 – 3 | 1.0 | 8 vs 0 | 11 – 4 – 7 | 0.12 |
| raw counts | 2 vs 5 | 4 – 3 – 2 | 1.0 | −1 vs 10 | 3 – 14 – 5 | 0.01 |

- **Log agrees with Anscombe.** Content leads in LOSO and trails by year.
- **Raw counts reverse LOSO.** Frequency wins 14 of 22 seasons. On raw counts the noise grows with the level,
  which breaks BCP's one-noise-level assumption (both raw-count picks are BCP), so raw is the weakest of the
  three. That is the likely reason, but it is not tested. In particular, it doesn't explain why frequency gets
  *better* on raw counts (12 hits vs 7). Either way, the content advantage is not robust to this choice. The Anscombe transform was chosen before any result was seen, for the reason in
  step 3; we did not pick it because it wins.
- Floors per scale are in `detection.TRANSFORMS` (log: set for about 10 articles a week). Margin 1 means a
  different step on each scale, but no chosen setting used it.

**Lessons for a next study.** Pre-register a wider early limit, or report lead time without a hit/false cut.
Pre-register one broad, bird-flu-free signal (`seasonal_articles`) as the main content signal: it held up in LOSO.
Collect more than 10 weeks before onset, so that very early alarms can be checked against a real "no flu" period.

## Limitations

- **The windows were collected around the onset.** We only have news from 10 weeks before each FluNet onset to 2
  weeks after. So every season's series starts exactly 10 weeks before onset, and the onset is always the 11th
  week. The detectors don't know this. But a rule like "always alarm in the 8th week" would land on week −3 and
  hit all 22 seasons. So a score on its own (for example "content hit 12 of 22") is not a measure of accuracy.
  Only the comparison of content against frequency is meaningful, because both get the same windows. Building
  the weeks from the ISO calendar (step 2) doesn't change this. Only year-round news data would fix it: then a
  detector would also have to stay quiet outside the season.
- **Few seasons.** 22 headline seasons for LOSO and 9 for the by-year test, so no result is statistically strong.
- **Three countries.** BRA, KEN and IDN have almost no content. No other country can replace them with the
  data we have: the GDELT gate kept only articles that mention one of the six cohort countries, and only inside
  their windows. Canada has the most items of the rest, but only 3–31 seasonal articles per season.
- **The transform matters** (post-hoc check 4).

## Inputs

Step 1 reads these, read only. Paths are in `signal_config.py` and assume the worktrees sit side by side as
`repo/`, `repo-sampling/` and `repo-llm-v2/` in one folder.

| File | Size | In git |
| --- | --- | --- |
| `repo-llm-v2/llm-extractor/results/pool_combined/raw_results.jsonl` (LLM replies) | 126 MB | no |
| `repo-llm-v2/llm-extractor/data/gold_labels.json` | 0.8 MB | yes |
| `repo-llm-v2/usefulness_filter/output/filter_decisions.csv` | 4 MB | no |
| `repo-sampling/sampling/output/all_articles_buckets.csv` | 11 MB | no |
| `repo/output/pool/season_assignments.jsonl` and `season_windows.json` | 55 MB | no |
| `repo/output/pool/pooled_articles.jsonl` (GDELT locations) | 2 GB | no |

## Use

Run from this folder, with the extractor's venv (or a venv from `requirements.txt`):

```bash
../llm-extractor/.venv/bin/python -m unittest discover tests   # 98 tests, offline
../llm-extractor/.venv/bin/python build_tables.py              # needs the big inputs
../llm-extractor/.venv/bin/python build_weekly.py              # needs the big inputs
../llm-extractor/.venv/bin/python run_detectors.py --cutoff 0.5 --sustain-weeks 2 --margin 1   # calibration only
../llm-extractor/.venv/bin/python tune.py                       # refuses: the settings are frozen
../llm-extractor/.venv/bin/python tune.py --check               # writes nothing: the frozen result still holds
../llm-extractor/.venv/bin/python run_detectors.py --final      # held-out, once: already done, don't rerun
../llm-extractor/.venv/bin/python report_results.py
../llm-extractor/.venv/bin/python loso.py
../llm-extractor/.venv/bin/python post_hoc.py                   # post-hoc checks 1-3, after the results
../llm-extractor/.venv/bin/python transform_check.py            # post-hoc check 4: log and raw counts
```
