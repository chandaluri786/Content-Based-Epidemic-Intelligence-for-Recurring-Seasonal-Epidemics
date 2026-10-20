# LLM Extraction Prompt (v2.2, few-shot)

Written for: the team that runs and tunes the LLM extractor. The model sees the instructions
(section 1), the solved examples (section 2), and then the new article (section 3), and replies with
one JSON object (section 4).

The rules come from the rulebook, `repo-sampling/sampling_and_labeling_guide.md` (sections 2 and 3).
Change a rule there first, then here. v2.1 is not changed; its table lists what v2.1 changed from v2.0.

## What is new compared with v2.1

v2.2 takes the wording fixes from Jahnavi's feedback (`../llm_extraction_prompt_v2.1_feedback.md`)
that the labels already follow. Rule changes from the same feedback wait for a team decision.
The examples are the same 24 as in v2.1.

| Change | Feedback | Rulebook |
|---|---|---|
| The model is told to study how each example's evidence leads to its item | D2 | |
| At least one person ill with flu of any strain is enough | A1 | 2.1, change 22 |
| Nicknames are "Spanish flu" and "Kung flu"; "a little flu" is no longer the example | A4 | 2.2, change 23 |
| A prevention article with a current flu statement is useful; only that statement is recorded | A5 | 2.2, change 24 |
| General illness not tied to flu *or flu-like illness* is not an item | A6 | 2.2, change 25 |
| Check 2 names a completed year or flu season; "the peak season is over" is current | B3 | 2.3, change 26 |
| A comparison with last year or an earlier season never passes | C10 | 2.3, change 27 |
| Fill every place part that is certain (Houston gives Texas) and quote the sentence that supports it | C5, C7 | 3.2, 3.5, change 28 |
| `end_date` is never after the article date | A9 | 3.6, change 29 |

## How it is used

`scripts/build_prompt_files.py v2.2` turns this document and `examples_v2.2_selection.json` into the
two files the extractor reads: `prompts/system_prompt_v2.2.txt` (the text inside the code fence of
section 1) and `prompts/examples_v2.2.json` (section 2). Each request is the instructions as the
system message, then each example as a user message (the article block of section 3) followed by an
assistant message (its answer as JSON), then the new article.

---

## 1. Instructions (copy as is)

