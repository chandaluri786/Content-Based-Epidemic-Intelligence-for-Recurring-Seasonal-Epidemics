import pytest
from pydantic import ValidationError

from pipeline.extraction.schema import ArticleExtraction


@pytest.mark.unit
class TestArticleExtraction:
    def test_accepts_a_valid_payload(self):
        extraction = ArticleExtraction(
            disease_signal=True,
            relevant=True,
            severity="severe",
            symptoms=["fever", "cough"],
            strain="h3n2",
            location_mentioned="Nairobi",
            confidence=0.85,
        )
        assert extraction.severity == "severe"
        assert extraction.strain == "h3n2"

    def test_rejects_invalid_severity_enum_value(self):
        with pytest.raises(ValidationError):
            ArticleExtraction(
                disease_signal=True,
                relevant=True,
                severity="catastrophic",
                symptoms=[],
                strain="unspecified",
                location_mentioned=None,
                confidence=0.5,
            )

    def test_rejects_invalid_strain_enum_value(self):
        with pytest.raises(ValidationError):
            ArticleExtraction(
                disease_signal=True,
                relevant=True,
                severity="mild",
                symptoms=[],
                strain="h5n1",
                location_mentioned=None,
                confidence=0.5,
            )

    def test_rejects_confidence_above_one(self):
        with pytest.raises(ValidationError):
            ArticleExtraction(
                disease_signal=True,
                relevant=True,
                severity="mild",
                symptoms=[],
                strain="unspecified",
                location_mentioned=None,
                confidence=1.5,
            )

    def test_rejects_confidence_below_zero(self):
        with pytest.raises(ValidationError):
            ArticleExtraction(
                disease_signal=True,
                relevant=True,
                severity="mild",
                symptoms=[],
                strain="unspecified",
                location_mentioned=None,
                confidence=-0.1,
            )

    def test_symptoms_are_lowercased(self):
        extraction = ArticleExtraction(
            disease_signal=True,
            relevant=True,
            severity="mild",
            symptoms=["Fever", "COUGH"],
            strain="unspecified",
            location_mentioned=None,
            confidence=0.5,
        )
        assert extraction.symptoms == ["fever", "cough"]

    def test_symptoms_list_is_truncated_to_ten(self):
        extraction = ArticleExtraction(
            disease_signal=True,
            relevant=True,
            severity="mild",
            symptoms=[f"symptom{i}" for i in range(15)],
            strain="unspecified",
            location_mentioned=None,
            confidence=0.5,
        )
        assert len(extraction.symptoms) == 10

    def test_location_mentioned_defaults_to_none(self):
        extraction = ArticleExtraction(
            disease_signal=False,
            relevant=False,
            severity="none",
            symptoms=[],
            strain="not_mentioned",
            confidence=0.1,
        )
        assert extraction.location_mentioned is None

    def test_json_schema_can_be_generated_for_structured_output(self):
        schema = ArticleExtraction.model_json_schema()
        assert "confidence" in schema["properties"]
        assert "severity" in schema["properties"]
