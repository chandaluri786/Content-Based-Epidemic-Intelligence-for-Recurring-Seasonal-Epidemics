"""Deterministic evidence checks on model items, kept apart from the event and field scores.

They show whether an item can be traced to the article. They do not show that the quote supports
the item: a sentence can exist in the article and still not say what the item claims.
"""

import re
from dataclasses import dataclass

from flu_extractor.checks import QUOTE_NOT_FOUND, QUOTE_TYPOGRAPHY_ONLY, find_quote_problem

_SUBTYPE = re.compile(r"^h\d+n\d+v?$")


@dataclass
class ItemEvidence:
    has_evidence: bool          # at least one non-empty quote
    quotes: int
    verbatim: int               # quotes found exactly (spacing ignored)
    typography_only: int        # found only after treating curly and straight quotes, dashes alike
    not_found: int
    number_found: bool | None   # the count's number appears in its evidence or the article; None = no number
    city_found: bool | None     # the city name appears in the article; None = no city
    # A subtype code (H1N1, H5N1...) appears in the article; None = not a code. Not appearing is not
    # always an error: "swine flu" gives H1N1 by rule 8.1.
    strain_found: bool | None

    @property
    def verifiable(self) -> bool:
        """At least one quote is in the article exactly."""
        return self.verbatim > 0


_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
          "sixteen seventeen eighteen nineteen twenty").split()


def _number_forms(number: int) -> set[str]:
    """Digits with and without thousands separators, and the word for 0-20 ("five")."""
    forms = {str(number), f"{number:,}", f"{number:,}".replace(",", " ")}
    if 0 <= number < len(_WORDS):
        forms.add(_WORDS[number])
    return forms


def _contains(haystack: str, needle: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(needle)}(?![\w])", haystack, flags=re.IGNORECASE) is not None


def check_item(item: dict, article_text: str) -> ItemEvidence:
    quotes = [q for q in item.get("evidence") or [] if isinstance(q, str) and q.strip()]
    problems = [find_quote_problem(q, article_text) for q in quotes]
    text = " ".join(article_text.split())
    number = item.get("number")
    number_found = None
    if isinstance(number, int) and not isinstance(number, bool):
        number_found = any(_contains(text, form) for form in _number_forms(number))
    city = item.get("city")
    strain = item.get("strain")
    return ItemEvidence(
        has_evidence=bool(quotes),
        quotes=len(quotes),
        verbatim=sum(p is None for p in problems),
        typography_only=sum(p == QUOTE_TYPOGRAPHY_ONLY for p in problems),
        not_found=sum(p == QUOTE_NOT_FOUND for p in problems),
        number_found=number_found,
        city_found=_contains(text, city) if isinstance(city, str) and city else None,
        strain_found=(_contains(text, strain) if isinstance(strain, str) and _SUBTYPE.match(strain.lower())
                      else None),
    )
