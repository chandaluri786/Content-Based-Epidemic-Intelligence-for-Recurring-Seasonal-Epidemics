from datetime import date, timedelta

import pytest

from pipeline.detection.lead_time import build_lead_time_row, compute_lead_time_days
from pipeline.join.epiweek_join import CountryWeekJoined


def make_week(week_index: int, relevant: int, raw: int) -> CountryWeekJoined:
    week_start = date(2023, 1, 2) + timedelta(weeks=week_index)
    return CountryWeekJoined(
        country_iso3="USA",
        season_year=2023,
        iso_year=2023,
        iso_week=week_index + 1,
        week_start_date=week_start,
        content_relevant_count=relevant,
        frequency_raw_count=raw,
        is_baseline_week=week_index < 4,
        days_from_onset=0,
    )


@pytest.mark.unit
class TestComputeLeadTimeDays:
    def test_none_signal_date_returns_none(self):
        assert compute_lead_time_days(None, date(2023, 2, 1)) is None

    def test_earlier_signal_gives_negative_lead_time(self):
        assert compute_lead_time_days(date(2023, 1, 25), date(2023, 2, 1)) == -7

    def test_later_signal_gives_positive_lead_time(self):
        assert compute_lead_time_days(date(2023, 2, 8), date(2023, 2, 1)) == 7


@pytest.mark.unit
class TestBuildLeadTimeRow:
    def test_insufficient_total_articles_is_excluded(self):
        weeks = [make_week(i, 0, 1) for i in range(8)]  # 8 total raw articles
        row = build_lead_time_row(
            "USA", 2023, date(2023, 2, 1), "positivity_2wk", weeks, min_total_articles=10
        )
        assert row.excluded_reason == "insufficient_data"
        assert row.content_signal_date is None
        assert row.frequency_signal_date is None

    def test_sufficient_data_computes_both_signals(self):
        counts = [0, 0, 0, 0, 10, 12, 0, 0]
        weeks = [make_week(i, c, c) for i, c in enumerate(counts)]
        row = build_lead_time_row(
            "USA", 2023, date(2023, 2, 20), "positivity_2wk", weeks, min_total_articles=10
        )
        assert row.excluded_reason is None
        assert row.content_signal_date is not None
        assert row.frequency_signal_date is not None
        assert row.content_lead_time_days is not None

    def test_content_beats_frequency_true_when_content_leads_earlier(self):
        weeks = [make_week(i, 0, 0) for i in range(8)]
        weeks[4] = make_week(4, relevant=10, raw=0)
        weeks[5] = make_week(5, relevant=12, raw=0)
        row = build_lead_time_row(
            "USA", 2023, date(2023, 2, 20), "positivity_2wk", weeks, min_total_articles=1
        )
        assert row.content_signal_date is not None
        assert row.frequency_signal_date is None
        assert row.content_beats_frequency is True

    def test_content_beats_frequency_false_when_only_frequency_detects(self):
        weeks = [make_week(i, 0, 0) for i in range(8)]
        weeks[4] = make_week(4, relevant=0, raw=10)
        weeks[5] = make_week(5, relevant=0, raw=12)
        row = build_lead_time_row(
            "USA", 2023, date(2023, 2, 20), "positivity_2wk", weeks, min_total_articles=1
        )
        assert row.content_signal_date is None
        assert row.frequency_signal_date is not None
        assert row.content_beats_frequency is False

    def test_content_beats_frequency_none_when_neither_detects(self):
        weeks = [make_week(i, 0, 0) for i in range(8)]
        row = build_lead_time_row(
            "USA", 2023, date(2023, 2, 20), "positivity_2wk", weeks, min_total_articles=0
        )
        assert row.content_beats_frequency is None

    def test_content_beats_frequency_compares_lead_times_when_both_detect(self):
        weeks = [make_week(i, 0, 0) for i in range(10)]
        # Content crosses earlier (index 4) than frequency (index 6).
        weeks[4] = make_week(4, relevant=10, raw=0)
        weeks[5] = make_week(5, relevant=12, raw=0)
        weeks[6] = make_week(6, relevant=0, raw=10)
        weeks[7] = make_week(7, relevant=0, raw=12)
        row = build_lead_time_row(
            "USA", 2023, date(2023, 3, 1), "positivity_2wk", weeks, min_total_articles=1
        )
        assert row.content_beats_frequency is True
