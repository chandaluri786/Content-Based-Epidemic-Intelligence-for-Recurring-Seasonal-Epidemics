"""
Unit tests for Stage 1 onset detection (pipeline/ground_truth.py) on
synthetic weekly FluNet rows -- the network fetch is monkeypatched out.
Run with: pytest
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import ground_truth
from pipeline.ground_truth import WeeklyPositivity, find_onsets, season_year_of, weekly_positivity

LOW, HIGH = 2.0, 30.0


def _series(start: date, pcts: list[float]) -> list[WeeklyPositivity]:
    return [WeeklyPositivity(week_start=start + timedelta(weeks=i), positivity_pct=p) for i, p in enumerate(pcts)]


def _row(week: str, processed: int, positive: int, source: str = "SENTINEL") -> dict:
    return {"ISO_WEEKSTARTDATE": week, "SPEC_PROCESSED_NB": processed, "INF_ALL": positive, "ORIGIN_SOURCE": source}


def test_weekly_positivity_pools_sentinel_and_nonsentinel_rows_of_the_same_week():
    """FluNet returns one row per origin source per week; treating them as
    separate weeks let a single week's high sentinel row look like a
    sustained run."""
    rows = [
        _row("2023-10-09", 65360, 870, "NONSENTINEL"),
        _row("2023-10-09", 3060, 320, "SENTINEL"),
        _row("2023-10-16", 100, 50),
    ]
    series = weekly_positivity(rows)
    assert [w.week_start for w in series] == [date(2023, 10, 9), date(2023, 10, 16)]
    assert round(series[0].positivity_pct, 2) == round(100 * 1190 / 68420, 2)
    assert series[1].positivity_pct == 50.0


def test_weekly_positivity_skips_weeks_without_a_denominator():
    rows = [_row("2023-01-02", 0, 0), _row("2023-01-09", None, 3), _row("2023-01-16", 10, None)]
    series = weekly_positivity(rows)
    assert [(w.week_start, w.positivity_pct) for w in series] == [(date(2023, 1, 16), 0.0)]


def test_season_year_of_uses_frame_start_month():
    assert season_year_of(date(2023, 12, 4), frame_start_month=7) == 2023
    assert season_year_of(date(2024, 1, 1), frame_start_month=7) == 2023
    assert season_year_of(date(2024, 7, 1), frame_start_month=7) == 2024
    assert season_year_of(date(2024, 1, 1), frame_start_month=1) == 2024


def test_carry_over_positivity_on_january_first_is_not_an_onset():
    """The old calendar-year rule picked ISO week 1 whenever the previous
    season was still above threshold. With a rising edge required, the only
    onset is the real one in early December."""
    start = date(2022, 10, 3)
    pcts = [LOW] * 9 + [HIGH] * 12 + [LOW] * 20  # rises 2022-12-05, stays high through Jan
    onsets = find_onsets(_series(start, pcts), "USA", frame_start_month=1, start_year=2022, end_year=2023)
    assert [(o.season_year, o.onset_date) for o in onsets] == [(2022, date(2022, 12, 5))]


def test_rising_edge_needs_enough_weeks_below_threshold_first():
    start = date(2023, 1, 2)
    too_short_dip = [LOW] * 3 + [HIGH] * 3          # only 3 weeks below before the run
    assert find_onsets(_series(start, too_short_dip), "IDN", 1, 2023, 2023) == []

    long_enough = [LOW] * 4 + [HIGH] * 3
    onsets = find_onsets(_series(start, long_enough), "IDN", 1, 2023, 2023)
    assert [o.onset_date for o in onsets] == [start + timedelta(weeks=4)]


def test_single_high_week_is_not_sustained():
    start = date(2023, 1, 2)
    pcts = [LOW] * 6 + [HIGH] + [LOW] * 6
    assert find_onsets(_series(start, pcts), "AUS", 1, 2023, 2023) == []


def test_usa_december_onset_is_labelled_with_the_frame_start_year():
    start = date(2023, 9, 4)
    pcts = [LOW] * 13 + [HIGH] * 10                  # rises 2023-12-04
    onsets = find_onsets(_series(start, pcts), "USA", frame_start_month=7, start_year=2023, end_year=2023)
    assert [(o.season_year, o.onset_date) for o in onsets] == [(2023, date(2023, 12, 4))]


def test_only_the_first_onset_in_each_frame_is_kept():
    start = date(2023, 1, 2)
    pcts = [LOW] * 4 + [HIGH] * 3 + [LOW] * 6 + [HIGH] * 3
    onsets = find_onsets(_series(start, pcts), "KEN", 1, 2023, 2023)
    assert [o.onset_date for o in onsets] == [start + timedelta(weeks=4)]


def test_lookback_crosses_the_frame_boundary():
    """Weeks below threshold at the end of December count toward a rising
    edge in the first weeks of January."""
    start = date(2022, 12, 5)
    pcts = [LOW] * 4 + [HIGH] * 3                     # rises 2023-01-02
    onsets = find_onsets(_series(start, pcts), "BRA", 1, 2023, 2023)
    assert [(o.season_year, o.onset_date) for o in onsets] == [(2023, date(2023, 1, 2))]


def test_onsets_outside_the_requested_years_are_dropped():
    start = date(2022, 1, 3)
    pcts = [LOW] * 4 + [HIGH] * 3 + [LOW] * 52 + [HIGH] * 3
    onsets = find_onsets(_series(start, pcts), "AUS", 1, 2023, 2023)
    assert [o.season_year for o in onsets] == [2023]


def test_fetch_weekly_rows_pages_with_skip_until_a_short_page(monkeypatch):
    """The FluNet API never returns @odata.nextLink, so paging must use $skip."""
    pages = {0: [{"n": i} for i in range(3)], 3: [{"n": i} for i in range(3, 6)], 6: [{"n": 6}]}
    requested_skips: list[int] = []

    def fake_get_page(country_iso3, start_year, end_year, skip, page_size):
        requested_skips.append(skip)
        return pages[skip]

    monkeypatch.setattr(ground_truth, "_get_page", fake_get_page)
    rows = ground_truth._fetch_weekly_rows("USA", 2015, 2016, page_size=3)
    assert [r["n"] for r in rows] == list(range(7))
    assert requested_skips == [0, 3, 6]


def test_compute_season_onsets_fetches_a_year_either_side(monkeypatch):
    seen: list[tuple[int, int]] = []

    def fake_fetch(country_iso3, start_year, end_year, page_size=1000):
        seen.append((start_year, end_year))
        return []

    monkeypatch.setattr(ground_truth, "_fetch_weekly_rows", fake_fetch)
    assert ground_truth.compute_season_onsets("USA", 2015, 2024) == []
    assert seen == [(2014, 2025)]


def test_weekly_positivity_drops_weeks_with_more_positives_than_specimens():
    """FluNet has at least one such week (BRA, 125%) -- a data error, not a rate."""
    rows = [_row("2018-03-05", 8, 10), _row("2018-03-12", 10, 2)]
    series = weekly_positivity(rows)
    assert [w.week_start for w in series] == [date(2018, 3, 12)]


def test_country_threshold_override_applies(monkeypatch):
    """IDN runs at a 20% baseline, so a 15% run is not an onset there but is one elsewhere."""
    monkeypatch.setattr(ground_truth, "ONSET_THRESHOLD_PCT_BY_COUNTRY", {"IDN": 20.0})
    start = date(2023, 1, 2)
    pcts = [12.0] * 4 + [15.0] * 3
    assert find_onsets(_series(start, pcts), "IDN", 1, 2023, 2023) == []
    assert find_onsets(_series(start, [5.0] * 4 + [15.0] * 3), "KEN", 1, 2023, 2023) != []

    idn = find_onsets(_series(start, [12.0] * 4 + [25.0] * 3), "IDN", 1, 2023, 2023)
    assert [o.onset_date for o in idn] == [start + timedelta(weeks=4)]


def test_aus_march_frame_lets_the_winter_season_beat_a_january_bump(monkeypatch):
    monkeypatch.setattr(ground_truth, "SEASON_START_MONTH", {"AUS": 3})
    start = date(2016, 11, 28)
    # Low Dec, a January bump, low Feb-Jun, winter rise in July.
    pcts = [LOW] * 6 + [HIGH] * 4 + [LOW] * 21 + [HIGH] * 8
    month = ground_truth.frame_start_month_for("AUS")
    onsets = find_onsets(_series(start, pcts), "AUS", month, 2017, 2017)
    assert [o.onset_date for o in onsets] == [start + timedelta(weeks=31)]
    assert onsets[0].onset_date.month == 7


def test_rising_edge_requires_calendar_contiguous_weeks():
    """Skipped weeks (no specimens, data errors) must not let the
    below-threshold lookback or the sustained run span a reporting gap."""
    start = date(2023, 1, 2)
    weeks = _series(start, [LOW] * 4 + [HIGH] * 3)
    with_gap_before = weeks[:3] + [WeeklyPositivity(w.week_start + timedelta(weeks=8), w.positivity_pct)
                                   for w in weeks[3:]]
    assert find_onsets(with_gap_before, "KEN", 1, 2023, 2023) == []

    with_gap_in_run = weeks[:5] + [WeeklyPositivity(w.week_start + timedelta(weeks=8), w.positivity_pct)
                                   for w in weeks[5:]]
    assert find_onsets(with_gap_in_run, "KEN", 1, 2023, 2023) == []
