"""Automatic checks on a model reply (section 5, step 3 of the prompt).

Two levels:
  * shape errors   - the reply does not follow the JSON schema, so it cannot be scored;
  * rule violations - the reply is well-formed but breaks a labeling rule.
"""

from datetime import date

from flu_extractor.places import PLACE_FIELDS, PlaceChecker

VALID_KINDS = {"cases", "deaths", "hospitalized", "trend"}
REQUIRED_TOP_LEVEL = ("useful", "borderline", "reason", "items", "findings")
REQUIRED_ITEM_FIELDS = (
    "kind", "strain", "number", "status", "total_or_new", "city", "state",
    "country", "start_date", "end_date", "words", "evidence",
)
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
    """Check the reply against the schema in section 4 of the prompt. Empty list = valid."""
    errors = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in parsed:
            errors.append(f"missing top-level key '{key}'")
    if errors:
        return errors  # the checks below need these keys

    if not isinstance(parsed["useful"], bool):
        errors.append("'useful' is not true/false")
    if not isinstance(parsed["items"], list):
        return errors + ["'items' is not a list"]
    findings = parsed["findings"]
    if not (isinstance(findings, list) and all(
        isinstance(f, dict) and isinstance(f.get("country"), str) and isinstance(f.get("finding"), str)
        for f in findings
    )):
        errors.append("'findings' must be a list of objects with string 'country' and 'finding'")

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


def _ranges_overlap(first: dict, second: dict) -> bool:
    """True if the date ranges of two items overlap. Items without an end date never overlap."""
    if not (first.get("end_date") and second.get("end_date")):
        return False
    first_start = first.get("start_date") or first["end_date"]
    second_start = second.get("start_date") or second["end_date"]
    return first_start <= second["end_date"] and second_start <= first["end_date"]


def find_rule_violations(parsed: dict, article_text: str, place_checker: PlaceChecker) -> list[str]:
    """Check labeling rules (a)-(g). Call only on a reply with no shape errors.

    `place_checker` tells whether a city, state or country exists, for rule (d).
    """
    violations = []
    items = parsed["items"]

    # (g) a not-useful article has no items
    if not parsed["useful"] and items:
        violations.append("(g) useful is false but items are present")

    # (a) every finding sentence is copied from the article
    for index, finding in enumerate(parsed["findings"], start=1):
        problem = find_quote_problem(finding["finding"], article_text)
        if problem:
            violations.append(f"(a) finding {index}: sentence {problem}: {finding['finding'][:60]!r}")

    for index, item in enumerate(items, start=1):
        label = f"item {index} ({item['kind']})"

        # (a) every evidence part is copied from the article, word for word
        for part in item["evidence"]:
            problem = find_quote_problem(part, article_text)
            if problem:
                violations.append(f"(a) {label}: evidence {problem}: {part[:60]!r}")

        # (b) 'words' is only for trend items
        if item["kind"] != "trend" and item["words"] is not None:
            violations.append(f"(b) {label}: 'words' must be null unless kind is trend")

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

        # (e) the range does not run backwards (ISO dates compare correctly as text)
        if item["start_date"] and item["end_date"] and item["start_date"] > item["end_date"]:
            violations.append(f"(e) {label}: start_date is after end_date")

    # (f) no two items of the same kind, strain and place with overlapping dates
    for i, first in enumerate(items):
        for j in range(i + 1, len(items)):
            second = items[j]
            same_subject = all(
                first[f] == second[f] for f in ("kind", "strain", "city", "state", "country")
            )
            if same_subject and _ranges_overlap(first, second):
                violations.append(f"(f) items {i + 1} and {j + 1} are the same kind and place with overlapping dates")
    return violations
