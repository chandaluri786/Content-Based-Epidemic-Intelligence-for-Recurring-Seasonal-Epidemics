# Item-based onset alarm: design and experiment

Date: 2026-11-19. Status: approved by Jahnavi; not yet implemented. Exploratory (post hoc): the pre-registered
held-out run is already spent (`output/held_out_run.json`). The weekly item series are built by
`COUNT_SIGNAL_RULES.md`.

## 1. The question

**Do signals built from what articles say (suspected cases, confirmed cases, hospitalisations, deaths) warn of the
flu season's start earlier, or more reliably, than simply counting flu articles?**

## 2. What is compared

| | Signal | Built from | Role |
|---|---|---|---|
| **Baseline** | `freq_articles` | weekly count of flu articles | what we must beat |
| **Test 1** | `content_articles` | weekly count of articles the LLM marks useful | content, article level |
| **Test 2 (main)** | **Item onset alarm** | the five item series below | content, item level |

The five item series (rules in `COUNT_SIGNAL_RULES.md`):

| Series | Evidence |
|---|---|
| `cases_suspected` | suspicion |
| `hospitalized_suspected` | suspicion |
| `cases_confirmed` | confirmation |
| `hospitalized_confirmed` | hospitalisation |
| `deaths_confirmed` | death |

`deaths_suspected` is not built: prompt v5.2 (2.4) never records a suspected death. Trend signals are set aside
until their rules are written (Section 10).

**Seasons:** the 22 USA, Australia and India seasons. Week 0 is the WHO FluNet onset; the weeks run from −10 to +1.

## 3. Replay: only what was known at the time

Each season is replayed week by week. At each week, every series is rebuilt from **only the articles published up to
the end of that week**. A late report updates the week its events happened in, but the detector sees that update only
from the week the article was published. **No alarm can use information from the future.**

## 4. When one series raises an alarm

The change-point detector (BCP or BOCPD) finds weeks where the pattern of a series changes. A change becomes an
**alarm** only if it passes both tests:

| Test | Rule |
|---|---|
| **Growth** | the change is a rise: each lasting week is **above the average of all the weeks before the change** |
| **Lasting** | the existing rule (`detection.is_sustained`): the change week and the next `sustain` − 1 weeks are all above the average of the weeks before the change, with `sustain` = 1, 2 or 3, tuned with the detector settings (Section 6). Sustain 1 checks only the change week, so it is no persistence check |

- The alarm is raised in the week the rise is confirmed: the change week itself with `sustain` 1, one week later
  with 2, two weeks later with 3.
- Each series raises **at most one alarm per season**: its first. A too-early first alarm counts as a false alarm and
  is not replaced by a later one.
- The detectors need a few weeks of history, so the earliest possible alarm is week −7.

How large the rise is does not count yet: any rise that lasts counts. A size test is future scope (Section 10).

## 5. The item onset alarm

> **Item onset alarm** = the **first week any of the five item series** raises an alarm.

That week is the one item-based onset date for the season.

- **Suspicion can raise it alone.** Early hints are the point of an early-warning system.
- **The numbers are never added together.** Only alarm weeks are combined, so one person reported as a case, an
  admission and a death is never counted three times.
- **Grade at the alarm** = the most serious evidence alarming in that week:

| Grade | Most serious evidence | What officials can prepare |
|---|---|---|
| 1 | suspicion | test kits, vaccine and antiviral stock, hospital alerts |
| 2 | confirmed cases | grade 1 + testing and vaccination drives |
| 3 | hospitalisations | grade 2 + beds, ICU staff, medicines |
| 4 | deaths | grade 3 + emergency measures |

- After the alarm, the grade is reassessed every week (which series have alarmed so far), to show how fast the
  season gets worse. The grade is reported with the result, not scored.

## 6. Settings: what is fixed and what is tuned

| Setting | Value | How |
|---|---|---|
| Growth | above the average of all earlier weeks (margin 0) | **fixed** |
| Lasting (`sustain`) | 1, 2 or 3 weeks | **tuned** |
| Detector (BCP or BOCPD, week-by-week runs) and its confidence cut-off | the existing grid | **tuned** |

