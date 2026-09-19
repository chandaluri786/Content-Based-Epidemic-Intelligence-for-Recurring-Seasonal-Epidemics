"""Shared retry/backoff GET wrapper for all external HTTP calls.

Used by ground_truth/flunet_client.py, ground_truth/ukhsa_client.py, and
gdelt/article_fetcher.py so retry/backoff behavior is defined once.
"""

import time
from typing import Any

import requests

DEFAULT_TIMEOUT_SECONDS = 30
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# requests' own default ("python-requests/x.y.z") gets blocked or served a
# stub/redirect page by several mainstream news outlets (confirmed empirically
# against Daily Mail, Business Standard, Yahoo News, Zawya, iHeartRadio -- see
# dev/active/flu-pipeline/context.md). A standard browser UA is not full bot
# evasion, but it clears this specific, identified failure mode.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class RequestFailedError(Exception):
    """Raised when a GET request fails and either isn't retryable or exhausts retries."""


class NotFoundError(RequestFailedError):
    """Raised for a 404 specifically, so callers can treat "genuinely doesn't
    exist" (e.g. a GDELT date before the GKG 2.0 launch) differently from a
    transient failure worth retrying later."""


def get_with_retry(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = 3,
    backoff_base: float = 2.0,
) -> requests.Response:
    """GET url, retrying on network errors and retryable HTTP status codes with
    exponential backoff (backoff_base * 2**attempt seconds). Non-retryable HTTP
    errors (e.g. 404) raise immediately without consuming a retry."""
    last_error: Exception | None = None
    request_headers = {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=request_headers, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            last_error = exc
        else:
            if response.status_code < 400:
                return response
            if response.status_code == 404:
                raise NotFoundError(f"GET {url} returned 404")
            if response.status_code not in RETRYABLE_STATUS_CODES:
                raise RequestFailedError(
                    f"GET {url} failed with non-retryable status {response.status_code}"
                )
            last_error = RequestFailedError(
                f"GET {url} failed with retryable status {response.status_code}"
            )

        is_last_attempt = attempt == max_retries - 1
        if not is_last_attempt:
            time.sleep(backoff_base * (2**attempt))

    raise RequestFailedError(f"GET {url} failed after {max_retries} attempts: {last_error}")
