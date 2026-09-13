from datetime import date

import pytest

from pipeline.detection.lead_time import LeadTimeRow
from pipeline.evaluation.lead_time_report import summarize_lead_times


def row(
    content_lead=None,
    frequency_lead=None,
    content_beats_frequency=None,
    excluded_reason=None,
) -> LeadTimeRow:
    return LeadTimeRow(
        country_iso3="USA",
        season_year=2023,
        official_onset_date=date(2023, 2, 1),
        official_onset_method="positivity_2wk",
        content_signal_date=date(2023, 1, 25) if content_lead is not None else None,
        content_lead_time_days=content_lead,
        frequency_signal_date=date(2023, 1, 25) if frequency_lead is not None else None,
        frequency_lead_time_days=frequency_lead,
        content_beats_frequency=content_beats_frequency,
        excluded_reason=excluded_reason,
    )


@pytest.mark.unit
class TestSummarizeLeadTimes:
    def test_empty_rows_returns_zeroed_summary(self):
        summary = summarize_lead_times([])
        assert summary.n_total == 0
        assert summary.content_lead_mean_days is None

    def test_counts_total_and_excluded_rows(self):
        rows = [
            row(excluded_reason="insufficient_data"),
            row(content_lead=-7, content_beats_frequency=True),
        ]
        summary = summarize_lead_times(rows)
        assert summary.n_total == 2
        assert summary.n_excluded == 1

    def test_computes_mean_median_stdev_for_content_lead_times(self):
        rows = [
            row(content_lead=-14, content_beats_frequency=True),
            row(content_lead=-7, content_beats_frequency=True),
            row(content_lead=0, content_beats_frequency=True),
        ]
        summary = summarize_lead_times(rows)
        assert summary.content_lead_mean_days == pytest.approx(-7.0)
        assert summary.content_lead_median_days == pytest.approx(-7.0)
        assert summary.n_content_detected == 3

    def test_content_win_rate_only_counts_comparable_rows(self):
        rows = [
            row(content_lead=-7, frequency_lead=0, content_beats_frequency=True),
            row(content_lead=0, frequency_lead=-7, content_beats_frequency=False),
            row(content_lead=None, frequency_lead=None, content_beats_frequency=None),
        ]
        summary = summarize_lead_times(rows)
        assert summary.content_win_rate == pytest.approx(0.5)

    def test_content_win_rate_is_none_when_no_comparable_rows(self):
        rows = [row(excluded_reason="insufficient_data")]
        summary = summarize_lead_times(rows)
        assert summary.content_win_rate is None

    def test_excluded_rows_do_not_pollute_detected_counts(self):
        rows = [row(excluded_reason="insufficient_data"), row()]
        summary = summarize_lead_times(rows)
        assert summary.n_content_detected == 0
        assert summary.n_frequency_detected == 0
