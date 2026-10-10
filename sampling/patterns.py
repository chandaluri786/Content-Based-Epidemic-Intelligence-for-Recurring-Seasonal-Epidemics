"""Word patterns (regular expressions) used to sort articles into piles.

Every pattern was derived from a scan of the 36,508 stored articles. They only decide which pile
an article goes into; people give the final label. Matching ignores upper/lower case (re.I).

Sections:
  - sentence splitting and number words
  - clean-up patterns (spam, dated headlines)
  - "not human flu" topics (animals, other diseases, idioms, history, research, business, awareness)
  - human-flu signals (counts, events, trend words, responses, symptoms, bird flu in people)
"""
import re

FLU = re.compile(r"\b(?:flu|influenza|h1n1|h3n2|h5n1|h5n8|h7n9|h5n6|swine flu|bird flu|avian flu|avian influenza)\b", re.I)
SENT = re.compile(r"(?<=[.!?])\s+|\n+")
NUM = r"(?:\d[\d,]*|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty|fifty|dozens?|hundreds?|thousands?)"

# ---- hygiene -------------------------------------------------------------------------------
SPAM = re.compile(r"ugbet|judi online|togel|casino|cassino|krocobet|olxtoto|slot gacor|aviator|taruhan|apostar|xem tr\w*c ti\w*p|xoilac|socolive|copy-trading|\bCFD\b|forex|pornograf|porn\b|escort|captcha|verify you are human|request unsuccessful|incapsula|cloudflare|access denied|系统维护|bank online|subscribe now for unlimited access|no longer be publishing|enable javascript|enable cookies|page not found|404 not found", re.I)
DATE_HEAD = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.? \d{1,2}, ?20\d\d\b", re.I)

# ---- topic confusers ----------------------------------------------------------------------
ANIMAL = re.compile(r"\b(?:bird flu|avian|poultry|chickens?|ducks?|turkeys?|geese|goose|wild birds?|migratory|culled|culling|slaughter\w*|livestock|farms?|flocks?|hogs?|pigs?|swine herds?|piglets?|equine|horses?|canine|dogs?|cats?|feline|h5n1|h5n2|h5n8|h7n9|h5n6|h7n7)\b", re.I)
PIG_CTX = re.compile(r"\b(?:pigs?|hogs?|swine herds?|piglets?|fair|variant|h3n2v|h1n2v)\b", re.I)
HUMAN = re.compile(r"\b(?:patients?|people|persons?|residents|children|kids|students|infants|babies|elderly|women|men|man|woman|girl|boy|hospitali\w+|admitted|diagnosed|human cases?|human infections?|humans|clinic|victims?)\b", re.I)
OTHER_DIS = re.compile(r"\b(?:ebola|zika|dengue|measles|mers|sars|malaria|hiv|aids|cholera|tuberculosis|tb|whooping cough|pertussis|norovirus|polio|mumps|rubella|meningitis|hepatitis|chikungunya|rsv|coronavirus|lassa|yellow fever|typhoid|chickenpox|shingles|strep)\b", re.I)
IDIOM = re.compile(r"\b(?:stomach flu|man flu|dog flu|canine influenza|canine flu|cat flu|horse flu|equine influenza|tummy flu|24-hour flu|stomach bug|google flu trends|flu trends)\b", re.I)
HIST = re.compile(r"\b(?:(?:19|20)\d0s|spanish flu|spanish influenza|1918|1957|1968|1976|2009 pandemic|years ago|decades ago|last century|historical\w*|great influenza|last year|last season|last winter|previous season|previous year|last flu season)\b", re.I)
RESEARCH = re.compile(r"\b(?:study|studies|researchers|scientists|published in|journal|trial|findings|peer-reviewed|mice|ferrets|genome|vaccine candidate|retrospective|cohort|enrolled|participants|odds ratio|risk factors?)\b", re.I)
BUSINESS = re.compile(r"\b(?:shares|stock|stocks|investors|earnings|revenue|sales|market|profit|nasdaq|nyse|analyst|price target|merger|acquisition|manufacturer|forecast to|cagr|billion)\b", re.I)
POLICY = re.compile(r"\b(?:budget|funding|legislation|lawmakers?|senate|congress|parliament|policy|grant|appropriat\w+|subsid\w+|regulat\w+|trade|export|import)\b", re.I)
SPORT = re.compile(r"\b(?:team|coach|player|players|game|nfl|nba|mlb|nhl|football|basketball|cricket|rugby|tournament|actor|actress|singer|pop star|rapper|celebrity|concert|band|tour|athlete|footballer|cricketer|star)\b", re.I)
AWARE = re.compile(r"\b(?:flumist|flu shots?|vaccin\w+|immuni[sz]\w+|get your|(?<!and )prevent\w*|protect yourself|protect against|wash your hands|handwashing|cover your (?:mouth|cough)|stay home|tips|how to|myths?|faq|what you need to know|symptoms of|signs of|precautions?|booster|nasal spray|herd immunity|effective(?:ness)?|symptoms include|common symptoms)\b", re.I)

