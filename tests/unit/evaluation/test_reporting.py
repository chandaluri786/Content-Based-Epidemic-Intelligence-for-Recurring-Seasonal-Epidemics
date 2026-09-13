import pytest

from pipeline.evaluation.lead_time_report import LeadTimeSummary
from pipeline.evaluation.reporting import render_final_report
from pipeline.evaluation.retrievability_report import CountryRetrievabilitySummary


def make_summary(**overrides) -> LeadTimeSummary:
    defaults = {
        "n_total": 10,
        "n_excluded": 1,
        "n_content_detected": 8,
        "n_frequency_detected": 6,
        "content_lead_mean_days": -9.5,
        "content_lead_median_days": -8.0,
        "content_lead_stdev_days": 3.2,
        "frequency_lead_mean_days": -2.0,
        "frequency_lead_median_days": -1.0,
        "frequency_lead_stdev_days": 1.5,
        "content_win_rate": 0.75,
    }
    defaults.update(overrides)
    return LeadTimeSummary(**defaults)


@pytest.mark.unit
class TestRenderFinalReport:
    def test_includes_lead_time_headline_numbers(self):
        report = render_final_report(make_summary(), [], limitations=[])
        assert "-9.5" in report
        assert "0.75" in report or "75" in report

    def test_includes_retrievability_numbers_per_country(self):
        retrievability = [CountryRetrievabilitySummary("USA", 20, 90.0, 85.0)]
        report = render_final_report(make_summary(), retrievability, limitations=[])
        assert "USA" in report
        assert "90.0" in report

    def test_includes_limitations_section(self):
        report = render_final_report(
            make_summary(),
            [],
            limitations=["Brazil/Indonesia excluded from GDELT ingestion (33% content-rich)."],
        )
        assert "Brazil/Indonesia excluded" in report

    def test_handles_none_values_in_summary_gracefully(self):
        summary = make_summary(
            content_lead_mean_days=None,
            content_lead_median_days=None,
            content_lead_stdev_days=None,
            content_win_rate=None,
        )
        report = render_final_report(summary, [], limitations=[])
        assert "N/A" in report
