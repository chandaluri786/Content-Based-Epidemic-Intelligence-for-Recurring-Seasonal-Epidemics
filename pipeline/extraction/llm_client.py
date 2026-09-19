"""LLM extraction client (Step 3).

ExtractionClient is a Protocol so the concrete provider is swappable and unit
tests can inject a fake without hitting a real API. GroqExtractionClient uses
Groq's free tier through the OpenAI-compatible endpoint (already-installed
`openai` SDK, no new dependency). Confirmed empirically against the live API:
there is no meaningful RPM throttle, but there are two independent per-model
daily rolling-window caps -- 1000 requests/day (RPD) and, the one that binds
first given this prompt's size, 200,000 tokens/day (TPD). A 429 from either
is treated as "this model's quota is used up for now" -- MultiModelExtractionClient
falls through to the next pooled model rather than retrying the same one.

A single structured-output call returns `relevant`/`confidence` together with
the rest of the schema -- not a separate relevance-classification call --
since judging real-signal-vs-explainer is exactly what the LLM already has to
do to fill `severity`/`strain` correctly.

Any failure (network, rate limit, malformed JSON, schema violation) for one
article is retried up to max_retries times and then returned as an
ExtractionFailure -- it must never raise past the caller and abort a batch.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from openai import OpenAI

from pipeline.config import (
    EXTRACTION_BACKOFF_BASE_SECONDS,
    EXTRACTION_MAX_RETRIES,
    EXTRACTION_MAX_TOKENS,
    GROQ_API_BASE_URL,
    GROQ_MIN_INTERVAL_SECONDS,
    GROQ_MODEL,
    GROQ_REASONING_EFFORT,
)
from pipeline.extraction.prompt import build_extraction_messages
from pipeline.extraction.schema import ArticleExtraction


@dataclass(frozen=True)
class ExtractionFailure:
    reason: str


class DailyQuotaExceeded(Exception):
    """Raised when the provider returns 429 -- treated as "today's request
    quota is used up," not a per-article failure worth retrying. Callers
    running a large batch should catch this, stop cleanly, and resume the
    remaining articles on a later day."""


class ExtractionClient(Protocol):
    model: str

    def extract(
        self, article_text: str, country_hint: str
    ) -> ArticleExtraction | ExtractionFailure: ...


_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "article_extraction",
        "schema": ArticleExtraction.model_json_schema(),
    },
}


class GroqExtractionClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = GROQ_MODEL,
        client: Any | None = None,
        max_retries: int = EXTRACTION_MAX_RETRIES,
        backoff_base: float = EXTRACTION_BACKOFF_BASE_SECONDS,
        min_interval_seconds: float = GROQ_MIN_INTERVAL_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client or OpenAI(base_url=GROQ_API_BASE_URL, api_key=api_key)
        self._model = model
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._min_interval = min_interval_seconds
        self._sleep = sleep_fn
        self._time = time_fn
        self._last_call_at: float | None = None

    @property
    def model(self) -> str:
        return self._model

    def _pace(self) -> None:
        if self._last_call_at is not None:
            wait = self._min_interval - (self._time() - self._last_call_at)
            if wait > 0:
                self._sleep(wait)
        self._last_call_at = self._time()

    def extract(
        self, article_text: str, country_hint: str
    ) -> ArticleExtraction | ExtractionFailure:
        messages = build_extraction_messages(article_text, country_hint)
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            self._pace()
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    response_format=_RESPONSE_FORMAT,
                    max_tokens=EXTRACTION_MAX_TOKENS,
                    reasoning_effort=GROQ_REASONING_EFFORT,
                )
                content = response.choices[0].message.content
                data = json.loads(content)
                return ArticleExtraction(**data)
            except Exception as exc:
                if getattr(exc, "status_code", None) == 429:
                    raise DailyQuotaExceeded(str(exc)) from exc
                last_error = exc
                is_last_attempt = attempt == self._max_retries - 1
                if not is_last_attempt:
                    self._sleep(self._backoff_base * (2**attempt))

        return ExtractionFailure(reason=f"{type(last_error).__name__}: {last_error}")
