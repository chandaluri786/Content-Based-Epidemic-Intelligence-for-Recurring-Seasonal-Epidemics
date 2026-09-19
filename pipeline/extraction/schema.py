"""LLM extraction output contract (Step 3).

Fields adapted from Health Sentinel (Pant et al. 2025)'s general
disease/severity/symptoms/location/confidence schema, narrowed to flu-specific
enums (strain, severity) rather than their generic multi-disease schema.
Identifiers (article_url, model version, timestamp) are deliberately excluded
here and filled by calling code -- never asked of the LLM, which shouldn't be
trusted to reproduce them faithfully.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from pipeline.config import COUNTRIES

MAX_SYMPTOMS = 10

Severity = Literal["none", "mild", "moderate", "severe", "fatal", "unknown"]
Strain = Literal["h1n1", "h3n2", "influenza_b", "unspecified", "not_mentioned"]
# Kept as an explicit tuple (verified against pipeline.config.COUNTRIES by
# tests/unit/extraction/test_schema.py) rather than built dynamically --
# pydantic/typing.Literal needs a static set of values to validate against.
CohortCountry = Literal["USA", "GBR", "JPN", "AUS", "BRA", "IND", "KEN", "IDN"]
assert set(CohortCountry.__args__) == set(COUNTRIES.keys())


class ArticleExtraction(BaseModel):
    disease_signal: bool = Field(
        description="Does the article report an actual disease-activity event, "
        "as opposed to general commentary or an explainer?"
    )
    relevant: bool = Field(
        description="Is this a genuine flu case/severity/outbreak signal, as opposed "
        "to an explainer article, a metaphorical use of 'flu', or a mistagged story?"
    )
    severity: Severity
    symptoms: list[str] = Field(default_factory=list)
    strain: Strain
    location_mentioned: str | None = Field(
        default=None, description="Location as mentioned in the text, not geocoded."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Self-rated extraction confidence.")
    # Flattened to a single Literal (not CohortCountry | Literal["other"] | None)
    # -- Groq's structured-output mode rejects a 3-way anyOf (enum + const +
    # null); confirmed empirically via BadRequestError("Failed to validate
    # JSON") on every real call. A flat enum + null (2-way anyOf, the same
    # shape as location_mentioned's str | None) is what actually works.
    primary_country: Literal[CohortCountry, "other"] | None = Field(
        default=None,
        description="The country that is the clear primary subject of this article "
        "(where the reported case/event is occurring) -- not any country merely "
        "mentioned in passing. Use 'other' for a confident primary-subject country "
        "outside the study cohort. Use null only when genuinely ambiguous or global "
        "in scope, with no single confident primary subject.",
    )

    @field_validator("symptoms")
    @classmethod
    def _normalize_symptoms(cls, value: list[str]) -> list[str]:
        return [s.lower() for s in value[:MAX_SYMPTOMS]]
