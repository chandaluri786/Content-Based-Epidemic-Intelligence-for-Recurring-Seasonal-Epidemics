"""Keyword rules that decide whether an article is flu related.

An article is flu related if its BODY text (not link, not header) contains at least one flu term.
Terms were derived from (1) the 1,280 labeled sample entries and (2) a full scan of the 230,409-article
GDELT corpus (2015-2024). Source tags: "seen" = found in the sample or corpus, "ext" = general knowledge,
never seen in either.

SCOPE: English language only. Flu words in other languages (Vogelgrippe, gripa, 流感, грипп ...) are NOT in the
list. Non-English articles are out of scope: they are not validated and are bucketed only by the English-attested
terms they happen to contain (strain codes, brand names, "influenza").

How it works
  1. normalize(): fix ligatures (NFKC), soft hyphens, "In?uenza" (lost fl ligature), "influ-enza" (line-break
     hyphen), and remove "flu/cy" (the fludarabine/cyclophosphamide chemo regimen).
  2. Every run of ASCII letters that contains flu / grip / influ / amivir / tamif / baloxavir ... is checked by
     accept_token(). This catches words glued together in URLs and hashtags (swineflu, flulike, theraflu).
  3. Pattern rules catch strains (H#N#), lineages, surveillance names and animal-flu terms.
"""
import re
import unicodedata

# --------------------------------------------------------------------------------------------------
# 1. normalisation
# --------------------------------------------------------------------------------------------------
_HYPHEN_BREAK = re.compile(r"(?i)\b(influ|influe|influen|in|inf|infl)-\s?(enza|nza|za|fluenza|luenza|uenza)\b")
_FLU_CY = re.compile(r"(?i)\bflu\s*/\s*cy\b|\bflu\s*/\s*cyclo\w*")


def normalize(text):
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("­", "").replace("​", "")
    t = re.sub(r"(?i)\bin\?uenza", "influenza", t)  # fl ligature lost to "?"
    t = _HYPHEN_BREAK.sub(lambda m: m.group(1) + m.group(2), t)
    t = _FLU_CY.sub(" ", t)
    return t


# --------------------------------------------------------------------------------------------------
# 2. token rules (lowercase ASCII letter runs)
# --------------------------------------------------------------------------------------------------
CAND = re.compile(r"[a-z]*(?:flu|grip|influ|amivir|tamif|baloxavir|piravir|relenza|arbidol|antadine)[a-z]*", re.I)

# typo forms of influenza seen in the corpus
TYPOS = {
    "infuenza", "infleunza", "inluenza", "inlfuenza", "influeneza", "influneza", "influeza", "influezna",
    "nfluenza", "lnfluenza", "ifluenza", "tnfluenza", "inuenza", "influnza", "inflenza", "influenz", "influenze",
}

# tokens that contain "flu" (or look like it) but are NOT flu
DENY_FRAG = re.compile(
    r"fluid|fluct|fluo|fluff|fluen|flux|flue(?!nz|y)|fluk(?!n)|flumm?ox|flummery|flume|flung|flunk|fluster|flush(?!ot|ow)|"
    r"flut(?:e|ter|ist|ie|icas)|flub(?!l?ok|ird)|flupir|fluphen|flupent|flurr|flurbi|flurazep|fluro|fluvial|fluvanna|"
    r"fluvoxam|fluvastat|fluconaz|flucloxa|fludar|fludro|flunix|flunomide|roflumilast|diflucan|fenflur|"
    r"affluen|confluen|effluen|efflu|mellifl|superfluo|pflug|fluminense|fluharty|fluckiger|flutie|"
    r"fluqe|styraciflua|^influ(?!enz|vac|vax)|influen(?!z)|influss|bonaflu|aflutter|vinflun|triflu|perfluor|polyflu|hexaflu|"
    r"isoflu|sevoflu|desflu|chloroflu|difluor|trifluor|hydroflu|alexaflu|lufu|fluxul|fluidiz|"
    r"flucht|flugzeug|flucks|flutsch|flufen|enflure|flucytos|fluciclo|fluture|"
    r"flugel|fluilds|fluiteq|fluridat|fludic|flurescent|flurosc",
    re.I,
)
# exact tokens denied even though they contain "flu"
DENY_EXACT = {"aflu", "paraflu", "flub", "fluffs", "ugripq", "flug", "fluge", "fluss", "flujo", "flunder", "fluhart",
              "flubros", "flubro", "flubras", "flurf", "flurotech", "flurotest",
              "flud", "fluw", "iyxfflu", "yayfluhcwfeo", "fluktuasi"}
