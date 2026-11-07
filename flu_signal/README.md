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

- **Frequency signal:** the article counts in every cohort country-season it mentions
  (`country_seasons` in `repo/output/pool/season_assignments.jsonl`). Column `frequency_seasons`.
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
| USA | 41,482 | 7,310 | 16,619 |
| AUS | 4,975 | 604 | 1,104 |
| IND | 12,823 | 536 | 1,334 |
| BRA | 8,474 | 42 | 58 |
| KEN | 6,200 | 5 | 8 |
| IDN | 3,757 | 6 | 6 |

BRA, KEN and IDN have almost no content (0–4 articles per season, except BRA-2023 with 35). So the main
lead-time comparison uses USA, AUS and IND (22 seasons). A second table covers all 38 seasons, with no
content signal counted as "not detected".

## Inputs

Read only, from the other worktrees: `llm-extractor/results/pool_combined/raw_results.jsonl`,
`llm-extractor/data/gold_labels.json`, `usefulness_filter/output/filter_decisions.csv`,
`repo-sampling/sampling/output/all_articles_buckets.csv`, and `repo/output/pool/season_assignments.jsonl`
and `season_windows.json`. Paths are in `signal_config.py`.

## Use

Run from this folder, with the extractor's venv:

```bash
../llm-extractor/.venv/bin/python -m unittest discover tests   # 11 tests, offline
../llm-extractor/.venv/bin/python build_tables.py
```