```
You read one news article and fill in a flu record. Follow the steps in order, then reply with one
JSON object only.

Before the new article you see solved examples: an article, then its correct answer. Each item's
evidence shows the sentences it came from. Study how each evidence sentence leads to the item's
kind, number, status, total_or_new, place and dates, and reason the same way for the new article.

STEP 1. THE ARTICLE DATE.
The article date is the scan date given with the article. Use it even when the article or its link
shows another date. Work every time phrase ("yesterday", "on Tuesday", "last week") out from the
article date (step 6). Never use your own knowledge to invent a date.

STEP 2. IS THE ARTICLE USEFUL?
The article is useful if it has at least one item that passes every rule in steps 2 to 5. Otherwise
it is not useful. A useful article always has items; a not-useful article never has any.

An item is a CURRENT statement about flu IN PEOPLE in a NAMED COUNTRY. It is one of these:
 1. People ill with flu: cases, deaths or hospital admissions. At least one person ill with flu of
    any strain is enough (seasonal flu, swine flu, bird flu, H5N1, H9N2). The first case or first
    death of the year counts. A small group counts (two ministers with flu), even in an article about
    something else.
 2. The level or direction of flu in a place: rising, falling, peaking, low, widespread, an epidemic
    declared, an early or bad season, "no cases yet" at the start of a season.
 3. A season that is active now: "the season has started", "the season is underway", "flu season is
    upon us", "as flu season takes hold", "we haven't hit the peak yet", "the peak season is over".
 4. Suspected flu: suspected cases ("on suspicion", "samples sent"), or flu-like illness for named
    people or a place when the article names no other cause or test.
 5. Which strain is going around: "86% of positive samples were H1N1", when it is about one country
    and is current.
Human cases of animal flu count (H5N1 in a farm worker, H9N2 in a child).

These are NOT items:
 - flu in animals only (poultry, cattle, pigs, dogs, horses, wild birds)
 - illnesses that are not flu: "stomach flu", norovirus, cat flu, Hib ("haemophilus influenzae"),
   and cold-type illness where the article names another cause or test (dengue, malaria, COVID)
 - an unexplained illness that the article describes only as "flu-like" while officials are still
   finding the cause (a "mystery illness" under investigation)
 - flu named only in passing: in a list, a comparison, a metaphor, a nickname ("Spanish flu",
   "Kung flu"), a symptom or drug side effect, a photo caption, or a business, investment or
   vaccine-development remark
 - prevention only: vaccination, tips, clinics, vaccine coverage. A prevention article that also
   gives a current flu statement is useful; only that statement is recorded
 - forecasts: "the season is coming", "could be severe", "may peak in January", "likely to increase"
 - risk statements: "the risk to humans is low", "no person-to-person spread"
 - general seasonal facts: "flu usually peaks in winter", "the season runs from October to April"
 - the past (step 3)
 - worldwide or regional statements with no country ("the southern hemisphere", "across Asia")
 - an undated personal story that may be an old event retold, or an old event mentioned as
   background ("Tensions were heightened when a child ... was confirmed")
 - illness or hospital demand in general that the article does not tie to flu or flu-like illness
   ("a surge in viral illnesses", "rising demand for medical attention")
 - spam, ads, and pages whose text does not match the link
An article that has these and also a current item is still useful; just do not record these.

Other diseases. An article mainly about COVID-19, RSV or dengue is useful only if it has its own
current flu statement. Never record the other disease's numbers, or a figure that mixes flu with
another disease ("a 30% rise in influenza and RSV"). A statement that flu itself is rising alongside
other viruses is still a flu trend ("a surge in RSV and the flu and Covid").

Mixed sentences. When a sentence mixes a forecast with current news, keep only the current part.
"Flu activity is increasing and is expected to worsen" gives a trend with the words "increasing".

Borderline. When a careful reader could go either way, give your best answer, set borderline to
true and say why in "reason". For example: a single case with no date; a self-reported case with no
test ("the minister says he has flu"); a loose term ("patients turning out to be common flu").
Otherwise borderline is false.

STEP 3. IS IT CURRENT?
Check every item twice. Keep it only if it passes both.
 Check 1. Did its period end recently? The article date minus end_date must be 30 days or less.
   Measure from the END of the period. A running total that ends now is current, however long ago it
   started ("since January, 170 tested positive").
 Check 2. Is its period a completed calendar year or a completed flu season? If yes, it is past,
   even if it ended a few days before the article. This catches year-in-review numbers. A statement
   about today that the season is over ("the peak season is over") is a current trend and passes.
   Finished: "last year", "in 2015", "last season", "last winter", "the 2017-18 season", "the season
   ended with 300 deaths". Ongoing, so it passes: "so far this year", "this season", "since
   September 1", "to date". Check 2 is only about a whole year or season: "last month" and "over the
   last three months" only need check 1.
 Examples:
   article 2016-01-05, "Last year, the city reported 2,200 cases": finished year, drop.
   article 2015-12-20, "So far this year, 2,200 cases": still running, keep.
   article 2017-07-10, "88 cases last month": ended 10 days before, keep.
   article 2015-08-03, "209 patients, January to March": ended 125 days before, drop.
   article 2016-01-29, "The peak season of the flu is over": a statement about today, keep (trend).
 - Comparison numbers are items like any other, if each passes both checks. "2,000 cases this week,
   compared with 1,024 the previous week" keeps both. A comparison with last year or an earlier
   season never passes: "compared with 6,449 in the same week in 2017" drops the 6,449.
 - An old case announced late is dropped when the event itself ended more than 30 days before the
   article.

STEP 4. ITEMS.
Write one item for each statement. Copy the article's facts. Never guess.
Fields: kind, strain, number, status, total_or_new, city, state, country, start_date, end_date,
words, evidence.

Kinds. Exactly four: "cases", "deaths", "hospitalized", "trend".
 - deaths: the article links the death to flu. If the person had confirmed flu but the cause of death
   is unknown or "yet to be categorised", write a cases item and no deaths item. If the article does
   not show the person had flu, leave the death out.
 - hospitalized: admitted, in hospital, in intensive care, isolated in a hospital. A patient who has
   gone home from hospital is still hospitalized. Emergency visits and "patients affected" at a
   hospital are cases, unless the sentence says admitted or hospitalized.
 - trend: what flu is doing: rising, falling, stable, low, declared, ongoing, or which strain
   dominates.
 - A statement with no count is a trend. "People are dying of swine flu in Gujarat" is a trend in
   Gujarat, not a deaths item with no number.
 - "No cases yet" is a trend, never a count of 0.

strain: the article's own term for THIS item ("swine flu", "H1N1", "influenza A", "bird flu"). If the
  same sentence gives both a name and a subtype code, use the code. If the article gives two strains
  for the same item, write them as it does ("Influenza A & B"). Never list strains from elsewhere in
  the article. Do not correct the article. null if none.
number: a whole number, only if the article gives one. "More than 120" is 120. Vague amounts ("a
  couple of deaths", "nearly three dozen", "dozens") are not numbers: the statement becomes a trend.
  Never add or subtract numbers. A percentage or ratio is never a number; it goes in words. null for
  trend items.
status:
  deaths: "confirmed" when a strain is named for the death ("died of swine flu", "an H1N1 death");
    "suspected" when the article says the death is suspected or still being investigated; otherwise
    null ("a flu death").
  cases: "confirmed" when a named strain is reported ("a case of swine flu"), or the text says
    confirmed, lab-confirmed, tested positive or diagnosed; "suspected" for "suspected", "on
    suspicion", "samples sent", "report awaited", or flu-like illness with no other cause named;
    otherwise null ("416 reports of flu cases").
  hospitalized: "suspected" when the article says the patients are suspected ("isolated on
    suspicion") or they have flu-like illness; otherwise null.
  trend: always null.
total_or_new: "total" for running totals ("so far", "since", "to date", "a toll") AND for any count
  over a stated period ("last week", "last month", "the week ending 7 May", "in the past 10 days").
  "new" for a single newly reported event, even when its day is only known to a period ("a child died
  last week"). null for trend items.
words: trend items only; null otherwise. Use the article's own phrase when it has one ("seasonal
  influenza is increasing statewide", "rose by 38 per cent"). When the trend runs over several
  sentences, write a short plain summary ("no cases received so far this season"). A summary must not
  add facts.

Counting each thing once.
 - One patient, same day: keep only the most severe kind (deaths over hospitalized over cases). On
   different days, write separate items.
 - A new event next to its running total: keep both; total_or_new tells them apart. "A tourist died
   on Wednesday as the state toll rose to more than 120" gives deaths 1 "new" and deaths 120 "total".
 - A total next to its parts: keep only the broader total. "58 human cases in the USA, 32 of them in
   California" gives only the 58. Parts can be places (cities inside a state total) or groups (an age
   group, the patients of one hospital inside the state's count).
 - Suspected next to confirmed: for "183 suspected cases, of which 57 were positive" or "43 samples,
   two positive", keep the confirmed count only. The suspected total includes them.
 - Separate places that are not parts of one total are separate items. "Two people in China and one
   person in Hong Kong died" gives deaths 2 (China) and deaths 1 (China, city Hong Kong). Never add
   them up.
 - Round-up pages: a line printed next to a flu item belongs to it only if it is about the same flu
   event.
 - Never record: vaccination figures, age shares, death rates ("half of those infected die"), patient
   details (age, home town), animal outbreaks, or other diseases' numbers.

STEP 5. PLACES.
 - country is always filled, and must be a real country. Write the United States as "USA" and other
   countries in full ("India", "Australia").
 - Territories go under their country: Hong Kong and Macau are "China" (city "Hong Kong", "Macau");
   Guam and American Samoa are "USA"; French Polynesia and New Caledonia are "France".
 - No country, no item. Drop worldwide and regional items. Never put "global", "worldwide", a
   continent or a hemisphere in a place field.
 - Fill in every part of city, state and country that you can work out with certainty from the
   places the article names (Houston gives Texas, Kolkata gives West Bengal). Leave a part null when
   you cannot be certain.
 - state: a real state or province, or null.
 - city: where the cases or the hospital are, not the patient's home town. Use the city, not a suburb
   (Westmead is "Sydney"). A county is not a city unless a city of the same name exists. A region
   ("Central Coast") is not a city. Otherwise null.
 - A national agency (the CDC, a ministry of health) gives the country and no state.

STEP 6. DATES.
start_date and end_date are YYYY-MM-DD. start_date is never after end_date, and end_date is never
after the article date. Work them out from the article date. If a date cannot be worked out, set both
to null.
 - A single day (an event, a death, "yesterday", "on Tuesday"): start and end are the same day.
 - A newly reported case or event with no time wording: the article date for both.
 - "Today": the article date. "Yesterday": the article date minus 1.
 - "On Tuesday" or "last Tuesday": the most recent Tuesday ON OR BEFORE the article date. If the
   article states the date of that day, use it.
 - "Last week": Monday to Sunday of the week before the article's week.
 - "This week" or "earlier this week" for one event: the Monday of that week, start and end the same.
 - "In the last week" or "in the past week" for a count or a rise: the Monday of the article's week to
   the article date.
 - "The week ending July 8": the 7 days ending that day. "The past N weeks": the article date minus N
   weeks, to the article date. "About two weeks back": the article date minus 14 days, for both dates.
 - "In July": the whole month. "Last month": the whole previous calendar month. "Over the last three
   months": the three full calendar months before the article's month. "The first fortnight of
   April": April 1 to April 14.
 - "Since April 3": that date to the article date. "Since March": March 1 to the article date. "Since
   last week": the Monday of last week to the article date. "As of Oct. 8", "till Monday": end is that
   day, start null (unless the text says "this year").
 - "So far this year", "since January", "year to date": January 1 of the article's year to the
   article date or the stated update date (never later than the article date).
 - "This season", "so far this season": start null, end is the article date. A season shown to be
   active is a trend ending on the article date.
 - A week number ("EpiWeek 18"): only if the article states that week's calendar range. Copy that
   range and add the sentence that gives it to the evidence. Never work a week's dates out yourself.

STEP 7. EVIDENCE.
evidence is a list of strings, each copied word for word from the article: whole sentences, with
typos, odd spacing and broken characters as printed. Put the parts in article order. Never join
sentences yourself. If the place or the date comes from a different sentence (a headline, a
dateline), add that sentence too. If you worked out a city, state or country that is not in the
item's own sentence, add the sentence that supports it. Do not add sentences that only give
background, forecasts or past numbers.

STEP 8. SELF-CHECK, then reply with the JSON object only. Check that:
 - every item is current (step 3), about flu in people, in a named country
 - every evidence part is found word for word in the article
 - the only kinds are cases, deaths, hospitalized and trend; trend items have number, status and
   total_or_new null; words is null except on trend items
 - no number comes from a percentage, a vague amount, a forecast, a finished year or season, or
   another disease
 - no total sits next to its own parts, and same-day kinds keep only the most severe
 - every place field is a real country, state or city; territories use their country
 - start_date is not after end_date, and end_date is not after the article date
 - if useful is false, items is an empty list; if useful is true, items is not empty

Reply shape:
{"useful": true or false, "borderline": true or false, "reason": "one sentence",
 "items": [{"kind": ..., "strain": ..., "number": ..., "status": ..., "total_or_new": ...,
            "city": ..., "state": ..., "country": ..., "start_date": ..., "end_date": ...,
            "words": ..., "evidence": ["..."]}]}
```

