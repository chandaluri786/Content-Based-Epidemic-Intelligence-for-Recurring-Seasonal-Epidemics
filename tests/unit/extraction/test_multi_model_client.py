import pytest

from pipeline.extraction.llm_client import DailyQuotaExceeded, ExtractionFailure
from pipeline.extraction.multi_model_client import MultiModelExtractionClient
from pipeline.extraction.schema import ArticleExtraction

VALID_EXTRACTION = ArticleExtraction(
    disease_signal=True,
    relevant=True,
    severity="severe",
    symptoms=["fever"],
    strain="h3n2",
    location_mentioned="Nairobi",
    confidence=0.9,
)


class FakeClient:
    """Injectable fake matching the ExtractionClient protocol."""

    def __init__(self, results, model="fake-model"):
        self._results = list(results)
        self.model = model
        self.calls = 0

    def extract(self, article_text, country_hint):
        self.calls += 1
        result = self._results.pop(0)
        if result == "quota":
            raise DailyQuotaExceeded("exhausted")
        return result


@pytest.mark.unit
class TestMultiModelExtractionClient:
    def test_uses_first_client_while_it_has_quota(self):
        client_a = FakeClient([VALID_EXTRACTION, VALID_EXTRACTION])
        client_b = FakeClient([VALID_EXTRACTION])
        multi = MultiModelExtractionClient([client_a, client_b])

        multi.extract("text", "USA")
        multi.extract("text", "USA")

        assert client_a.calls == 2
        assert client_b.calls == 0

    def test_last_used_model_reflects_which_client_handled_the_call(self):
        client_a = FakeClient([VALID_EXTRACTION], model="model-a")
        client_b = FakeClient([VALID_EXTRACTION], model="model-b")
        multi = MultiModelExtractionClient([client_a, client_b])

        multi.extract("text", "USA")
        assert multi.last_used_model == "model-a"

    def test_last_used_model_updates_after_falling_through(self):
        client_a = FakeClient(["quota"], model="model-a")
        client_b = FakeClient([VALID_EXTRACTION], model="model-b")
        multi = MultiModelExtractionClient([client_a, client_b])

        multi.extract("text", "USA")
        assert multi.last_used_model == "model-b"

    def test_falls_through_to_next_client_on_quota_exceeded(self):
        client_a = FakeClient(["quota"])
        client_b = FakeClient([VALID_EXTRACTION])
        multi = MultiModelExtractionClient([client_a, client_b])

        result = multi.extract("text", "USA")

        assert result is VALID_EXTRACTION
        assert client_a.calls == 1
        assert client_b.calls == 1

    def test_stays_on_second_client_for_subsequent_calls_once_switched(self):
        client_a = FakeClient(["quota"])
        client_b = FakeClient([VALID_EXTRACTION, VALID_EXTRACTION])
        multi = MultiModelExtractionClient([client_a, client_b])

        multi.extract("text", "USA")
        multi.extract("text", "USA")

        assert client_a.calls == 1
        assert client_b.calls == 2

    def test_raises_daily_quota_exceeded_when_every_client_is_exhausted(self):
        client_a = FakeClient(["quota"])
        client_b = FakeClient(["quota"])
        multi = MultiModelExtractionClient([client_a, client_b])

        with pytest.raises(DailyQuotaExceeded):
            multi.extract("text", "USA")

    def test_extraction_failure_from_a_client_is_returned_not_treated_as_quota(self):
        failure = ExtractionFailure(reason="boom")
        client_a = FakeClient([failure])
        client_b = FakeClient([VALID_EXTRACTION])
        multi = MultiModelExtractionClient([client_a, client_b])

        result = multi.extract("text", "USA")

        assert result is failure
        assert client_b.calls == 0

    def test_empty_client_list_raises_value_error(self):
        with pytest.raises(ValueError):
            MultiModelExtractionClient([])
