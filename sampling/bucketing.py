"""Put one article into one bucket using the word patterns in patterns.py.

Bucket names: P_ = likely useful, N_ = likely not useful, Z_ = human case of bird/swine flu,
X_ = junk (spam, stub, index page). The checks run in order and the first match wins.
A bucket only decides which articles people read; it is never the label.
"""
import re

from patterns import (
    ADVICE, ANIMAL, AWARE, BUSINESS, COMPARE, COUNT_A, COUNT_B, COUNT_C, CUR, DATE_HEAD, EVENT_C, FLU, GENERIC, HIST, HUMAN,
    HYPO, IDIOM, INDIVIDUAL, NEG_EVID, NONFLU_EMERG, OLDYEAR, OTHER_DIS, PHARMA, POLICY, RATE, RESEARCH,
    RESPONSE, SENT, SICK_NOW, SPAM, SPORT, STATUS, TREND_NEAR, ZOON_HUM, ZOON_NEG, ZOON_SUB,
)

# ---- thresholds -------------------------------------------------------------------------------
MIN_CHARS = 300           # shorter text is a stub or error page
MAX_DIGIT_RATIO = 0.05    # more digits than this means an index page or garbled text
MAX_DATED_HEADLINES = 6   # this many "Jan 5, 2016" headlines means an index page
ANIMAL_RATIO = 0.5        # share of animal terms that makes the article "animal flu"
IDIOM_SHARE = 0.5         # share of flu sentences that are stomach flu, dog flu, etc.
RESEARCH_MAX = 0.5        # count sentences in research-heavy articles need a "now" word
HISTORY_MIN = 0.4
RESEARCH_MIN = 0.4
BUSINESS_MIN = 0.3
POLICY_MIN = 0.4
AWARENESS_MIN = 0.3

# Words showing a bird-flu article is about animals (used for the animal share).
ANIMAL_TERMS = re.compile(
    r"\b(?:bird flu|avian (?:flu|influenza)|h5n1|h5n8|h7n9|h5n6|h5n2|poultry|chickens?|ducks?|culled|culling|flocks?)\b",
    re.I,
)
YEAR = re.compile(r"\b(19\d\d|20[01]\d)\b")
DECADE = re.compile(r"\b(?:19|20)\d0s\b")


def is_past(s: str) -> bool:
    """Sentence is about the past (last year, 1918...) and not just comparing with it."""
    return bool(HIST.search(s)) and not COMPARE.search(s)


def junk_bucket(text: str):
    """Return (bucket, reason) if the text is spam, too short or an index page, otherwise None."""
    if SPAM.search(text):
        return "X_spam_stub", "spam, blocked page, paywall or site notice"
    if len(text) < MIN_CHARS:
        return "X_too_short", f"under {MIN_CHARS} characters"
    digit_ratio = sum(c.isdigit() for c in text) / len(text)
    if digit_ratio > MAX_DIGIT_RATIO or len(DATE_HEAD.findall(text)) >= MAX_DATED_HEADLINES:
        return "X_listing_garbled", "many digits or many dated headlines (index page)"
    return None


def is_trend(s: str, animal_only: bool) -> bool:
    """Sentence about how flu is changing now (rising, widespread, low...), not advice or history."""
    if animal_only or not FLU.search(s):
        return False
    if BUSINESS.search(s) or SPORT.search(s) or is_past(s):
        return False
    if (OLDYEAR.search(s) and not CUR.search(s)) or NONFLU_EMERG.search(s) or NEG_EVID.search(s):
        return False
    wording = TREND_NEAR.search(s) and not (AWARE.search(s) or GENERIC.search(s) or HYPO.search(s) or PHARMA.search(s))
    return bool(wording or (STATUS.search(s) and not HYPO.search(s)))


