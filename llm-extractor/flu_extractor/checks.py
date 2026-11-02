"""Automatic checks on a model reply.

Two levels:
  * shape errors   - the reply does not follow the JSON schema, so it cannot be scored;
  * rule violations - the reply is well-formed but breaks a labeling rule.
"""

from datetime import date, timedelta

from flu_extractor.places import PLACE_FIELDS, PlaceChecker

VALID_KINDS = {"cases", "deaths", "hospitalized", "trend"}
VALID_COUNT_TYPES = {"new", "cumulative_region", "cumulative_subset"}
VALID_STATUSES = {"confirmed", "suspected"}
VALID_WORDS = {"rising", "falling", "high", "moderate", "low", "inactive", "present"}
REQUIRED_TOP_LEVEL = ("summary", "reasoning", "useful", "reason", "items")
REQUIRED_ITEM_FIELDS = (
    "kind", "number", "count_type", "status", "strain", "city", "state", "country",
    "start_date", "end_date", "words", "evidence",
)
RECENT_DAYS = 30  # section 4.7 of the prompt
# Wording of rule (d) violations.
PLACE_NOT_FOUND = "was not found as a"
PLACE_UNCHECKED = "could not be checked (place lookup unavailable)"


def _is_iso_date(value) -> bool:
    """True if value is a string like 2018-07-30 that is a real calendar date."""
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def find_shape_errors(parsed: dict) -> list[str]:
    """Check the reply against the schema in the prompt. Empty list = valid."""
    errors = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in parsed:
            errors.append(f"missing top-level key '{key}'")
    if errors:
        return errors  # the checks below need these keys

    if not isinstance(parsed["useful"], bool):
        errors.append("'useful' is not true/false")
    reasoning = parsed["reasoning"]
    if not (isinstance(reasoning, list) and reasoning and all(isinstance(s, str) for s in reasoning)):
        errors.append("'reasoning' must be a non-empty list of strings")
    if not isinstance(parsed["items"], list):
        return errors + ["'items' is not a list"]

    for index, item in enumerate(parsed["items"], start=1):
        label = f"item {index}"
        if not isinstance(item, dict):
            errors.append(f"{label} is not an object")
            continue
        for field in REQUIRED_ITEM_FIELDS:
            if field not in item:
                errors.append(f"{label} missing field '{field}'")
        if item.get("kind") not in VALID_KINDS:
            errors.append(f"{label} has kind {item.get('kind')!r}, not one of {sorted(VALID_KINDS)}")
        for field in ("start_date", "end_date"):
            if item.get(field) is not None and not _is_iso_date(item.get(field)):
                errors.append(f"{label} has an invalid {field} {item.get(field)!r}")
        for field in PLACE_FIELDS:
            if item.get(field) is not None and not isinstance(item.get(field), str):
                errors.append(f"{label} {field} must be text or null, not {item.get(field)!r}")
        number = item.get("number")
        if number is not None and (isinstance(number, bool) or not isinstance(number, int)):
            errors.append(f"{label} number must be a whole number or null, not {number!r}")
        evidence = item.get("evidence")
        if not (isinstance(evidence, list) and evidence and all(isinstance(e, str) for e in evidence)):
            errors.append(f"{label} evidence must be a non-empty list of strings")
    return errors


def _collapse_whitespace(text: str) -> str:
    """Make 'a  b\\nc' and 'a b c' equal, so line breaks do not cause false alarms."""
    return " ".join(text.split())


# Reasons a quoted passage fails rule (a). The report counts failures by these phrases.
QUOTE_EMPTY = "is empty"
QUOTE_TYPOGRAPHY_ONLY = "differs from the article only in quote or dash characters"
QUOTE_NOT_FOUND = "is not found in the article"

# Fancy characters that a model tends to turn into plain ones when it copies text.
_TYPOGRAPHY = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "..."})


def find_quote_problem(quote: str, article_text: str) -> str | None:
    """Rule (a): a quote must be an exact, unbroken piece of the article.

    Returns None when it is, otherwise one of the QUOTE_* reasons. Only line breaks and
    runs of spaces are ignored. Text joined from separate places, reworded, shortened with
    "..." or invented is not found, because the article has no such continuous passage.
    """
    squashed_quote = _collapse_whitespace(quote)
    squashed_article = _collapse_whitespace(article_text)
    if not squashed_quote:
        return QUOTE_EMPTY  # an empty string is "inside" every article, so it needs its own test
    if squashed_quote in squashed_article:
        return None
    if squashed_quote.translate(_TYPOGRAPHY) in squashed_article.translate(_TYPOGRAPHY):
        return QUOTE_TYPOGRAPHY_ONLY  # the words are the article's, but the copy is not exact
    return QUOTE_NOT_FOUND