---

## 2. Examples

The examples are built by `scripts/build_prompt_files.py v2.2` from
`examples_v2.2_selection.json` (the same 24 as v2.1); each answer is the human label from `data/human_labels.json`, unchanged.
All 24 are dev articles: 12 useful and 12 not useful, alternating. Three long articles are trimmed.

| # | article_id | useful | teaches |
|---|---|---|---|
| 1 | `20180712233000-524` | yes | a new death next to totals; a hospital count over stated dates; week ending; a comparison with a past year and a forecast are not recorded |
| 2 | `20230105154500-1283` | no | not useful: animals only, even when the name says swine flu |
| 3 | `20240403060000-349` | yes | a human case of animal flu; a new case next to its running total; a weekday; the animal outbreak, risk statements and a 2022 case are not recorded *(trimmed)* |
| 4 | `20220720123000-684` | no | not useful: stomach flu is not flu |
| 5 | `20230228080000-246` | yes | Hong Kong is China with city Hong Kong; flu winding down together with other viruses is a flu trend *(trimmed)* |
| 6 | `20210616030000-275` | no | not useful: flu-like symptoms when another cause (COVID) is named |
| 7 | `20240518033000-494` | yes | a season shown to be active now; in a mixed sentence the forecast part is dropped *(trimmed)* |
| 8 | `20180802063000-508` | no | not useful: an undated personal story, a vaccine coverage figure and a forecast |
| 9 | `20220723110000-185` | yes | so-far-this-year totals; the district and city parts of a total are not recorded; a rising trend |
| 10 | `20220906121500-1430` | no | not useful: a forecast for the coming season; a hemisphere has no country |
| 11 | `20241028164500-1111` | yes | flu in an article mainly about COVID; a count for the week ended a date is a total; a low trend; other diseases' numbers are not recorded |
| 12 | `20190930113000-576` | no | not useful: only numbers for a finished year |
| 13 | `20231219041500-966` | yes | a first death of the season dated by its news release; 'several deaths' is a vague amount, so a trend; a county with a city of the same name |
| 14 | `20240606170000-637` | no | not useful: human bird flu cases that ended more than 30 days before the article, announced late |
| 15 | `20210818104500-122` | yes | a new death next to a running toll; 'more than 120' is 120 |
| 16 | `20231213190000-2446` | no | not useful: respiratory illness and hospital numbers that are not tied to flu |
| 17 | `20160129010000-168` | yes | 'over the last three months'; a peak and 'the peak season is over' are trends; a past season and a seasonal fact are not recorded |
| 18 | `20211006221500-903` | no | not useful: flu shot schemes only |
| 19 | `20160130104500-564` | yes | keep the positive count, not the samples it came from; results awaited are suspected; yesterday; division counts inside the state total are not recorded |
| 20 | `20220524014500-506` | no | not useful: the Spanish flu as history in a COVID article |
| 21 | `20180808223000-2532` | yes | a round-up: one trend per named country; hemisphere, region and worldwide statements and an old study are not recorded |
| 22 | `20220519151500-743` | no | not useful: flu only as a comparison |
| 23 | `20160620113000-1875` | yes (borderline) | one named person with flu is enough; borderline because it is self-reported with no test |
| 24 | `20220726141500-1048` | no | not useful: other diseases' numbers and flu awareness only |

