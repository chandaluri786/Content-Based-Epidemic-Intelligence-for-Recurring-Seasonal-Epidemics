import pytest

from pipeline.extraction.relevance import passes_rule_prefilter


@pytest.mark.unit
class TestPassesRulePrefilter:
    def test_text_with_a_content_marker_passes(self):
        assert passes_rule_prefilter("Health officials report a surge in flu cases this week.")

    def test_text_with_no_content_markers_fails(self):
        assert not passes_rule_prefilter(
            "Flu season is a great time to get outside and enjoy life."
        )

    def test_is_case_insensitive(self):
        assert passes_rule_prefilter("A new OUTBREAK has been reported.")

    def test_empty_text_fails(self):
        assert not passes_rule_prefilter("")

    def test_who_bare_substring_does_not_count_but_full_phrase_does(self):
        assert not passes_rule_prefilter("Officials who said the situation is stable.")
        assert passes_rule_prefilter("The World Health Organization issued a statement.")

    def test_min_markers_above_one_requires_multiple_hits(self):
        # Contains exactly 3 distinct markers: "case", "death", "severe".
        text = "A death was reported following a severe case."
        assert passes_rule_prefilter(text, min_markers=1)
        assert passes_rule_prefilter(text, min_markers=3)
        assert not passes_rule_prefilter(text, min_markers=4)
