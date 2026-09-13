"""Fetch article HTML and strip it to plain text (Step 2/3 boundary).

`retrievable` uses the exact method the feasibility spike used
(len(text.strip()) > RETRIEVABLE_MIN_TEXT_LEN), so full-scale numbers stay
comparable to the spike's 88% figure in evaluation/retrievability_report.py.
"""

from dataclasses import dataclass
from html.parser import HTMLParser

from pipeline.common.http import RequestFailedError, get_with_retry
from pipeline.config import RETRIEVABLE_MIN_TEXT_LEN

_SKIP_TAGS = {"script", "style"}


class _TextExtractingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._chunks.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._chunks)


def strip_html(html: str) -> str:
    parser = _TextExtractingParser()
    parser.feed(html)
    return parser.get_text()


@dataclass(frozen=True)
class FetchedArticle:
    url: str
    text: str
    retrievable: bool


def fetch_article_text(url: str, max_retries: int = 2, backoff_base: float = 1.0) -> FetchedArticle:
    try:
        response = get_with_retry(url, max_retries=max_retries, backoff_base=backoff_base)
    except RequestFailedError:
        return FetchedArticle(url=url, text="", retrievable=False)

    text = strip_html(response.text)
    return FetchedArticle(
        url=url, text=text, retrievable=len(text.strip()) > RETRIEVABLE_MIN_TEXT_LEN
    )
