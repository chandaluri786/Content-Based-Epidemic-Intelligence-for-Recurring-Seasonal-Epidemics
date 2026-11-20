# Item signal results: frequency vs useful articles vs item signals

**Run:** 2026-11-19, on strict ISO weeks (`db5acf3`): `build_weekly.py` then `loso.py --items`, prompt v5.2 items.
**Rules:** [COUNT_SIGNAL_RULES.md](COUNT_SIGNAL_RULES.md) and [COMBINED_SIGNAL_RULES.md](COMBINED_SIGNAL_RULES.md).
**Status:** everything in this file is **post hoc and exploratory**. The item signals were designed after the
held-out results were known, and no item setting has been tested on seasons it was not chosen on.

---

## Exploratory: item signals look promising

**Read this next to the results that came before:**

| Evaluation | Content | Frequency | Status |
|---|---|---|---|
| By-year test, 9 held-out seasons (README) | `rising_articles`: score **0** | `freq_articles`: score **3** | **pre-registered**: content not better |
| Leave one season out, 22 seasons (README) | `content_articles`: score **11** | `freq_articles`: score **5** | main evaluation, chosen after the run; wins 9–6–7, p = 0.61 |
| Leave one season out, 22 seasons (this file) | `item_onset`: score **18** (19/1/2) | `freq_articles`: score **5** (7/2/13) | **post hoc**; wins 14–4–4, p = 0.031 |

What looks promising, and what it does not show yet:

- **Coverage:** combining the five item series catches **19 of 22** onsets, against 7 of 22 for frequency.
- **Suspicion:** suspicion items drive most of the alarms. A suspicion series triggered 13 of the 20 alarms, and without the suspicion series the score falls from 18 to 9.
- **Reliability, not lead time:**
  - The gain is reliability (fewer misses), not earliness.
  - The median lead is 7 days, about 0 once reporting lag is counted.
  - The tuned sustain is 1, which means **no persistence check**. So the alarm is "the first upward change the detector is ≥ 90% sure of", not a sustained rise.
- **Not shown yet:** that this holds on seasons the setting was not chosen on. Section 7 says how to check that without new data.

---

## 1. How to read the numbers

| Term | Meaning |
|---|---|
| Hit | alarm in weeks −4..+1 around the FluNet onset (−5..+1 for the wider range) |
| False alarm | alarm earlier than the hit range |
| Miss | no alarm by week +1 |
| Score | hits − false alarms |
| Median lead | days before onset, over hits. "As known" takes about 7 days off for reporting lag. |
| Wins–losses–ties | season by season against `freq_articles` |
| "Better" | score at least the baseline's and more wins than losses ("mixed" if only one holds) |

- **Seasons:** 22 headline seasons (USA 8, AUS 6, IND 8).
- **Fair test of each season:** each season is scored with settings chosen on the other 21 (leave-one-season-out).
- **No hindsight:** item series are replayed "as known at the time". At season week t, only items scanned by the Sunday of week t are used.
- **Weeks:** strict ISO weeks.
  - Article signals sit in the week of the scan date.
  - Item numbers sit in the week their events happened.
  - So the ISO-week change (`db5acf3`) moved the frequency baseline but left every item series unchanged.

## 2. Head-to-head, all signals

Each cell is hits / false alarms / misses → score.

| Family | Signal | −4..+1 (main) | −5..+1 | Median lead (days) | Lead as known |
|---|---|---|---|---|---|
| Frequency | **`freq_articles`** (GDELT tag count, the performance baseline) | 7/2/13 → **5** | 6/2/14 → 4 | 7 | 0 |
| Reference | `calendar_usual_onset` (no news, see 5.4) | 9/4/9 → 5 | 9/4/9 → 5 | | |
| Useful articles | `content_articles` | 12/1/9 → **11** | 13/0/9 → 13 | 7 | 0 |
| Item series | `cases_suspected` | 12/1/9 → 11 | 12/1/9 → 11 | 0 | −7 |
| Item series | `hospitalized_suspected` | 4/1/17 → 3 | 4/1/17 → 3 | 17.5 | 10.5 |
| Item series | `cases_confirmed` | 14/2/6 → **12** | 17/0/5 → **17** | 17.5 | 10.5 |
| Item series | `hospitalized_confirmed` | 10/2/10 → 8 | 12/1/9 → 11 | 14 | 7 |
| Item series | `deaths_confirmed` | 11/2/9 → 9 | 11/2/9 → 9 | 0 | −7 |
| Item combined | **`item_onset`** | **19/1/2 → 18** | **19/1/2 → 18** | 7 | 0 |
| Item combined | `item_onset` without suspicion | 13/4/5 → 9 | 17/1/4 → 16 | 7 | 0 |

