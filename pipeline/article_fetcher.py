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
    """Returns the raw HTML, or None if every retry failed.

    Confirmed live, not hypothetical: one real site sent a redirect whose
    Location header contained invalid UTF-8 bytes, which crashed deep
    inside requests' own redirect-following code with a UnicodeDecodeError
    -- not a requests.RequestException, so it wasn't caught here and took
    down the entire run. Same category of problem as the oversized-CSV-
    field crash in gkg_parser.py: one malformed response from one site
    should never crash a multi-hour job. Caught explicitly rather than a
    blanket `except Exception`, so a genuinely new/unexpected failure mode
    still surfaces instead of being silently swallowed."""
    for attempt in range(HTTP_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.text
        except (requests.RequestException, UnicodeDecodeError):
            if attempt < HTTP_MAX_RETRIES:
                time.sleep(HTTP_BACKOFF_BASE_SECONDS * (2 ** attempt))
    return None
