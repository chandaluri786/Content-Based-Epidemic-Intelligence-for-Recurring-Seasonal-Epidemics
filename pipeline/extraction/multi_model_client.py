"""Waterfalls extraction calls across multiple ExtractionClient instances
(different models), each with its own independent daily-quota pool.

Confirmed empirically (2026-09-13): Groq's 1000 RPD cap is tracked per model,
not account-wide -- a burst of calls to one model did not move another
model's remaining-requests counter. So exhausting one model's daily quota
and falling through to the next multiplies today's effective throughput,
rather than requiring a multi-day wait on a single model.
"""

from pipeline.extraction.llm_client import DailyQuotaExceeded, ExtractionClient, ExtractionFailure
from pipeline.extraction.schema import ArticleExtraction


class MultiModelExtractionClient:
    def __init__(self, clients: list[ExtractionClient]) -> None:
        if not clients:
            raise ValueError("at least one client is required")
        self._clients = clients
        self._current_index = 0
        self.last_used_model: str | None = None

    def extract(
        self, article_text: str, country_hint: str
    ) -> ArticleExtraction | ExtractionFailure:
        while self._current_index < len(self._clients):
            current_client = self._clients[self._current_index]
            try:
                result = current_client.extract(article_text, country_hint)
            except DailyQuotaExceeded:
                self._current_index += 1
                continue
            self.last_used_model = current_client.model
            return result

        raise DailyQuotaExceeded("every configured model has exhausted today's quota")