# ---- signals (human, flu) -------------------------------------------------------------------
CASE_NOUN = r"(?:cases?|deaths?|fatalit\w+|patients?|victims?|infections?|hospitali[sz]ations?|admissions?|persons?|people|lives|children|kids|students|residents|infants|babies|women|men|workers|staff)"
VERB_AFTER = r"(?:died|dead|killed|infected|sick|diagnosed|hospitali[sz]ed|admitted|tested positive|fell ill|affected|suffering|treated|confirmed|infected with|ill)"
COUNT_A = re.compile(rf"\b{NUM}\s+(?:(?!(?:of|and|per|for|to|the|in|on|with|by|from|at)\b)[\w-]+\s+){{0,3}}?(?:cases?|deaths?|fatalit\w+|patients?|victims?|infections?|hospitali[sz]ations?|admissions?)\b", re.I)
COUNT_C = re.compile(rf"\b(?:killed|claimed the lives of|claimed|sickened|infected|hospitali[sz]ed|left|struck)\s+(?:at least |more than |over |nearly |about |around |some |almost )?{NUM}\s+(?:more\s+)?(?:people|persons?|children|kids|students|residents|patients|infants|women|men)\b", re.I)
COUNT_B = re.compile(rf"\b{NUM}\s+(?:people|persons?|children|kids|students|residents|infants|babies|women|men|workers|staff|inmates|pupils)\s+(?:\w+\s+){{0,3}}{VERB_AFTER}\b", re.I)
EVENT_C = re.compile(r"\b(?:died (?:of|from|after)|dies (?:of|from)|death of|killed by|succumbed to|tested positive|test(?:ed)? positive|confirmed (?:with|cases?|positive)|(?:was|were|is|are) (?:confirmed|diagnosed) (?:with|as having)|admitted (?:with|to)|hospitali[sz]ed (?:with|for|due)|first (?:flu |swine flu |h1n1 )?(?:cases?|deaths?|infections?|patients?|fatalit\w+|victims?)|(?:flu|influenza|h1n1|swine flu) (?:cases?|infections?) (?:(?:are|were|was|is|have been|has been|being) )*(?:reported|confirmed|detected|found|recorded)|cases? of (?:the )?(?:flu|influenza|swine flu|h1n1) (?:were |was |have been |has been )?(?:reported|confirmed)|death toll|toll (?:rose|rises|climbs|reaches|has)|claimed (?:the )?lives?)\b", re.I)
TREND_UP = r"on the rise|rising|\brise[sd]?\b|\brose\b|increase[sd]?|increasing|surg\w+|spik\w+|climb\w*|jump\w*|soar\w*|skyrocket\w*|uptick|ramp\w*|growing|worsen\w*|mounting|escalat\w*"
TREND_DN = r"declin\w+|decreas\w+|\bdrop\w*|\bfall(?:ing|s)?\b|\bfell\b|\beas(?:e|es|ed|ing)\b|subsid\w+|wan(?:e|es|ed|ing)|taper\w*|slow(?:ed|ing)|recede\w*|abat\w+"
PEAK = r"peak\w*|height of|at its worst|worst of the (?:flu )?season"
ONSET = r"early arrival|arriv\w+ (?:of )?(?:the )?(?:flu )?season|season (?:has )?arrived|arrived early|first (?:flu |swine flu |h1n1 )?(?:case|cases|death|confirmed|reported)|season (?:has |have )?(?:begun|began|begins|started|starts|is here)|has begun|have begun|early start|started early|officially|underway|under way|beginning to|start of the (?:flu )?season|kicked off|onset|taking hold"
EXTENT = r"widespread|epidemic|outbreak|nationwide|statewide|across the (?:state|country|nation)|regional|hitting|sweeping|hit hard|geographic spread"
LOWQ = r"quiet|milder|mild (?:flu|season)|sporadic|isolated|minimal|slow start|late start|low activity|remains low|still low|lower than"
SIZE = r"few|several|many|dozens|scores|hundreds|thousands|handful|sharp|steady|significant|substantial|slight(?:ly)?|dramatic|rapid(?:ly)?|alarming|unusually|higher than"
QUIET = r"no (?:new |confirmed |reported )?(?:cases|deaths)|has not yet|have not yet|yet to|not yet|no sign|so far this (?:season|year)|only (?:a few|one|two)|have been few"
EPI_CTX = re.compile(r"\b(?:season|cases?|activity|outbreak|epidemic|patients?|infections?|illness(?:es)?|deaths?|spread|hospital\w*|levels?)\b", re.I)
TREND = re.compile(rf"\b(?:{TREND_UP}|{TREND_DN}|{PEAK}|{ONSET}|{EXTENT}|{LOWQ}|{QUIET})\b", re.I)
SIZEW = re.compile(rf"\b(?:{SIZE})\b", re.I)
EPI_N = r"(?:flu season|season|cases|case|activity|outbreaks?|epidemics?|infections|illness(?:es)?|deaths|spread|hospitali[sz]ations|levels|numbers|patients|admissions)"
TREND_NEAR = re.compile(rf"\b(?:{TREND_UP}|{TREND_DN}|{PEAK}|{ONSET}|{EXTENT}|{LOWQ}|{QUIET})\W+(?:\w+\W+){{0,6}}?{EPI_N}\b|\b{EPI_N}\W+(?:\w+\W+){{0,6}}?(?:{TREND_UP}|{TREND_DN}|{PEAK}|{ONSET}|{EXTENT}|{LOWQ}|{QUIET})\b", re.I)
CELEB_PERSON = re.compile(r"\b(?:singer|actress|actor|pop star|rapper|athlete|footballer|cricketer|minister|former|president|prime minister|mp|mla|leader|star)\b", re.I)
RESPONSE = re.compile(r"\b(?:schools? (?:were |are |have been |was )?(?:closed|shut)|closed (?:its |the )?schools?|school closures?|isolation wards?|quarantin\w+|red alert|alert (?:issued|sounded|raised)|visiting restrictions|task force|helpline|screening (?:counter|centre|center|camp)s?|screening (?:of|for|at) |(?:declared|declares|declaring) (?:a |an )?(?:public health |health )?(?:emergency|epidemic|outbreak)|state of emergency|health emergency|emergency (?:declared|measures)|outbreak declared|epidemic declared|holiday(?:s)? (?:extended|declared)|masks? (?:mandatory|compulsory|distributed))\b", re.I)
RATE = re.compile(r"(?:%|\bper ?cent\b|\bpercent\b|per 100,?000|\baverage\b|\bmedian\b|\bratio\b)", re.I)
SYMPT = re.compile(r"\b(?:fever|cough\w*|sore throat|body aches?|chills|runny nose|sneezing|fatigue|headaches?|flu-like|influenza-like|respiratory illness)\b", re.I)
SYMPT_EVT = re.compile(r"\b(?:reported|complain\w*|developed|fell ill|falling ill|come down with|came down with|down with|sick|suffering|treated|visited|presented|absent|absenteeism|affected)\b", re.I)
POP = re.compile(r"\b(?:people|patients|children|kids|students|residents|staff|workers|dozens|hundreds|scores|several|many|number of|pupils|inmates)\b", re.I)
HYPO = re.compile(r"\b(?:could|would|might|may|if a|if there|if the|in case|should|hypothetical|scenario|exercise|drill)\b", re.I)
NEG_EVID = re.compile(r"\b(?:no evidence|no indication|no sign of|there is no|nothing to suggest)\b", re.I)
NONFLU_EMERG = re.compile(r"\b(?:zika|ebola|mers|polio|international concern|pheic|microcephaly|yellow fever)\b", re.I)
PHARMA = re.compile(r"\b(?:drugs?|molecule|compound|candidate|highly active|resistant to|adamantanes|tamiflu|oseltamivir|antibod\w+|adjuvant|pipeline)\b", re.I)
GENERIC = re.compile(r"\b(?:usually|typically|generally|normally|each year|every year|annually|annual|per year|most years|most often|runs from|lasts? (?:from|until|through)|peaks? (?:in|during|between|around)|ends? in|begins? (?:in|as early|as soon)|can begin|signal(?:s)? (?:not only|the)|approach of (?:fall|winter)|time of year|season (?:runs|lasts|typically|usually))\b", re.I)
OLDYEAR = re.compile(r"\b(?:19\d\d|200\d|201[0-3])\b")
STATUS = re.compile(r"\b(?:(?:widespread|high|very high|elevated|moderate|low|minimal|sporadic|regional|local|extreme|severe|geographic spread)(?:ly)?\s+(?:flu |influenza |influenza-like |ili )?(?:activity|conditions|levels?|spread)|reporting (?:widespread|outbreaks|flu|influenza)|outbreaks? (?:in|across) (?:every|all|most|nearly every) (?:state|region|district)|every state (?:is )?reporting|worse than (?:last|previous|usual)|(?:bad|severe|mild|heavy|early|late|slow|nasty) flu season|flu season (?:is|looks|looking|appears|seems) (?:worse|bad|mild|severe|early|late|early|slow|off)|(?:flu|influenza) (?:is|are) (?:now )?(?:widespread|everywhere)|(?:flu|influenza|h1n1|swine flu) (?:is |has been |was )?(?:now )?spreading|(?:flu|influenza)(?: cases)? (?:is |are |has been )?going around|not much flu|widespread (?:flu|influenza))\b", re.I)
TYPE_UNCERTAIN = re.compile(r"\b(?:suspected|probable|presumptive|reportedly|allegedly|unconfirmed|feared|believed to|being tested|awaiting|pending|samples? (?:were |was )?sent|under observation|isolation ward)\b", re.I)
CUR = re.compile(r"\b(?:today|tonight|yesterday|this (?:week|month|morning|season|flu season)|so far|to date|currently|right now|at present|on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|last week|past (?:week|few days|month)|since (?:last|early|late)? ?(?:october|november|december|january|february|march|april|may|june|july|august|september|monday|friday)|this year's|this year)\b", re.I)

