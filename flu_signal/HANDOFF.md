# flu_signal handoff

Written for: a teammate, or a new Claude Code session, picking up the change-point work. Read this first, then
`README.md` (every rule and every number) when you need detail.

## Where things stand (2026-11-08)

- Steps 1–5 are done, and the one held-out run is spent (`output/held_out_run.json`, 2026-11-07).
- **Pre-registered result:** content is not better. On the 9 held-out USA/AUS/IND seasons (2022–2024), content
  (`rising_articles`, BCP, cut-off 0.4, sustain 1) scores 0 vs frequency's 3 (`freq_articles`, BOCPD, 0.4, sustain 1).
- **Leave one season out (22 seasons, planned in advance):** content 11 vs 3, wins 11–6–5, p = 0.33.
- **Post hoc (`post_hoc.py`, designed after the results):** content alarms earlier. From an early limit of −5 it
  wins most seasons in both evaluations. Bird flu does not explain the LOSO win.
- Still to do: a methods/results write-up that replaces the stale parts of `repo/capstone_proposal.md`.

## Check it yourself (git only, no big data)

```bash
cd repo-llm-v2/flu_signal
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover tests      # 86 tests
.venv/bin/python report_results.py && .venv/bin/python loso.py && .venv/bin/python post_hoc.py
git status --short output/                       # nothing listed = same numbers
```

`post_hoc.py` also checks itself: its −4 rows must match the frozen settings and `results_summary.json`, or it
stops with an error.

## Rules that keep the test honest

- Don't run `run_detectors.py --final` again, or `tune.py --force`. The held-out seasons are used up.
- Anything new (another early limit, another signal, a new tuning) is post hoc. Label it so, and never present it
  as the main result.
- Don't pick the "best" signal from the per-signal table on 2022–2024: that is choosing on the test seasons.

## Things that surprise people

- **Signals are nested.** `content_articles` (any item, bird flu included) ⊃ `seasonal_articles` (no bird flu)
  ⊃ `activity_articles` ⊃ `rising_articles` (trend rising or high). `avian_articles` is a negative control,
  never a candidate. `freq_articles` includes bird-flu news too, because the GDELT themes do.
- **The two evaluations pick different signals.** By year froze `rising_articles`; LOSO picks `content_articles`
  (BCP, 0.3, sustain 3) in 21 of 22 folds. LOSO retunes in every fold; it never reuses the frozen setting.
- **No alarm can come before week −7:** the detectors need 4 weeks of history. So the −7 row of the post-hoc
  table means "every week before onset counts", and false alarms are impossible there.
- **No smoothing.** Detectors read raw weekly counts after the Anscombe transform.
- **BRA, KEN and IDN have almost no content** (0 content hits in 16 seasons), so the headline uses USA/AUS/IND.
- **Paths assume the worktree layout:** `repo/`, `repo-sampling/` and `repo-llm-v2/` side by side in one folder
  (see `signal_config.py`). Steps 1–2 need about 2.2 GB of gitignored inputs; ask Aditya.
- **The LLM extractor costs money.** Nothing here calls it; `flu_signal` only reads its saved replies.

## Open questions worth discussing

- Which early limit is clinically useful? −4 was set in advance; content's advantage shows from −5.
- For a next study: pre-register `seasonal_articles` (broad, no bird flu) as the content signal, a wider limit or
  a lead-time measure without a hit/false cut, and more than 10 weeks before onset.