The lead columns are for the −4 range.

### Season by season against `freq_articles`

| Candidate | −4: W–L–T (p) | Decision at −4 | −5: W–L–T (p) | Decision at −5 |
|---|---|---|---|---|
| **item_onset** | **14–4–4 (0.031)** | **better** | 16–4–2 (0.012) | better |
| item_onset without suspicion | 10–9–3 (1.0) | better | 16–4–2 (0.012) | better |
| cases_confirmed | 13–4–5 (0.049) | better | 17–2–3 (0.0007) | better |
| cases_suspected | 10–5–7 (0.30) | better | 11–4–7 (0.12) | better |
| hospitalized_confirmed | 10–5–7 (0.30) | better | 11–4–7 (0.12) | better |
| deaths_confirmed | 8–6–8 (0.79) | better | 9–6–7 (0.61) | better |
| hospitalized_suspected | 4–5–13 (1.0) | **not better** | 4–5–13 (1.0) | not better |
| content_articles | 9–6–7 (0.61) | better | 12–4–6 (0.077) | better |

- **Clearly ahead season by season (p < 0.05 at −4):** only `item_onset` and `cases_confirmed`. The rest are "better" by the decision rule only.
- **The no-suspicion variant** is "better" at −4 only by the letter of the rule (10 wins vs 9 losses, p = 1.0).

## 3. By country (−4..+1)

| Signal | AUS (6) | IND (8) | USA (8) |
|---|---|---|---|
| `freq_articles` | 1/0/5 | 2/1/5 | 4/1/3 |
| `calendar_usual_onset` (reference) | 2/1/3 | 2/2/4 | 5/1/2 |
| `content_articles` | 4/0/2 | 4/0/4 | 4/1/3 |
| `cases_suspected` | 3/0/3 | 3/1/4 | 6/0/2 |
| `hospitalized_suspected` | 0/0/6 | 1/1/6 | 3/0/5 |
| `cases_confirmed` | 5/1/0 | 4/0/4 | 5/1/2 |
| `hospitalized_confirmed` | 2/0/4 | 4/1/3 | 4/1/3 |
| `deaths_confirmed` | 2/1/3 | 5/0/3 | 4/1/3 |
| **`item_onset`** | **6/0/0** | **5/1/2** | **8/0/0** |
| `item_onset` without suspicion | 4/2/0 | 5/0/3 | 4/2/2 |