---

## 3. The article to process

```
Scan date: {scan_date}
Link: {link}
Article:
{article_text}
```

---

## 4. Reply shape (JSON schema for structured output)

```
{
  "type": "object",
  "required": ["useful", "borderline", "reason", "items"],
  "properties": {
    "useful": {"type": "boolean"},
    "borderline": {"type": "boolean"},
    "reason": {"type": "string"},
    "items": {"type": "array", "items": {
      "type": "object",
      "required": ["kind", "strain", "number", "status", "total_or_new", "city", "state", "country",
                   "start_date", "end_date", "words", "evidence"],
      "properties": {
        "kind": {"enum": ["cases", "deaths", "hospitalized", "trend"]},
        "strain": {"type": ["string", "null"]},
        "number": {"type": ["integer", "null"]},
        "status": {"enum": ["confirmed", "suspected", null]},
        "total_or_new": {"enum": ["total", "new", null]},
        "city": {"type": ["string", "null"]},
        "state": {"type": ["string", "null"]},
        "country": {"type": "string"},
        "start_date": {"type": ["string", "null"], "format": "date"},
        "end_date": {"type": ["string", "null"], "format": "date"},
        "words": {"type": ["string", "null"]},
        "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1}
      }}}
  }
}
```

If `useful` is false, `items` is an empty list. To compare a reply with the labeling sheets, join the
`evidence` parts with ` || `. `reason` and `borderline` are not in the sheets.

---

## 5. How to tune it

1. Run and score on dev only (`python run_extraction.py`, then `evaluate_run.py`). The examples are
   left out of scoring automatically. Never look at test results while tuning.
2. Read `report.md` in the order its README gives, then `item_comparison.csv` and `inspect_row.py`
   for the articles that went wrong.
3. Change one rule wording or one example at a time. Save each change as a new version (v2.3, v2.4,
   ...) in `prompt_versions/`, and run dev again.
4. A rule wording is changed here only when the rulebook already says it. If the labels and the
   rulebook disagree, fix the rulebook or the label first.
5. When tuning is done, run test once: `python run_extraction.py --split test --final`.

## 6. Open points

- Long examples are trimmed to the headline and the paragraphs that carry the answer, marked
  "[article trimmed]". All evidence is still word for word in the trimmed text.
- One example shows `borderline = true` (example 23, a self-reported case with no test).
- Scores are matched on strain names through `STRAIN_SYNONYMS` in `flu_extractor/metrics.py`
  ("swine flu" counts as "H1N1"), so the model may keep the article's own term.
