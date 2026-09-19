import pytest

from pipeline.extraction.geo_crosscheck import classify_geo_match


@pytest.mark.unit
class TestClassifyGeoMatch:
    def test_matching_country_agrees(self):
        assert classify_geo_match(primary_country="KEN", gdelt_country="KEN") == "agree"

    def test_none_primary_country_is_ambiguous(self):
        assert classify_geo_match(primary_country=None, gdelt_country="KEN") == "ambiguous"

    def test_different_cohort_country_disagrees(self):
        assert classify_geo_match(primary_country="USA", gdelt_country="KEN") == "disagree"

    def test_other_disagrees(self):
        assert classify_geo_match(primary_country="other", gdelt_country="IND") == "disagree"

    def test_is_case_sensitive_to_iso3_codes(self):
        assert classify_geo_match(primary_country="ken", gdelt_country="KEN") == "disagree"