How much data each item series has (weeks with a value, summed over the country's seasons):

| Series | AUS | IND | USA |
|---|---|---|---|
| cases_confirmed | 24 | 55 | 91 |
| deaths_confirmed | 9 | 37 | 83 |
| hospitalized_confirmed | 9 | 44 | 61 |
| cases_suspected | 7 | 15 | 37 |
| hospitalized_suspected | 0 | 9 | 7 |

## 4. What worked, when and why

### Frequency (all articles): weakest
- **Result:** 13 misses. Worst in AUS (1 of 6).
- **Why:** it counts every article about the country, including bird flu, vaccine policy and general health news.
  - That volume moves for reasons unrelated to the season starting.
  - When a season starts quietly in the news, the volume doesn't move.
- **No better than the calendar:** its score of 5 equals the calendar reference, which uses no news at all.

### Useful-article count: steady but slow
- **Result:** almost no false alarms (1 at −4, 0 at −5), but 9 misses, 4 of them in India.
- **Why:**
  - The LLM's "useful" judgement removes the off-topic articles that fool frequency.
  - It needs sustain 2–3 (the rise must last 2–3 weeks) to stay clean, so it fires later.
  - In countries with few useful articles it never rises enough.

### Single item series: performance follows how much data the series has

| Series | Verdict | Why |
|---|---|---|
| `cases_confirmed` | **Best single signal**: all 6 AUS seasons, 17-day median lead, no false alarms at −5 | Most data of any series in every country |
| `cases_suspected` | **Early but thin**: fires right at onset (median lead 0), misses where few articles speculate | People talk about suspected flu as soon as it appears, but such reports are rare |
| `hospitalized_confirmed` | Middling; misses 4 of 6 AUS seasons | Little AUS data |
| `deaths_confirmed` | **Late by nature** (median lead 0); good in IND (5 hits), poor in AUS | Deaths follow cases |
| `hospitalized_suspected` | **Too sparse to use**; not better than frequency | No AUS data at all; 16 weeks in total |

### Combined item alarm: the series cover each other's gaps
- **Why it works:**
  - Different series catch different seasons (season grid below):
    - USA-2018: only suspected cases fire;
    - IND-2024: only deaths fire;
    - AUS-2016: only confirmed cases fire.
  - Taking the earliest alarm of the five lifts hits from 14 (best single series) to 19.
- **The price:**
  - With five chances to fire, false alarms multiply. So the tuning pushed the cutoff to **0.9** (in 21 of 22 folds), which makes each series fire a little later.
  - So the combined alarm is **not earlier** than its parts: median lead 7 days, about 0 as known.
- **Suspicion is essential:**
  - A suspicion series triggered **13 of the 20** alarms (8 by `cases_suspected` alone).
  - Without suspicion, the −4 result falls to score 9 and 10–9–3 against frequency.
- **Evidence grade at the alarm:**

  | Grade | Alarms |
  |---|---|
  | 1 (suspicion) | 10 |
  | 2 (confirmed cases) | 3 |
  | 3 (hospitalisations) | 5 |
  | 4 (deaths) | 2 |

### When it fails
- **India is the weak spot.**
  - Both misses: IND-2015, where no item series fires, and IND-2018.
  - The one false alarm: IND-2022, a `cases_suspected` alarm at week −6.
- **USA and AUS:** every season is caught (8 of 8 and 6 of 6), because they have the most items of every kind.

### Alarm week per season (−4..+1)

`−` = no alarm. Hit range −4..+1; anything earlier is a false alarm.
- `calendar` is the no-news reference; −10 means its usual date fell before the window.
- The `item_onset` and "no suspicion" columns use one shared setting for all five series.
- The single-series columns use each series' own tuned setting, so they can be earlier than `item_onset`.

| Season | freq | calendar | **item_onset** | no suspicion | useful | cases susp. | hosp. susp. | cases conf. | hosp. conf. | deaths conf. |
|---|---|---|---|---|---|---|---|---|---|---|
| AUS-2016 | − | −3 | **−1** | −2 | − | − | − | −2 | − | − |
| AUS-2017 | − | −4 | **0** | 0 | 1 | 1 | − | 0 | − | − |
| AUS-2018 | − | −10 | **−3** | −6 | − | −3 | − | −3 | − | −6 |
| AUS-2022 | − | − | **1** | 1 | −3 | 1 | − | 1 | − | 0 |
| AUS-2023 | − | − | **0** | −5 | 0 | − | − | −5 | 0 | − |
| AUS-2024 | −3 | − | **−2** | −2 | −1 | − | − | −3 | −2 | 1 |
| IND-2015 | − | −3 | **−** | − | − | − | − | − | − | − |
| IND-2016 | − | − | **−1** | −3 | − | −1 | −7 | −1 | −3 | 0 |
| IND-2017 | −1 | − | **0** | 0 | 0 | 1 | −4 | −4 | −4 | 0 |
| IND-2018 | − | −8 | **−** | 1 | − | − | − | 1 | −1 | − |
| IND-2021 | − | −6 | **−3** | −3 | −1 | 1 | − | − | −3 | −3 |
| IND-2022 | 1 | −3 | **−6** | − | −4 | −6 | − | − | −7 | 1 |
| IND-2023 | −6 | − | **−1** | −4 | −2 | − | − | −4 | − | − |
| IND-2024 | − | − | **0** | − | − | − | − | − | − | −3 |
| USA-2015 | −1 | −7 | **0** | 0 | − | 1 | 0 | −3 | −5 | − |
| USA-2016 | − | −2 | **1** | 0 | −1 | − | − | 0 | 1 | −3 |
| USA-2017 | 1 | 1 | **1** | − | − | 1 | − | − | − | 1 |
| USA-2018 | − | 0 | **−3** | − | − | −3 | − | − | − | − |
| USA-2019 | −5 | − | **−1** | −1 | −3 | −1 | − | −3 | − | −3 |
| USA-2022 | −1 | − | **−3** | −3 | −2 | −3 | −2 | −3 | −2 | −3 |
| USA-2023 | − | −1 | **−4** | −6 | −5 | −4 | − | −1 | −4 | −7 |
| USA-2024 | −3 | 0 | **−3** | −5 | −1 | − | −3 | −5 | 1 | − |

## 5. Cautions

1. **The pre-registered test favoured frequency.**
   - In the by-year test (settings frozen in advance, 9 held-out seasons), content scored 0 against frequency's 3.
   - Every result in this file is post hoc and must be reported next to it.
2. **Many comparisons were run:** 8 candidates and 2 hit ranges against one baseline. A single p = 0.03 is weaker evidence than it looks.
3. **22 seasons is small:** a swing of one or two seasons turns a win into a tie.
4. **Calendar reference (in `loso.py --items`, `calendar_reference` in the summary):**
   - How it works: alarm in the ISO week of the country's usual onset date (the median from its other seasons, leave one season out).
   - It scores 9/4/9 → 5, the same as `freq_articles`. So frequency does no better than knowing the usual date.
   - `item_onset` (18) does far better, so the item result is not just "flu starts around the same time each year".
   - Because the windows are built around the onset, absolute scores only mean something against references like this one (README, Limitations).
5. **18 items left out:** all are `new` counts covering 2–7 days, against prompt 4.2. Whether to count those that fall inside one ISO week is still open.
6. **Weak India data:** India has the least content, and its results carry the least weight.

## 6. Parameters

### 6.1 Fixed by design (same for every signal, never tuned)

| Parameter | Value | Where |
|---|---|---|
| Weeks | strict ISO weeks; a season is the 12 whole ISO weeks labelled −10..+1 against the onset's ISO week | `weekly.season_weeks` |
| Hit range | −4..+1 (main, set in advance); −5..+1 (post hoc) | `ITEM_EARLY_LIMITS = (4, 5)` |
| Score | hits − false alarms | `tune.choose` |
| Growth margin | 0 (growth only, no size test) | `ITEM_MARGIN = 0.0` |
| Sustain choices | 1, 2, 3 weeks, counting the change week (1 = no persistence check) | `SUSTAIN_CHOICES` |
| Cutoff grid | 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9 | `CUTOFF_GRID` |
| Detectors | BCP and BOCPD, prospective, on Anscombe-transformed counts | `bcp.py`, `bocpd.py` |
| BCP | first run after 4 weeks seen; within-block floor 0.1 per week; 200 grid points | `MIN_WEEKS`, `W_FLOOR_PER_WEEK`, `W_GRID_POINTS` |
| BOCPD | hazard 1/10; prior from the first 3 weeks; alarm only if the run began in the last 2 weeks; variance floor 1.0 | `HAZARD`, `PRIOR_WEEKS`, `RECENT_WEEKS`, `MIN_VARIANCE` |
| Item series | cases_suspected, hospitalized_suspected, cases_confirmed, hospitalized_confirmed, deaths_confirmed (no deaths_suspected) | `ITEM_SERIES` |
| Item onset | earliest alarm of the 5 series, one shared setting | `loso.item_alarm_weeks` |
| Replay | as known at the time (scan date ≤ Sunday of week t) | `weekly.item_vintages` |
| Count rules | one ISO week only, null start excluded, country → state → city, cumulative_region closes days, same-article guard, partial overlap dropped | `COUNT_SIGNAL_RULES.md` |

### 6.2 Settings chosen by the tuning

These are the settings most of the 22 leave-one-season-out folds chose. Each is written as detector / cutoff / sustain; margin is 0 throughout. **They were chosen with all 22 seasons in view, so they are not validated.**

| Signal | Main (−4..+1) | Folds | −5..+1 | Folds |
|---|---|---|---|---|
| **`item_onset`** | **BCP / 0.9 / 1** | 21 of 22 | BCP / 0.9 / 1 | 21 of 22 |
| `item_onset` without suspicion | BCP / 0.7 / 1 | 19 of 22 | BCP / 0.6 / 1 | 21 of 22 |
| `cases_confirmed` | BCP / 0.4 / 1 | 20 of 22 | BCP / 0.4 / 1 | 21 of 22 |
| `cases_suspected` | BCP / 0.9 / 1 | 20 of 22 | BCP / 0.9 / 1 | 20 of 22 |
| `hospitalized_confirmed` | BCP / 0.5 / 1 | 18 of 22 | BCP / 0.3 / 1 | 19 of 22 |
| `hospitalized_suspected` | BOCPD / 0.3 / 1 | 20 of 22 | BOCPD / 0.3 / 1 | 20 of 22 |
| `deaths_confirmed` | BCP / 0.3 / 1 | 22 of 22 | BCP / 0.3 / 1 | 22 of 22 |
| `content_articles` | BCP / 0.3 / 3 | 21 of 22 | BCP / 0.3 / 2 | 22 of 22 |
| `freq_articles` (baseline) | BCP / 0.5 / 1 | 20 of 22 | | |

## 7. Next steps (no new data needed)

There are no 2025 seasons in the pool. Getting them would need new GDELT downloads and a paid extractor run, so a fresh-season test is not planned. The checks below use only the data already here.

1. **Persistence:** rerun with sustain fixed at 2 (and 3) for every signal. That tells us whether `item_onset` still beats frequency when "sustained" is literally true, or whether its edge depends on alarming at the first upward week.
2. **Split by year:**
   - Tune `item_onset` and `freq_articles` on the 2015–2021 seasons only. Then score both once on 2022–2024, the same split as the pre-registered test.
   - This is still post hoc, because the item design came after those results. But it tests the chosen settings on seasons they were not tuned on, and it can be compared directly with content 0 vs frequency 3.
3. **The 18 multi-day `new` items:** decide whether those inside one ISO week count, and rerun to show whether any result moves.
