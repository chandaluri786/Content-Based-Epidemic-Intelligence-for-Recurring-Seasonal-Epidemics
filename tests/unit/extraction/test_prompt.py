import pytest

from pipeline.config import MAX_ARTICLE_CHARS
from pipeline.extraction.prompt import FEW_SHOT_EXAMPLES, build_extraction_messages


@pytest.mark.unit
class TestFewShotExamples:
    def test_has_exactly_six_examples(self):
        assert len(FEW_SHOT_EXAMPLES) == 6

    def test_covers_the_required_example_kinds(self):
        kinds = {ex["kind"] for ex in FEW_SHOT_EXAMPLES}
        assert kinds == {
            "clear_positive",
            "explainer_negative",
            "ambiguous_low_confidence",
            "mistagged_negative",
            "animal_flu_negative",
            "incidental_mention_negative",
        }

    def test_animal_flu_example_is_marked_not_relevant(self):
        example = next(ex for ex in FEW_SHOT_EXAMPLES if ex["kind"] == "animal_flu_negative")
        assert example["output"]["relevant"] is False

    def test_mistagged_example_has_a_primary_country(self):
        example = next(ex for ex in FEW_SHOT_EXAMPLES if ex["kind"] == "mistagged_negative")
        assert example["output"]["primary_country"] == "BRA"

    def test_incidental_mention_example_is_still_relevant_but_names_the_true_subject(self):
        # Genuine flu signal (Japan), with the target country (India) only
        # mentioned in passing -- primary_country must diverge from the
        # country the article would otherwise be filed under.
        example = next(ex for ex in FEW_SHOT_EXAMPLES if ex["kind"] == "incidental_mention_negative")
        assert example["output"]["relevant"] is True
        assert example["output"]["primary_country"] == "JPN"


@pytest.mark.unit
class TestBuildExtractionMessages:
    def test_system_prompt_instructs_primary_country_judgment(self):
        messages = build_extraction_messages("text", country_hint="IND")
        assert "primary_country" in messages[0]["content"]

    def test_system_prompt_warns_the_given_tag_may_be_wrong(self):
        # Confirmed empirically: presenting the country tag as a bare stated
        # fact anchors the model into agreeing with it even against clear
        # contrary evidence in the article text (e.g. it echoed back Brazil
        # for an article headlined about Australia's Northern Territory).
        # The system prompt must say the tag can be wrong, not just ask for
        # a primary_country field.
        messages = build_extraction_messages("text", country_hint="IND")
        system_content = messages[0]["content"].lower()
        assert "sometimes wrong" in system_content or "may be wrong" in system_content

    def test_user_message_frames_the_country_as_a_tag_to_verify_not_a_fact(self):
        messages = build_extraction_messages("text", country_hint="BRA")
        user_content = messages[1]["content"]
        assert "Country: BRA" not in user_content
        assert "BRA" in user_content

    def test_returns_system_and_user_messages(self):
        messages = build_extraction_messages("Some article text.", country_hint="Kenya")
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user"]

    def test_system_message_contains_all_examples(self):
        messages = build_extraction_messages("text", country_hint="USA")
        system_content = messages[0]["content"]
        for example in FEW_SHOT_EXAMPLES:
            assert example["article_text"] in system_content

    def test_user_message_contains_the_target_article_text_and_country_hint(self):
        messages = build_extraction_messages(
            "A flu outbreak has been reported.", country_hint="Kenya"
        )
        user_content = messages[1]["content"]
        assert "A flu outbreak has been reported." in user_content
        assert "Kenya" in user_content

    def test_article_text_is_truncated_to_max_article_chars(self):
        long_text = "x" * (MAX_ARTICLE_CHARS + 500)
        messages = build_extraction_messages(long_text, country_hint="USA")
        user_content = messages[1]["content"]
        assert len(user_content) < len(long_text) + 200
        assert "x" * MAX_ARTICLE_CHARS in user_content
        assert "x" * (MAX_ARTICLE_CHARS + 1) not in user_content