ZOON_SUB = re.compile(r"\b(?:h7n9|h5n1|h5n6|h9n2|h7n7|bird flu|avian (?:flu|influenza))\b", re.I)
ZOON_HUM = re.compile(rf"\b(?:{NUM}\s+(?:new\s+|more\s+|additional\s+)?(?:human\s+)?(?:h7n9|h5n1|h5n6|h9n2|avian flu|bird flu)\s+(?:infections?|cases?|deaths?)|(?:h7n9|h5n1|h5n6|h9n2)\s+(?:avian flu\s+)?(?:infections?|cases?)\s+(?:have been\s+|were\s+|was\s+)?(?:confirmed|reported)|human (?:cases?|infections?|deaths?) (?:of|with|from)|(?:a |an )?(?:man|woman|patient|child|boy|girl|farmer|poultry worker)\b[^.]{0,40}\b(?:h7n9|h5n1|h5n6|avian flu|bird flu))\b", re.I)
ZOON_NEG = re.compile(r"\b(?:no (?:human|indication|evidence|reports?)|not (?:been )?(?:transmitted|infect\w+) (?:to )?humans?|poses? no|no immediate public health)\b", re.I)


# Percent of a group that is sick right now ("20 percent of students and staff are sick with flu").
SICK_NOW = re.compile(r"\b\d+(?:\.\d+)?\s?(?:%|percent|per cent)\s+of\s+(?:\w+\s+){0,4}(?:are|were|have been|is)\s+(?:currently\s+)?(?:sick|ill|absent|out sick|infected|down with)\b", re.I)
# Comparing this year with an earlier one ("outpacing the numbers at this time last year") is a current statement.
COMPARE = re.compile(r"\b(?:than|compared (?:to|with)|versus|vs\.?|from|outpacing|ahead of|behind|above|below|same time|this time) (?:\w+ ){0,4}(?:last (?:year|season|winter)|a year ago|year earlier)\b", re.I)

# One named person's flu illness as reported ("was treated for the flu", "battling the flu", "fell ill with the flu").
INDIVIDUAL = re.compile(r"\b(?:(?:treated|hospitali[sz]ed|admitted|rushed to (?:a |the )?(?:local )?hospital|taken to (?:a |the )?(?:local )?hospital) (?:for|with|due to) (?:the |a |an )?(?:severe |bad |nasty |serious )?(?:flu|influenza)|(?:battling|suffering from|fell ill with|fallen ill with|diagnosed with|bout of) (?:the |a |an )?(?:\w+ )?(?:bout of )?(?:the )?(?:flu|influenza)|(?:he|she|they|was|were|had been|has been|being) (?:sick|ill|down) with (?:the )?(?:flu|influenza))\b", re.I)
# Advice or "what if" wording that must not count as a real person's illness.
ADVICE = re.compile(r"\b(?:avoid|if you|you(?:'ll| will| can| may)?|your|anyone|everyone|can get|can cause|should|must|keep|stay|protect|precaution\w*|when you|people who|maintain|so that|transmit\w*)\b", re.I)