- Tuned settings are chosen on the other 21 seasons and applied blind to the season left out
  (leave-one-season-out), with the existing scoring and tie-break rules.
- The **baseline and useful articles get exactly the same treatment**: the same fixed growth rule and the same tuning.
- For the item onset alarm, one setting is shared by all five series and chosen by the score of the **item onset
  alarm** itself, so false alarms from any series count against it.
- The margin is fixed at 0 here (the earlier runs also tried 1), so the baseline's numbers can differ from the
  earlier results.

## 7. Scoring

Each onset date is compared with the FluNet onset:

| Outcome | Rule | Points |
|---|---|---|
| **Hit** | alarm in weeks **−4 to +1** | +1 |
| **False alarm** | alarm before week −4 | −1 |
| **Miss** | no alarm by week +1 | 0 |

- **Score** = hits − false alarms over the 22 seasons.
- **Lead time** of a hit = how many days before the onset the alarm came; also reported counted from the end of the
  alarm week, when all its articles are in.
- Early limit **−4** was set in advance; **−5** is reported as post hoc.

## 8. How the result is judged

**Main comparison:** item onset alarm vs baseline, early limit −4.

The item signals are **better** than the baseline if both hold:
1. the item onset alarm's score is **at least** the baseline's, and
2. it **wins more seasons than it loses**. It wins a season with a better outcome, or the same outcome with an
   earlier alarm.

Both hold: better. Neither: not better, reported as the finding. One: mixed.

**Reported alongside (to explain and test the result):**
- hits, false alarms and misses shown separately, not only the score;
- each of the five item series alone, scored the same way;
- which series triggered the item onset alarm in each season, to show whether suspicion gave the lead;
- the item onset alarm **without the suspicion series**: do the hints add earlier correct warnings, or only false
  alarms?
- useful articles (Test 1) vs the baseline, the same way;
- early limit −5 (post hoc);
- the `sustain` value chosen in each fold;
- a calendar reference with no news: alarm in the ISO week of the country's usual onset date (median of its other
  seasons, leave one season out), to show what knowing the usual timing alone scores;
- results by country (USA, Australia, India).

## 9. Cautions to state with the result

- **Small sample:** 22 seasons, so differences of a season or two are descriptive, not proof.
- **Exploratory:** the held-out seasons were already used. Firm confirmation needs seasons the settings were not
  chosen on. New seasons (2025 onward) would need new GDELT downloads and a paid extractor run, so the next checks
  use the data here (Section 10).
- **Seasons overlap:** seasons of the same year in different countries share news events, so they are not fully
  independent.
- **False alarms are visible only in weeks −7 to −5.** The data start 10 weeks before each onset, so alarms in quiet
  months cannot be measured.
- **Item series are sparse,** especially the suspected ones. A silent series avoids false alarms but also misses,
  which is why outcomes are shown separately.
- **No size test yet:** any lasting rise counts, so small rises in sparse series can cause false alarms.

## 10. Future scope

- **Size of the rise:** a rise counts only if it clears the normal range (normal level + a multiple of the normal
  bounce, from the weeks before the rise). The multiple and the window are chosen by testing on quiet, made-up series
  against a false-alarm target, not by guessing.
- **At least 2 different articles** behind a rise, so one story cannot cause an alarm.
- **Trend signals** (for example "flu is rising"), once their rules are written, with their place in the alarm decided
  before any results are seen.
- **A longer history before each season,** so false alarms in quiet months can be measured. This needs a new data
  pull and extraction run.
- **Persistence check:** `sustain` fixed at 2 (and 3) for every signal, so "lasting" is literally true.
- **By-year split:** tune on 2015–2021 only and score 2022–2024 once, the same split as the pre-registered test
  (still post hoc, since the item design came after those results).
- **New seasons (2025 onward)** as a true test, if new GDELT data and an extractor run become possible.
- **Multi-series detectors,** if more data become available.