def count_sentences(text: str, scan_year: int) -> dict:
    """Walk through the sentences that mention flu (or sit next to one) and count the evidence."""
    sentences = [s for s in SENT.split(text) if s.strip()]
    found = dict(numbered=0, event=0, history=0, anchored=0, trend=0, response=0, bird_flu_human=0)
    for i, s in enumerate(sentences):
        if not any(0 <= j < len(sentences) and FLU.search(sentences[j]) for j in (i - 1, i, i + 1)):
            continue
        animal_only = bool(ANIMAL.search(s)) and not HUMAN.search(s)
        if ZOON_SUB.search(s) and ZOON_HUM.search(s) and not ZOON_NEG.search(s):
            found["bird_flu_human"] += 1
        # Skip animal-only sentences, other diseases, and research results with no "now" word.
        if animal_only or (OTHER_DIS.search(s) and not FLU.search(s)) or (RESEARCH.search(s) and not CUR.search(s)):
            continue

        has_number = bool(COUNT_A.search(s) or COUNT_B.search(s) or COUNT_C.search(s))
        sick_now = bool(SICK_NOW.search(s))
        one_person = bool(INDIVIDUAL.search(s)) and not (AWARE.search(s) or HYPO.search(s) or ADVICE.search(s))
        # Vaccine-benefit sentences and rates are not case reports unless they say "now".
        is_rate = (RATE.search(s) or AWARE.search(s)) and not CUR.search(s) and not sick_now
        if (has_number or sick_now or one_person or EVENT_C.search(s)) and not is_rate and not GENERIC.search(s):
            old_year = any(int(y) <= scan_year - 2 for y in YEAR.findall(s)) or bool(DECADE.search(s))
            if (is_past(s) or old_year) and not CUR.search(s):
                found["history"] += 1
            else:
                found["numbered" if has_number else "event"] += 1
                found["anchored"] += bool(CUR.search(s))
        found["trend"] += is_trend(s, animal_only)
        found["response"] += bool(RESPONSE.search(s))
    return found


def share(pattern, sentences: list[str]) -> float:
    """Share of the given sentences that match the pattern (a regex, or a function returning True/False)."""
    matches = pattern.search if hasattr(pattern, "search") else pattern
    return sum(1 for s in sentences if matches(s)) / len(sentences)


def bucket_article(raw_text: str, scan_year: int) -> tuple[str, str]:
    """Return (bucket, reason) for one article."""
    text = " ".join(raw_text.split())
    junk = junk_bucket(text)
    if junk:
        return junk

    flu_sentences = [s for s in SENT.split(raw_text) if FLU.search(s)]
    if not flu_sentences:
        return "N_no_flu_text", "no flu term anywhere in the text"

    # --- how much of the article is about animals, other diseases, or idioms ---------------------
    n_flu = len(FLU.findall(text))
    n_animal = len(ANIMAL_TERMS.findall(text))
    if n_animal / (n_flu + n_animal) >= ANIMAL_RATIO:
        found = count_sentences(raw_text, scan_year)
        if found["bird_flu_human"]:
            return "Z_zoonotic_human", "bird flu article with a human-case sentence"
        return "N_animal_flu", "animal-flu terms dominate and no human cases"
    if share(IDIOM, flu_sentences) >= IDIOM_SHARE:
        return "N_flu_idiom", "stomach flu, man flu, dog flu or flu-trends"

    found = count_sentences(raw_text, scan_year)
    current = found["numbered"] + found["event"]
    other_disease_sentences = sum(1 for s in SENT.split(raw_text) if OTHER_DIS.search(s))
    if other_disease_sentences > n_flu and current + found["trend"] + found["response"] == 0:
        return "N_other_disease", "another disease is mentioned more than flu"

    # --- likely useful ---------------------------------------------------------------------------
    research_share = share(RESEARCH, flu_sentences)
    history_share = share(is_past, flu_sentences)
    if current and (research_share < RESEARCH_MAX or found["anchored"]):
        if found["numbered"]:
            return "P_A1_counts", "current numbered count (cases, deaths, patients)"
        return "P_A2_case_event", "current case or death event without a number"
    if (found["trend"] or found["response"]) and (research_share < RESEARCH_MAX or found["trend"]) and history_share < 0.5:
        return "P_B_trend_response", "trend, onset, quiet-season or response statement"

    # --- likely not useful -----------------------------------------------------------------------
    if history_share >= HISTORY_MIN or (found["history"] and not current):
        return "N_history_only", "flu sentences are about past years"
    if research_share >= RESEARCH_MIN:
        return "N_research", "study, lab or research framing"
    if share(BUSINESS, flu_sentences) >= BUSINESS_MIN or share(POLICY, flu_sentences) >= POLICY_MIN:
        return "N_business_policy", "market, funding or regulation framing"
    if share(AWARE, flu_sentences) >= AWARENESS_MIN:
        return "N_awareness", "vaccine, prevention or explainer wording"
    return "N_other_flu_mention", "flu is mentioned but no pattern matched"
