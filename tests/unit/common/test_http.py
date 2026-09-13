import pytest
import requests

from pipeline.common.http import NotFoundError, RequestFailedError, get_with_retry


@pytest.mark.unit
class TestGetWithRetry:
    def test_returns_response_on_first_success(self, requests_mock):
        requests_mock.get("https://example.test/ok", text="hello", status_code=200)
        resp = get_with_retry("https://example.test/ok", max_retries=3, backoff_base=0.0)
        assert resp.text == "hello"

    def test_retries_on_5xx_then_succeeds(self, requests_mock):
        requests_mock.get(
            "https://example.test/flaky",
            [
                {"status_code": 500, "text": "err"},
                {"status_code": 200, "text": "ok"},
            ],
        )
        resp = get_with_retry("https://example.test/flaky", max_retries=3, backoff_base=0.0)
        assert resp.status_code == 200

    def test_retries_on_429_then_succeeds(self, requests_mock):
        requests_mock.get(
            "https://example.test/rate-limited",
            [
                {"status_code": 429, "text": "slow down"},
                {"status_code": 200, "text": "ok"},
            ],
        )
        resp = get_with_retry("https://example.test/rate-limited", max_retries=3, backoff_base=0.0)
        assert resp.status_code == 200

    def test_raises_request_failed_error_after_exhausting_retries(self, requests_mock):
        requests_mock.get("https://example.test/always-down", status_code=500)
        with pytest.raises(RequestFailedError):
            get_with_retry("https://example.test/always-down", max_retries=2, backoff_base=0.0)

    def test_raises_not_found_error_on_404_without_retrying(self, requests_mock):
        requests_mock.get("https://example.test/not-found", status_code=404)
        with pytest.raises(NotFoundError):
            get_with_retry("https://example.test/not-found", max_retries=3, backoff_base=0.0)
        assert requests_mock.call_count == 1

    def test_raises_request_failed_error_on_other_4xx_without_retrying(self, requests_mock):
        requests_mock.get("https://example.test/forbidden", status_code=403)
        with pytest.raises(RequestFailedError):
            get_with_retry("https://example.test/forbidden", max_retries=3, backoff_base=0.0)
        assert requests_mock.call_count == 1

    def test_not_found_error_is_a_request_failed_error(self):
        assert issubclass(NotFoundError, RequestFailedError)

    def test_network_exception_is_retried(self, requests_mock):
        requests_mock.get(
            "https://example.test/timeout",
            [
                {"exc": requests.exceptions.ConnectionError},
                {"status_code": 200, "text": "ok"},
            ],
        )
        resp = get_with_retry("https://example.test/timeout", max_retries=3, backoff_base=0.0)
        assert resp.status_code == 200

    def test_passes_params_and_headers_through(self, requests_mock):
        requests_mock.get("https://example.test/echo", text="ok", status_code=200)
        get_with_retry(
            "https://example.test/echo",
            params={"q": "flu"},
            headers={"User-Agent": "test-agent"},
            backoff_base=0.0,
        )
        last = requests_mock.last_request
        assert last.qs == {"q": ["flu"]}
        assert last.headers["User-Agent"] == "test-agent"
