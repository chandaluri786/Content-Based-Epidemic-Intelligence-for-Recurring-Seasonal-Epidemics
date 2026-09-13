import pytest

from pipeline.evaluation.retrievability_report import (
    SPIKE_BASELINE_PCT,
    ArticleRetrievabilityRecord,
    diverges_from_spike_baseline,
    summarize_retrievability,
)


def rec(country: str, retrievable: bool, content_rich: bool) -> ArticleRetrievabilityRecord:
    return ArticleRetrievabilityRecord(country, retrievable, content_rich)


@pytest.mark.unit
class TestSummarizeRetrievability:
    def test_computes_percentages_per_country(self):
        records = [
            rec("USA", True, True),
            rec("USA", True, False),
            rec("USA", False, False),
            rec("USA", True, True),
        ]
        summaries = {s.country_iso3: s for s in summarize_retrievability(records)}
        usa = summaries["USA"]
        assert usa.n_articles == 4
        assert usa.pct_retrievable == pytest.approx(75.0)
        assert usa.pct_content_rich == pytest.approx(50.0)

    def test_separates_countries(self):
        records = [rec("USA", True, True), rec("KEN", False, False)]
        summaries = {s.country_iso3: s for s in summarize_retrievability(records)}
        assert summaries["USA"].pct_retrievable == pytest.approx(100.0)
        assert summaries["KEN"].pct_retrievable == pytest.approx(0.0)

    def test_empty_records_returns_empty_list(self):
        assert summarize_retrievability([]) == []


@pytest.mark.unit
class TestDivergesFromSpikeBaseline:
    def test_no_divergence_when_close_to_spike_baseline(self):
        assert not diverges_from_spike_baseline(pct_value=85.0)

    def test_flags_divergence_when_more_than_ten_points_below(self):
        assert diverges_from_spike_baseline(pct_value=70.0)

    def test_flags_divergence_when_more_than_ten_points_above(self):
        assert diverges_from_spike_baseline(pct_value=99.0)

    def test_exactly_ten_points_is_not_flagged(self):
        assert not diverges_from_spike_baseline(pct_value=SPIKE_BASELINE_PCT - 10.0)
