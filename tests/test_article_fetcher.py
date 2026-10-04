"""
Unit test for Stage 6's fetch_html -- mocks requests.get so this doesn't
need live network access, consistent with how other network-dependent
stages are left untested per README (except this one specific regression,
which is cheap to verify without a real request). Run with: pytest
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.article_fetcher import fetch_html


def test_fetch_html_returns_none_on_unicode_decode_error_instead_of_crashing():
    """Real failure, confirmed live: a site's redirect Location header
    contained invalid UTF-8 bytes, which crashed deep inside requests'
    redirect-following code with UnicodeDecodeError -- not a
    requests.RequestException, so the original except clause didn't catch
    it and it took down the entire multi-hour run. fetch_html must not
    propagate this; it should return None like any other failed fetch."""
    with patch("pipeline.article_fetcher.requests.get", side_effect=UnicodeDecodeError("utf-8", b"\xf1", 0, 1, "invalid continuation byte")):
        assert fetch_html("https://example.com/broken-redirect") is None
