"""Checks on a reply (the model's, a gold record's or a few-shot example's) against the prompt
(v5.2; v5.1 has the same reply format and fixed values).

Three layers:

  1. find_format_errors(reply): the reply follows the prompt's format, with every value it fixes.
     A reply with a format error cannot be scored. During a run it is sent back to the model with a
     note naming the problem (extractor.py).
  2. find_evidence_errors(reply, article_text): every evidence quote is copied exactly from the
     article (10.1). During a run a reply with a bad quote is also sent back; if the last reply still
     has one, it is scored and the quote is reported as rule (a).
  3. find_rule_violations(reply, article_text, scan_date, place_checker): rules that need the article,
     the scan date or the geocoder: recency (4.7), evidence order (10.1), the reasoning steps ("How to
     work"), places that are real and written in their agreed form (5.1), and, from v5.2, overlapping
     counts within one place (G4) and contradicting trend words (G5). They are reported, never used to
     reject a reply.
"""

import re
from datetime import date, timedelta

from flu_extractor.places import PLACE_FIELDS, PlaceChecker

# --- The values the prompt fixes (2.2, the same in v5.1 and v5.2) ----------------

REPLY_KEYS = ("summary", "reasoning", "useful", "reason", "items")                    # "Your reply"
ITEM_FIELDS = ("kind", "number", "count_type", "status", "strain", "city", "state", "country",
               "start_date", "end_date", "words", "evidence")                         # 2.2
COUNT_KINDS = ("cases", "hospitalized", "deaths")                                     # 2.3
KINDS = (*COUNT_KINDS, "trend")
COUNT_TYPES = ("new", "cumulative_region", "cumulative_subset")                       # Section 7
STATUSES = ("confirmed", "suspected")                                                 # Section 6
TREND_WORDS = ("rising", "falling", "high", "moderate", "low", "inactive", "present")  # 9.2
# 8.1: a subtype code as written in upper case (H1N1, H3N2v, H5), or one of three names.
STRAIN_NAMES = ("influenza A", "influenza B", "avian influenza")
STRAIN_CODE = re.compile(r"H\d{1,2}(N\d{1,2})?v?")
RECENT_DAYS = 30                                                                      # 4.7

# Wording of rule (d) problems, counted in the report.
PLACE_NOT_FOUND = "was not found"
PLACE_UNCHECKED = "could not be checked (place lookup unavailable)"


