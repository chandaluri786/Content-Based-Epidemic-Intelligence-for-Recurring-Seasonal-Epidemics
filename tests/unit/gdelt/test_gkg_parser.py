import pytest

from pipeline.gdelt.gkg_parser import parse_gkg_line

# A real line shape confirmed against live GKG 2.1 data:
# fields[4] = URL, fields[10] = V2Locations ("type#name#FIPS#adm1#lat#lon#featureid#offset", ; separated)
REAL_SHAPE_LINE = (
    "20231211003000-1\t20231211003000\t1\trsn.net.au\thttp://www.rsn.net.au/news/some-flu-story\t\t\t"
    "THEME1;THEME2\tcounts\t"
    "1#Ballarat, Victoria, Australia#AS#AS07#-37.5#143.8#-1557125#164\t"
    "4#Ballarat, Victoria, Australia#AS#AS07#-37.5#143.8#-1557125#164\tpersons\torgs\ttone\n"
)


@pytest.mark.unit
class TestParseGkgLine:
    def test_extracts_url_and_country_codes(self):
        record = parse_gkg_line(REAL_SHAPE_LINE)
        assert record is not None
        assert record.url == "http://www.rsn.net.au/news/some-flu-story"
        assert "AS" in record.country_codes

    def test_multiple_locations_yield_multiple_country_codes(self):
        line = (
            "id\tdate\t1\tsrc\thttp://example.com/story\t\t\tthemes\tcounts\t\t"
            "1#Nairobi, Kenya#KE#adm1#0#0#0#0;4#London, UK#UK#adm1#0#0#0#0\tp\to\tt\n"
        )
        record = parse_gkg_line(line)
        assert record.country_codes == frozenset({"KE", "UK"})

    def test_empty_locations_field_yields_empty_country_codes(self):
        line = "id\tdate\t1\tsrc\thttp://example.com/story\t\t\tthemes\tcounts\t\t\tp\to\tt\n"
        record = parse_gkg_line(line)
        assert record is not None
        assert record.country_codes == frozenset()

    def test_line_with_too_few_fields_returns_none(self):
        assert parse_gkg_line("only\tfour\tfields\there") is None

    def test_line_with_empty_url_returns_none(self):
        line = "id\tdate\t1\tsrc\t\t\t\tthemes\tcounts\t\tlocs\tp\to\tt\n"
        assert parse_gkg_line(line) is None

    def test_malformed_location_entry_is_skipped_not_fatal(self):
        line = (
            "id\tdate\t1\tsrc\thttp://example.com/story\t\t\tthemes\tcounts\t\t"
            "garbage-no-hashes;4#London, UK#UK#adm1#0#0#0#0\tp\to\tt\n"
        )
        record = parse_gkg_line(line)
        assert record.country_codes == frozenset({"UK"})