# allowed even though a deny fragment matches (flu vaccines/drugs/surveillance whose name starts like a false word)
ALLOW = re.compile(
    r"^(?:fluenz\w*|efluelda|fluview\w*|flushot\w*|flushow\w*|getmyflushot|findaflushot|schoolflushot|shastaflushots|"
    r"octoflushow|fludase\w*|fludrop\w*|fludb|fludemic\w*|flumos|flumist\w*|flumadine|flucide\w*|flublok|flubok|"
    r"fluey|flugen\w*|influvac\w*|influvax|superflu|flurona)$",
    re.I,
)

# English-attested forms only: "grippe" / "la grippe" (old English word for flu), "grippal", and brand or
# system names (Vaxigrip, Agrippal, Grippol, Gripp-Heel, InfoGripe).
GRIP_ACCEPT = re.compile(
    r"^(?:grippe|lagrippe|grippal|gripp|gripex|grippex|extragrip|infogripe?|vaxigrip\w*|agrippal|grippol)$"
)


def accept_token(tok):
    """True if a lowercase letter-run is a flu word."""
    if tok in ("flu", "flus"):
        return True
    if "influenz" in tok:
        return not (tok.startswith(("parainfluenz", "paraenfluenz")) or tok in ("influenzae", "parainfluenzae"))
    if tok in TYPOS:
        return True
    if "amivir" in tok or "tamif" in tok or "baloxavir" in tok or "favipiravir" in tok or tok in (
            "relenza", "arbidol", "amantadine", "rimantadine", "umifenovir", "pimodivir", "rapivab", "inavir"):
        return True
    if "grip" in tok:
        return bool(GRIP_ACCEPT.match(tok))
    if "flu" in tok:
        if ALLOW.match(tok):
            return True
        if tok in DENY_EXACT or DENY_FRAG.search(tok):
            return False
        return True
    return False


# --------------------------------------------------------------------------------------------------
# 3. pattern rules: (group, source, regex, flags)
# --------------------------------------------------------------------------------------------------
I = re.IGNORECASE
PATTERNS = [
    # strains: H1N1, H5N1, H3N2v, h7n9 and any other H#N#, also when glued to a word (h5n1strain)
    ("strain", "seen", r"(?<![A-Za-z])h\d{1,2}n\d{1,2}(?!\d)", I),
    # lineages
    ("lineage", "seen", r"\bB/(?:Victoria|Yamagata)\b|\bB/(?:Phuket|Austria|Colorado)/\d+|\b(?:Victoria|Yamagata)[- ]lineage\b|\bB-(?:Victoria|Yamagata)\b", I),
    ("lineage", "ext", r"\bB/(?:Brisbane|Washington)/\d+|\bA/(?:Brisbane|Victoria|Perth|Hong\s*Kong|California|Michigan|Texas|Switzerland|Singapore|Darwin|Sydney)/\d+|\bpdm09\b|\bclade\s+2\.3\.4\.4b?\b|\bsubtype\s+H\d{1,2}\b", I),
    # surveillance acronyms
    ("surveillance", "seen", r"\bILI\b", 0),  # uppercase only
    ("surveillance", "ext", r"\bILINet\b|\bRIDT\b|\bGISRS\b|\bNREVSS\b|\bERVISS\b|\bFluID\b", 0),
    ("surveillance", "ext", r"\bnational\s+influenza\s+cent(?:er|re)s?\b", I),
    # animal-flu abbreviations
    ("name", "ext", r"\bHPAI\b|\bLPAI\b|\bHPAIV\b|\bhighly\s+pathogenic\s+avian\b|\bfowl\s+(?:plague|pest)\b", I),
    ("name", "ext", r"\bswine-origin\b", I),
]
PATTERNS = [(g, s, re.compile(p, f), p) for g, s, p, f in PATTERNS]


def flu_hits(text):
    """List of (group, source, matched_text) for the article body."""
    t = normalize(text)
    hits = []
    for m in CAND.finditer(t):
        w = m.group(0).lower()
        if accept_token(w):
            hits.append(("word", "seen", w))
    for g, s, rx, _ in PATTERNS:
        for m in rx.finditer(t):
            hits.append((g, s, m.group(0)))
    return hits


def is_flu_related(text):
    t = normalize(text)
    for m in CAND.finditer(t):
        if accept_token(m.group(0).lower()):
            return True
    return any(rx.search(t) for _, _, rx, _ in PATTERNS)
