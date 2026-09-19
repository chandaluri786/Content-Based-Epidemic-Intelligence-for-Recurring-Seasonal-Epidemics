import pytest

from pipeline.gdelt.content_richness import score_content_richness

GENUINE_ARTICLE = (
    "Health officials in the region reported a sharp increase in influenza "
    "cases this week, with several hospitalizations linked to the H3N2 "
    "strain. The outbreak has prompted local clinics to expand vaccine "
    "availability ahead of the holiday season. Doctors say most patients "
    "report severe symptoms including high fever and persistent cough. "
    "The World Health Organization noted similar surges in neighboring "
    "countries this season, urging residents to seek care early if "
    "symptoms worsen. Officials expect the surge to peak within weeks."
)

# The demonstrated AUS false-positive failure mode: a real long article that
# happens to contain a challenge-adjacent phrase ("sign in") should not be
# flagged just because of that phrase.
LONG_ARTICLE_WITH_STRAY_PHRASE = GENUINE_ARTICLE + " Sign in to comment below."

NAV_BOILERPLATE_NO_PUNCTUATION = (
    "Home News Sport Weather Login Register Subscribe Home News Sport "
    "Weather Login Register Subscribe Home News Sport Weather"
)

COOKIE_CONSENT_STUB = (
    "We use cookies. By continuing you agree to our Privacy Policy. "
    "Click Accept to continue."
)


@pytest.mark.unit
class TestScoreContentRichness:
    def test_genuine_article_is_content_rich(self):
        score = score_content_richness(GENUINE_ARTICLE)
        assert score.is_content_rich is True

    def test_long_article_with_stray_challenge_phrase_is_not_penalized(self):
        score = score_content_richness(LONG_ARTICLE_WITH_STRAY_PHRASE)
        assert score.is_content_rich is True

    def test_nav_boilerplate_without_punctuation_is_rejected(self):
        score = score_content_richness(NAV_BOILERPLATE_NO_PUNCTUATION)
        assert score.is_content_rich is False
        assert score.sentence_count < 3

    def test_cookie_consent_stub_is_rejected(self):
        score = score_content_richness(COOKIE_CONSENT_STUB)
        assert score.is_content_rich is False
        assert score.content_marker_hits == 0

    def test_empty_text_is_rejected(self):
        score = score_content_richness("")
        assert score.is_content_rich is False
        assert score.text_len == 0
        assert score.sentence_count == 0

    def test_short_text_below_length_floor_is_rejected(self):
        score = score_content_richness("Flu case reported.")
        assert score.is_content_rich is False

    def test_ttr_window_bounds_ratio_for_long_repetitive_text(self):
        repeated = ("flu case outbreak vaccine severe strain. ") * 200
        score = score_content_richness(repeated)
        assert 0.0 <= score.type_token_ratio <= 1.0

    def test_thresholds_are_configurable(self):
        score = score_content_richness(GENUINE_ARTICLE, min_marker_hits=100)
        assert score.is_content_rich is False