def _same_except_evidence(first: dict, second: dict) -> bool:
    """True when two items agree on every field but evidence (G3 in the prompt)."""
    return all(first[name] == second[name] for name in REQUIRED_ITEM_FIELDS if name != "evidence")


def _evidence_in_article_order(evidence: list[str], article_text: str) -> bool:
    """Parts after the first must follow article order (10.1). The first part may come from anywhere."""
    squashed_article = _collapse_whitespace(article_text)
    positions = [squashed_article.find(_collapse_whitespace(part)) for part in evidence[1:]]
    found = [position for position in positions if position >= 0]
    return found == sorted(found)


def _kind_field_problems(item: dict) -> list[str]:
    """Rules (b) and (c): which fields a trend and a count must and must not fill (2.2)."""
    problems = []
    if item["kind"] == "trend":
        if item["words"] not in VALID_WORDS:
            problems.append(f"(b) trend word {item['words']!r} is not one of the seven words")
        if item["number"] is not None or item["count_type"] is not None or item["status"] is not None:
            problems.append("(b) a trend must have null number, count_type and status")
        return problems
    if item["words"] is not None:
        problems.append("(c) 'words' must be null on a count")
    if item["number"] is None:
        problems.append("(c) a count needs a number")
    if item["count_type"] not in VALID_COUNT_TYPES:
        problems.append(f"(c) count_type {item['count_type']!r} is not valid")
    if item["status"] not in VALID_STATUSES:
        problems.append(f"(c) status {item['status']!r} is not valid")
    return problems


def _date_problems(item: dict, scan_date: str) -> list[str]:
    """Rules (e), (h) and (i): the end date exists, is recent, and the range is in order."""
    problems = []
    end_date = item["end_date"]
    if not end_date:
        return ["(h) the end date is missing (G2)"]
    if item["start_date"] and item["start_date"] > end_date:  # ISO dates compare correctly as text
        problems.append("(e) start_date is after end_date")
    scanned = date.fromisoformat(scan_date)
    if end_date > scan_date:
        problems.append(f"(i) end date {end_date} is after the scan date {scan_date}")
    elif date.fromisoformat(end_date) < scanned - timedelta(days=RECENT_DAYS):
        problems.append(f"(i) end date {end_date} is more than {RECENT_DAYS} days before the scan date")
    return problems


def find_rule_violations(parsed: dict, article_text: str, scan_date: str,
                         place_checker: PlaceChecker) -> list[str]:
    """Check labeling rules (a)-(j). Call only on a reply with no shape errors.

    `place_checker` tells whether a city, state or country exists, for rule (d).
    """
    violations = []
    items = parsed["items"]

    # (g) useful is true exactly when there are items (Section 11)
    if parsed["useful"] != bool(items):
        violations.append("(g) useful does not agree with the items list")

    for index, item in enumerate(items, start=1):
        label = f"item {index} ({item['kind']})"

        # (a) every evidence part is copied from the article, word for word
        for part in item["evidence"]:
            problem = find_quote_problem(part, article_text)
            if problem:
                violations.append(f"(a) {label}: evidence {problem}: {part[:60]!r}")
        # (j) evidence after the first part is in article order
        if not _evidence_in_article_order(item["evidence"], article_text):
            violations.append(f"(j) {label}: evidence after the first part is out of article order")

        for problem in _kind_field_problems(item) + _date_problems(item, scan_date):
            violations.append(f"{problem[:3]} {label}: {problem[4:]}")

        # (h) a country is required (G1)
        if not item["country"]:
            violations.append(f"(h) {label}: the country is missing (G1)")

        # (d) each place field is null or a real city / state / country, as the field requires
        for field in PLACE_FIELDS:
            value = item[field]
            if value is None:
                continue
            is_known = place_checker.is_known(field, value)
            if is_known is False:
                violations.append(f"(d) {label}: {field} {value!r} {PLACE_NOT_FOUND} {field}")
            elif is_known is None:
                violations.append(f"(d) {label}: {field} {value!r} {PLACE_UNCHECKED}")

    # (f) no two items identical except evidence (G3). Overlapping counts are allowed (G5).
    for i, first in enumerate(items):
        for j in range(i + 1, len(items)):
            if _same_except_evidence(first, items[j]):
                violations.append(f"(f) items {i + 1} and {j + 1} are identical except evidence (G3)")
    return violations
