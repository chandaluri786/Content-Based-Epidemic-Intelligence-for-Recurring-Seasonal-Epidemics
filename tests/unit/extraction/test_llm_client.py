import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pipeline.extraction.llm_client import (
    DailyQuotaExceeded,
    ExtractionFailure,
    GroqExtractionClient,
)
from pipeline.extraction.schema import ArticleExtraction

VALID_PAYLOAD = {
    "disease_signal": True,
    "relevant": True,
    "severity": "severe",
    "symptoms": ["fever"],
    "strain": "h3n2",
    "location_mentioned": "Nairobi",
    "confidence": 0.9,
}


def fake_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def make_client(create_side_effect, **kwargs):
    fake_openai_client = MagicMock()
    fake_openai_client.chat.completions.create.side_effect = create_side_effect
    clock = {"t": 0.0}
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["t"] += seconds

    def fake_time():
        return clock["t"]

    client = GroqExtractionClient(
        client=fake_openai_client,
        sleep_fn=fake_sleep,
        time_fn=fake_time,
        **kwargs,
    )
    return client, fake_openai_client, sleeps


@pytest.mark.unit
class TestGroqExtractionClient:
    def test_returns_valid_extraction_on_first_success(self):
        client, _openai_client, _ = make_client([fake_response(json.dumps(VALID_PAYLOAD))])
        result = client.extract("some article text", country_hint="Kenya")
        assert isinstance(result, ArticleExtraction)
        assert result.strain == "h3n2"

    def test_retries_after_transient_exception_then_succeeds(self):
        client, openai_client, sleeps = make_client(
            [Exception("rate limited"), fake_response(json.dumps(VALID_PAYLOAD))],
            max_retries=3,
        )
        result = client.extract("text", country_hint="Kenya")
        assert isinstance(result, ArticleExtraction)
        assert openai_client.chat.completions.create.call_count == 2
        assert len(sleeps) >= 1

    def test_returns_extraction_failure_after_exhausting_retries(self):
        client, _openai_client, _ = make_client(
            [Exception("down")] * 3,
            max_retries=3,
        )
        result = client.extract("text", country_hint="Kenya")
        assert isinstance(result, ExtractionFailure)
        assert "down" in result.reason

    def test_malformed_json_returns_extraction_failure_not_raise(self):
        client, _openai_client, _ = make_client(
            [fake_response("not valid json{{{")] * 3,
            max_retries=3,
        )
        result = client.extract("text", country_hint="Kenya")
        assert isinstance(result, ExtractionFailure)

    def test_schema_violation_returns_extraction_failure_not_raise(self):
        bad_payload = dict(VALID_PAYLOAD, severity="catastrophic")
        client, _openai_client, _ = make_client(
            [fake_response(json.dumps(bad_payload))] * 3,
            max_retries=3,
        )
        result = client.extract("text", country_hint="Kenya")
        assert isinstance(result, ExtractionFailure)

    def test_paces_calls_to_respect_min_interval(self):
        client, _openai_client, sleeps = make_client(
            [
                fake_response(json.dumps(VALID_PAYLOAD)),
                fake_response(json.dumps(VALID_PAYLOAD)),
            ],
            min_interval_seconds=2.0,
        )
        client.extract("text", country_hint="Kenya")
        client.extract("text", country_hint="Kenya")
        assert any(s == pytest.approx(2.0) for s in sleeps)

    def test_does_not_sleep_extra_when_enough_time_has_already_passed(self):
        fake_openai_client = MagicMock()
        fake_openai_client.chat.completions.create.side_effect = [
            fake_response(json.dumps(VALID_PAYLOAD)),
            fake_response(json.dumps(VALID_PAYLOAD)),
        ]
        clock = {"t": 0.0}
        sleeps = []

        client = GroqExtractionClient(
            client=fake_openai_client,
            sleep_fn=lambda s: sleeps.append(s),
            time_fn=lambda: clock["t"],
            min_interval_seconds=2.0,
        )
        client.extract("text", country_hint="Kenya")
        clock["t"] += 10.0  # plenty of time has passed since the last call
        client.extract("text", country_hint="Kenya")
        assert sleeps == []

    def test_429_raises_daily_quota_exceeded_without_retrying(self):
        rate_limit_exc = Exception("rate limit exceeded")
        rate_limit_exc.status_code = 429
        client, openai_client, _ = make_client([rate_limit_exc], max_retries=3)
        with pytest.raises(DailyQuotaExceeded):
            client.extract("text", country_hint="Kenya")
        assert openai_client.chat.completions.create.call_count == 1

    def test_non_429_exception_with_status_code_still_retries_normally(self):
        server_error = Exception("server error")
        server_error.status_code = 500
        client, openai_client, _ = make_client(
            [server_error, fake_response(json.dumps(VALID_PAYLOAD))], max_retries=3
        )
        result = client.extract("text", country_hint="Kenya")
        assert isinstance(result, ArticleExtraction)
        assert openai_client.chat.completions.create.call_count == 2

    def test_passes_max_tokens_to_bound_completion_length(self):
        client, openai_client, _ = make_client([fake_response(json.dumps(VALID_PAYLOAD))])
        client.extract("text", country_hint="Kenya")
        _, kwargs = openai_client.chat.completions.create.call_args
        assert kwargs["max_tokens"] > 0

    def test_model_property_exposes_configured_model_name(self):
        fake_openai_client = MagicMock()
        client = GroqExtractionClient(client=fake_openai_client, model="some-model-name")
        assert client.model == "some-model-name"

    def test_passes_low_reasoning_effort_to_stay_within_the_completion_budget(self):
        # gpt-oss models spend completion tokens on hidden reasoning before
        # emitting JSON -- confirmed empirically that the default effort
        # blows the EXTRACTION_MAX_TOKENS budget on this schema's primary_country
        # judgment (reasoning_tokens alone exceeded 300), causing
        # json_validate_failed on nearly every real call. "low" keeps the
        # response inside budget without needing to raise max_tokens (which
        # would directly cut the Groq TPD-bound daily throughput).
        client, openai_client, _ = make_client([fake_response(json.dumps(VALID_PAYLOAD))])
        client.extract("text", country_hint="Kenya")
        _, kwargs = openai_client.chat.completions.create.call_args
        assert kwargs["reasoning_effort"] == "low"

    def test_passes_country_hint_into_the_prompt(self):
        client, openai_client, _ = make_client([fake_response(json.dumps(VALID_PAYLOAD))])
        client.extract("article body", country_hint="Kenya")
        _, kwargs = openai_client.chat.completions.create.call_args
        user_message = kwargs["messages"][1]["content"]
        assert "Kenya" in user_message
        assert "article body" in user_message
