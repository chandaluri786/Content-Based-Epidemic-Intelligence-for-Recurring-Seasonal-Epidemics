"""
Stage 6: fetch one article's raw HTML.

Plain HTTP GET -- no headless browser. See README "Known limitations" for
why: bot-blocking and JS-rendering are both real, confirmed failure modes,
but without first diagnosing what fraction of failures each one actually
causes, adding browser-automation complexity is a guess at where the
problem is, not a targeted fix.
"""

from __future__ import annotations

import time

import requests

from config import HTTP_BACKOFF_BASE_SECONDS, HTTP_MAX_RETRIES, HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT

_HEADERS = {"User-Agent": HTTP_USER_AGENT}


def fetch_html(url: str) -> str | None:
    """Returns the raw HTML, or None if every retry failed."""
    for attempt in range(HTTP_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException:
            if attempt < HTTP_MAX_RETRIES:
                time.sleep(HTTP_BACKOFF_BASE_SECONDS * (2 ** attempt))
    return None
