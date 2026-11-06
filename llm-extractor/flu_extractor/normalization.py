"""Normalize item values before comparison, and say which fields apply to which kind of item.

Only harmless differences are removed: case, repeated spaces, Unicode quote and dash variants.
Meaningful differences (new vs cumulative, another number, another period) are kept. Place names
are not handled here: before items are compared, evaluation.py turns every city, state and country
into its agreed form, its English name in OpenStreetMap (prompt 5.1, places.agreed_names), so
"Bangalore" and "Bengaluru", or "USA" and "United States", are already the same value. The same rules
apply to gold and model items. A change here can change every score, so NORMALIZATION_VERSION is
written into each evaluation summary.
"""

import unicodedata

NORMALIZATION_VERSION = "norm_v3"

COUNT_KINDS = ("cases", "hospitalized", "deaths")
ITEM_KINDS = (*COUNT_KINDS, "trend")

# The fields each kind fills (prompt 2.2). Evidence is never scored; it gets its own checks.
COUNT_FIELDS = ("kind", "number", "count_type", "status", "strain", "city", "state", "country",
                "start_date", "end_date")
TREND_FIELDS = ("kind", "words", "strain", "city", "state", "country", "start_date", "end_date")
ALL_FIELDS = ("kind", "number", "count_type", "status", "words", "strain", "city", "state", "country",
              "start_date", "end_date")


class _Missing:
    """A field absent from the item, which is not the same as an explicit null."""

    def __repr__(self) -> str:
        return "(missing)"


MISSING = _Missing()

_PUNCTUATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "..."})


def applicable_fields(kind: str | None) -> tuple[str, ...]:
    """The fields scored for an item of this kind. Unknown kinds are scored like counts."""
    return TREND_FIELDS if kind == "trend" else COUNT_FIELDS


def normalize_value(value):
    """The comparable form of one field value. Numbers stay numbers; None stays None."""
    if value is MISSING or value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else value
    text = unicodedata.normalize("NFKC", str(value)).translate(_PUNCTUATION)
    return " ".join(text.split()).lower()


def normalize_item(item: dict) -> dict:
    """Every scored field in comparable form. Fields absent from the item become MISSING."""
    return {name: normalize_value(item[name]) if name in item else MISSING for name in ALL_FIELDS}


def show(value) -> str:
    """A value as it is written in reports: null as (null), an absent field as (missing)."""
    if value is MISSING:
        return "(missing)"
    return "(null)" if value is None else str(value)
