import pytest

from pipeline.gdelt.flu_filter import find_matching_countries
from pipeline.gdelt.gkg_parser import GkgRecord


def make_record(url: str, country_codes: frozenset[str]) -> GkgRecord:
    return GkgRecord(url=url, country_codes=country_codes)


@pytest.mark.unit
class TestFindMatchingCountries:
    def test_matches_flu_term_and_target_country(self):
        record = make_record("http://news.example.com/flu-outbreak-nairobi", frozenset({"KE"}))
        assert find_matching_countries(record, ["KEN"]) == ["KEN"]

    def test_no_match_when_flu_term_absent(self):
        record = make_record("http://news.example.com/election-results", frozenset({"KE"}))
        assert find_matching_countries(record, ["KEN"]) == []

    def test_no_match_when_country_not_in_target_list(self):
        record = make_record("http://news.example.com/flu-outbreak", frozenset({"BR"}))
        assert find_matching_countries(record, ["KEN"]) == []

    def test_matches_multiple_target_countries_in_one_pass(self):
        record = make_record(
            "http://news.example.com/influenza-cases-surge", frozenset({"KE", "UK"})
        )
        assert set(find_matching_countries(record, ["KEN", "GBR", "USA"])) == {"KEN", "GBR"}

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/fluid-power-equipment",
            "http://example.com/hydrofluoric-acid-market",
            "http://example.com/influencer-marketing-tips",
            "http://example.com/flutter-entertainment-earnings",
        ],
    )
    def test_known_false_positive_urls_do_not_match(self, url):
        record = make_record(url, frozenset({"US"}))
        assert find_matching_countries(record, ["USA"]) == []

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/flu-outbreak-hospitals",
            "http://example.com/influenza-cases-rise",
            "http://example.com/news/flu/season-begins",
        ],
    )
    def test_known_true_positive_urls_match(self, url):
        record = make_record(url, frozenset({"US"}))
        assert find_matching_countries(record, ["USA"]) == ["USA"]

    def test_empty_target_countries_returns_empty(self):
        record = make_record("http://example.com/flu-outbreak", frozenset({"US"}))
        assert find_matching_countries(record, []) == []
