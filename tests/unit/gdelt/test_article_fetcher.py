import pytest

from pipeline.gdelt.article_fetcher import fetch_article_text, strip_html


@pytest.mark.unit
class TestStripHtml:
    def test_strips_basic_tags(self):
        html = "<html><body><p>Hello <b>world</b></p></body></html>"
        assert strip_html(html) == "Hello world"

    def test_excludes_script_and_style_content(self):
        html = "<html><head><style>.a{color:red}</style></head><body><script>alert(1)</script><p>Text</p></body></html>"
        assert strip_html(html) == "Text"

    def test_collapses_whitespace_between_block_elements(self):
        html = "<div>First</div><div>Second</div>"
        result = strip_html(html)
        assert "First" in result
        assert "Second" in result

    def test_empty_html_returns_empty_string(self):
        assert strip_html("") == ""

    def test_malformed_html_does_not_raise(self):
        html = "<div><p>Unclosed paragraph<div>Nested"
        result = strip_html(html)
        assert "Unclosed paragraph" in result
        assert "Nested" in result


@pytest.mark.unit
class TestFetchArticleText:
    def test_retrievable_true_when_text_is_long_enough(self, requests_mock):
        long_text = "word " * 100
        requests_mock.get("https://example.test/article", text=f"<p>{long_text}</p>")
        result = fetch_article_text("https://example.test/article")
        assert result.retrievable is True
        assert "word" in result.text

    def test_retrievable_false_when_text_is_too_short(self, requests_mock):
        requests_mock.get("https://example.test/short", text="<p>Hi</p>")
        result = fetch_article_text("https://example.test/short")
        assert result.retrievable is False

    def test_fetch_failure_returns_non_retrievable_empty_text(self, requests_mock):
        requests_mock.get("https://example.test/down", status_code=500)
        result = fetch_article_text("https://example.test/down", max_retries=1, backoff_base=0.0)
        assert result.retrievable is False
        assert result.text == ""