def is_iso_date(value) -> bool:
    """True if value is a string like 2018-07-30 that is a real calendar date."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_valid_strain(value) -> bool:
    """8.1: null, a subtype code in upper case, or influenza A / influenza B / avian influenza."""
    return value is None or value in STRAIN_NAMES or (isinstance(value, str) and bool(STRAIN_CODE.fullmatch(value)))


# --- Layer 1: format ---------------------------------------------------------

def _item_format_errors(item, label: str) -> list[str]:
    if not isinstance(item, dict):
        return [f"{label} is not an object"]
    missing = [name for name in ITEM_FIELDS if name not in item]
    if missing:
        return [f"{label} is missing the field(s) {', '.join(missing)} (every item has all 12 fields)"]
    errors = []
    extra = [name for name in item if name not in ITEM_FIELDS]
    if extra:
        errors.append(f"{label} has field(s) the prompt does not define: {', '.join(extra)}")
    kind = item["kind"]
    if kind not in KINDS:
        return errors + [f"{label} kind {kind!r} is not one of {', '.join(KINDS)}"]
    if kind == "trend":                                                  # 2.2, 9.2
        if item["words"] not in TREND_WORDS:
            errors.append(f"{label} is a trend, so words must be one of {', '.join(TREND_WORDS)}, "
                          f"not {item['words']!r}")
        for name in ("number", "count_type", "status"):
            if item[name] is not None:
                errors.append(f"{label} is a trend, so {name} must be null")
    else:                                                                # 2.2, Sections 3, 6, 7
        number = item["number"]
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            errors.append(f"{label} is a count, so number must be a whole number of at least 1, not {number!r}")
        if item["count_type"] not in COUNT_TYPES:
            errors.append(f"{label} count_type must be one of {', '.join(COUNT_TYPES)}, not {item['count_type']!r}")
        if item["status"] not in STATUSES:
            errors.append(f"{label} status must be one of {', '.join(STATUSES)}, not {item['status']!r}")
        if item["words"] is not None:
            errors.append(f"{label} is a count, so words must be null")
    if not is_valid_strain(item["strain"]):                              # 8.1
        errors.append(f"{label} strain {item['strain']!r} is not a subtype code in upper case (H1N1, H3N2v), "
                      f"{', '.join(STRAIN_NAMES)}, or null")
    for name in PLACE_FIELDS:                                            # 5.1
        value = item[name]
        if value is not None and not (isinstance(value, str) and value.strip()):
            errors.append(f"{label} {name} must be a place name or null, not {value!r}")
    if not item["country"]:
        errors.append(f"{label} has no country (G1)")
    if item["city"] and not item["state"]:
        errors.append(f"{label} has a city but no state (5.1: the chain must be complete)")
    for name in ("start_date", "end_date"):                              # 4.2
        if item[name] is not None and not is_iso_date(item[name]):
            errors.append(f"{label} {name} {item[name]!r} is not a date written YYYY-MM-DD")
    if not item["end_date"]:
        errors.append(f"{label} has no end_date (G2)")
    elif is_iso_date(item["end_date"]) and is_iso_date(item["start_date"]) and item["start_date"] > item["end_date"]:
        errors.append(f"{label} start_date is after end_date")
    evidence = item["evidence"]                                          # 10.2
    if not (isinstance(evidence, list) and evidence and all(isinstance(q, str) and q.strip() for q in evidence)):
        errors.append(f"{label} evidence must be a non-empty list of non-empty quotes")
    return errors


def find_format_errors(reply) -> list[str]:
    """Layer 1: everything the reply format fixes. An empty list means the format is valid."""
    if not isinstance(reply, dict):
        return ["the reply is not a JSON object"]
    missing = [key for key in REPLY_KEYS if key not in reply]
    if missing:
        return [f"missing top-level key(s) {', '.join(missing)}"]
    errors = []
    if not (isinstance(reply["summary"], str) and reply["summary"].strip()):
        errors.append("summary must be a non-empty line of text")
    reasoning = reply["reasoning"]
    if not (isinstance(reasoning, list) and reasoning and all(isinstance(s, str) for s in reasoning)):
        errors.append("reasoning must be a non-empty list of steps (text)")
    if not isinstance(reply["useful"], bool):
        errors.append("useful must be true or false")
    if not (isinstance(reply["reason"], str) and reply["reason"].strip()):
        errors.append("reason must be a non-empty sentence")
    items = reply["items"]
    if not isinstance(items, list):
        return errors + ["items must be a list"]
    for index, item in enumerate(items, start=1):
        errors += _item_format_errors(item, f"item {index}")
    if isinstance(reply["useful"], bool) and reply["useful"] != bool(items):  # Section 11
        errors.append("useful must be true exactly when items is not empty (Section 11)")
    return errors



# --- Layer 2: evidence copied from the article ----------------------------------

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

    Returns None when it is, otherwise one of the QUOTE_* reasons. Only line breaks and runs of
    spaces are ignored. Text joined from separate places, reworded, shortened with "..." or
    invented is not found, because the article has no such continuous passage.
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


def find_evidence_errors(reply: dict, article_text: str) -> list[str]:
    """Layer 2 (rule a): every evidence quote of every item is an exact piece of the article.

    Call on a reply with a valid format. Each problem names the item and the start of the quote.
    """
    errors = []
    for index, item in enumerate(reply["items"], start=1):
        for quote in item["evidence"]:
            problem = find_quote_problem(quote, article_text)
            if problem:
                errors.append(f"(a) item {index} ({item['kind']}): evidence {problem}: {quote[:80]!r}")
    return errors


# --- Layer 3: rule checks -----------------------------------------------------------

def _evidence_in_article_order(evidence: list[str], article_text: str) -> bool:
    """Parts after the first must follow article order (10.1). The first part may come from anywhere."""
    squashed_article = _collapse_whitespace(article_text)
    positions = [squashed_article.find(_collapse_whitespace(part)) for part in evidence[1:]]
    found = [position for position in positions if position >= 0]
    return found == sorted(found)


def _recency_problems(item: dict, scan_date: str) -> list[str]:
    """Rule (i), 4.7: the end date is on or before the scan date and within the 30 days before it."""
    end_date = item["end_date"]
    if end_date > scan_date:
        return [f"end date {end_date} is after the scan date {scan_date}"]
    if date.fromisoformat(end_date) < date.fromisoformat(scan_date) - timedelta(days=RECENT_DAYS):
        return [f"end date {end_date} is more than {RECENT_DAYS} days before the scan date"]
    return []


def find_place_problems(item: dict, place_checker: PlaceChecker) -> list[str]:
    """Rule (d), 5.1: the place is real as a whole chain, and written in its agreed form.

    Real: the geocoder is asked for the country, then state + country, then city + state + country,
    so a state in the wrong country or a city in the wrong state is not found. Agreed form: every
    level that is found must be written as its English name in OpenStreetMap (5.1); a level written
    another way ("USA", "Bangalore", "NSW") is reported with the agreed form. Scoring already uses
    the agreed form, so this reports how well the reply follows 5.1, not a scoring difference.
    """
    problems = []
    agreed = place_checker.agreed_names(item)
    for level in ("country", "state", "city"):
        written = item[level]
        if not written:
            continue
        chain = ", ".join(v for v in (item["city"] if level == "city" else None,
                                      item["state"] if level != "country" else None, item["country"]) if v)
        found = agreed["resolved"][level]
        if found is None:
            problems.append(f"{level} {chain!r} {PLACE_UNCHECKED}")
            break
        if found is False:
            problems.append(f"{level} {chain!r} {PLACE_NOT_FOUND} as a {level} in that chain")
            break  # the levels below cannot be found either
        if " ".join(written.split()) != agreed[level]:
            problems.append(f"{level} {written!r} is not in its agreed form (5.1); write {agreed[level]!r}")
    return problems


def _overlap_problems(items: list[dict]) -> list[str]:
    """G4 and G5 of prompt v5.2, where a script can decide them from the fields alone.

    G4: two counts of the same kind, place fields, period, strain and status count the same people
        (a count and its parts, or one count recorded twice). Counts that differ in any of these
        are allowed (a total and a shorter period, influenza A and B, confirmed among suspected).
    G5: two trend items with the same place fields, strain and period have different words.
    """
    problems, seen_counts, seen_trends = [], {}, {}
    for index, item in enumerate(items, start=1):
        where = tuple(item[f] for f in ("city", "state", "country", "start_date", "end_date", "strain"))
        if item["kind"] == "trend":
            earlier = seen_trends.setdefault(where, (index, item["words"]))
            if earlier[0] != index and earlier[1] != item["words"]:
                problems.append(f"(G5) items {earlier[0]} and {index}: trend words '{earlier[1]}' and "
                                f"'{item['words']}' for the same place, strain and period")
        else:
            key = (item["kind"], item["status"], *where)
            earlier = seen_counts.setdefault(key, index)
            if earlier != index:
                problems.append(f"(G4) items {earlier} and {index}: two {item['kind']} counts with the same "
                                f"place, period, strain and status overlap")
    return problems


def find_rule_violations(reply: dict, article_text: str, scan_date: str,
                         place_checker: PlaceChecker) -> list[str]:
    """Layers 2 and 3 for a reply with a valid format: rules (a), (d), (i), (j), (k), G4 and G5.

    (a) evidence copied exactly from the article; (d) places real and in their agreed form; (i) end date
    recent; (j) evidence after the first quote in article order; (k) reasoning starts with
    Step 0 and Step 1 cites Rule 1; G4 and G5 as in _overlap_problems.
    """
    violations = list(find_evidence_errors(reply, article_text))
    steps = reply["reasoning"]
    if not steps[0].startswith("Step 0"):
        violations.append("(k) reasoning does not begin with Step 0 (How to work)")
    elif len(steps) < 2 or not steps[1].startswith("Step 1 (Rule 1)"):
        violations.append("(k) Step 1 does not cite Rule 1 (How to work)")
    for index, item in enumerate(reply["items"], start=1):
        label = f"item {index} ({item['kind']})"
        if not _evidence_in_article_order(item["evidence"], article_text):
            violations.append(f"(j) {label}: evidence after the first quote is out of article order")
        violations += [f"(i) {label}: {p}" for p in _recency_problems(item, scan_date)]
        violations += [f"(d) {label}: {p}" for p in find_place_problems(item, place_checker)]
    # v5.2 G4: two counts that would count the same people (same kind, place, period, strain and
    # status) are never both recorded, so identical counts are reported. duplicates.py also lists them.
    violations += _overlap_problems(reply["items"])
    return violations


def record_is_invalid(record: dict) -> bool:
    """A logged reply that was cut off, unparseable or malformed after all its retries."""
    if record.get("parse_error") or record.get("invalid"):
        return True
    return bool(record.get("parsed")) and bool(find_format_errors(record["parsed"]))  # logs written before `invalid`
