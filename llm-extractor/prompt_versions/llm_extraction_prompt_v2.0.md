# LLM Extraction Prompt (v2.0, few-shot)

Written for: the team that will use this prompt to make an LLM label news articles and pull out the useful flu text. It is for **few-shot prompting**: the model sees the instructions, 43 solved articles (the human answers), and then the new article.

This version improves `llm_extraction_prompt_v1.0.md` using `labeling/LABELING_PROCESS_LEARNINGS.md` (section 18, the final rule set for rows 1 to 320, plus sections 12, 17 and the clarifications in 18.9). v1.0 is not changed.

## What is new compared with v1.0

| Change | Why (from the learnings file) |
|---|---|
| 43 examples instead of 14, useful and not useful articles mixed in order; every rule in the instructions that has a clean labeled example has one, and each example heading says which rule it teaches; no example comes from the recheck list (the 20 rows the human found hard) | the examples teach the boundary between the two; the `no` traps are 18.2 |
| Examples of `no` traps v1.0 lacked: flu as a comparison (row 282), a vaccine launch with "haemophilus influenza" (215), a photo caption in a disease story (225), the whole of a closed year (264) | 18.2 |
| Examples where `words` is a short summary and not the article's own phrase (rows 49, 83 and 208) | 18.9 |
| Step 2 is now one definition ("a current human flu statement") with one list of what does not count; the ordered questions A to F of the first draft are gone | removes overlap and contradictions |
| A first case or first death of the year is a `cases` or `deaths` item; a trend is the fallback when nothing tangible can be counted but the place is known and the flu period is ongoing | 18.9 |
| A death is `deaths` when flu is confirmed or suspected as the cause; a confirmed flu case with an unknown cause of death is a `cases` item; otherwise the death is left out | 18.9 |
| Borderline cases explained with a plain example each | 18.5 |
| Items have the same fields as the human sheet (no `date_basis` and no `inferred`) | 18.9 |
| The article date is the scan date only (no printed or link date) | Jahnavi, second review |
| A formal JSON schema, and the examples also come as a `.jsonl` file | so the examples can be sent as chat turns |

## How it is used

One request per article, in this order: the **instructions** (section 1), the **examples** (section 2), the **article** (section 3). The model replies with one JSON object (section 4). Use the API's structured-output mode with the schema in section 4.

Two ways to send the examples:
1. As text, inside the request, exactly as in section 2.
2. As chat turns: for each example, a user message with the "Scan date / Link / Article" block and an assistant message with the "Answer" JSON. The same 43 examples are in `llm_extraction_examples_v2.0.jsonl`, one per line with the keys `scan_date`, `link`, `article`, `answer` (and `teaches`, which is only for the team).

---

## 1. Instructions (copy as is)

```
You read one news article and fill in a flu record. Follow the steps in order.

STEP 1. THE ARTICLE DATE.
The article date is the scan date given with the article. Many statements give time only as "yesterday",
"on Tuesday" or "last week"; work them out from the scan date (step 5). Use the scan date even when the
article or its link shows another date. Never use your own knowledge to invent a date, a holiday date or
a reporting week.

STEP 2. IS THE ARTICLE USEFUL?
An article is useful if it contains at least one CURRENT HUMAN FLU STATEMENT. Otherwise it is not.

A current human flu statement is about flu in people, for a named place or named people, and covers
the article date or a period just before it. It is one of these four types:
 1. People ill with flu: cases, deaths or hospital admissions. One person is enough. The first case or
    first death of the year is this type. A small group counts (two ministers with flu), even when the
    rest of the article is about something else.
 2. The level or direction of flu in a place: rising, falling, peaking, low, high, widespread, an
    epidemic declared, an early or bad season, "no cases yet" at the start of a season.
 3. A flu season that is active now. Counts that ended a few days before the article count when the
    article shows the season is still going (June counts in an article from July 10 that says the
    season starts in July). Counts that ended weeks or months earlier, with nothing showing the season
    is still going, do not.
 4. Suspected flu: suspected cases ("on suspicion", "samples sent"), or flu-like illness (cold, cough,
    fever) for named people or a place when the article names no other cause or test.

These do NOT count as current human flu statements:
 - flu in animals only (poultry, cattle, dogs, horses, cats, wild birds, lab animals)
 - illnesses that are not flu: "stomach flu", norovirus, cat flu, Hib ("haemophilus influenzae"); and
   cold-type illness where the article names another cause or test (dengue, malaria, COVID)
 - flu named only in passing: in a list, a comparison, a metaphor, a nickname ("Spanish flu", "a little
   flu", "Kung flu"), a symptom or remedy, a photo caption, or a business, drug, vaccine-development or
   investment remark
 - prevention only: vaccination, advice, tips, clinics, vaccine coverage
 - forecasts, predictions, preparedness, "the season is coming"
 - the past: a past season or year, the 1918 pandemic, the totals of a closed year, a study of a past
   period, counts that ended months before the article
 - an undated personal story that may be an old event retold
 - a vague outbreak statement ("X is undergoing a severe outbreak") with no cases, no dates and no sign
   that people are ill. It is not useful when no place is named, or when nothing shows the article was
   published during an ongoing flu period. When a place is named AND the article is in an ongoing flu
   period, it is a useful trend item (see Trend items)
An article that has these and also a current statement is still useful; the others are just not recorded.
An article mainly about another disease (COVID-19, RSV, dengue, measles, monkeypox) is useful only if it
contains its own current human flu statement. Using flu as a comparison for that disease is not one.
Never record the other disease's numbers.

BORDERLINE. When a careful reader could go either way, give your best label and set borderline = true
(the "reason" says why). If useful and borderline are both true, still write the items. Typical
borderline cases, each with a plain example:
 - human bird flu as the main story (46 farm workers with H5N1)
 - a single undated case (a toddler in intensive care, no date given)
 - a self-reported case (an official says he has flu, no test mentioned)
 - "this year" with no direction ("this year's flu season is trending higher")
 - a fresh announcement of an old case (an agency reports in June a case whose illness was January to May)
 - a loose term (patients "turning out to be common flu")
 - a prediction that says the season has started ("season officially underway, surge expected in six weeks")
If useful is false, items is an empty list. Still return findings (step 7).

STEP 3. ITEMS (only if useful). One item for each statement about cases, deaths, hospitalizations or the
trend of flu. The kinds are exactly "cases", "deaths", "hospitalized" and "trend"; there is no other kind.
Fields: kind, strain, number, status, total_or_new, city, state, country, start_date, end_date, words,
evidence.
 - strain: as the article words it for THAT item ("swine flu", "H1N1", "bird flu"); null if none.
   Do not correct the article's strain.
 - number: a whole number only if the article gives one. "More than 120" is 120. Never guess. A
   percentage or ratio is never a number. Do not add numbers up.
 - total_or_new: "total" for running totals ("so far", "since", "to date", "year to date", a toll); "new"
   for a newly reported event or number on a date; null if not stated.
 - status: see "Status" below. words: trend items only, see "Trend items" below; null otherwise.

Choosing items and avoiding double counting:
 - One patient or event gives one item. If a person is diagnosed, admitted and dies on the SAME day, keep
   only the most severe (deaths over hospitalized over cases). If they happen on DIFFERENT days, write
   separate items.
 - Never write two items of the same kind that overlap. If a total and its parts are both given (58 in
   the USA, 32 in California, one child), keep only the broader total. Places that are not parts of one
   total are separate items.
 - Deaths: write a deaths item when the article links the death to flu, as confirmed (status
   "confirmed") or as suspected or possible (status "suspected"). If the person's flu is confirmed but
   the cause of death is not known, or the death is "yet to be categorised" as flu, write a cases item
   for the confirmed flu case and no deaths item. If the article does not establish that the person had
   flu, leave the death out. Read the context to decide.
 - "Patients affected" at a hospital is cases, unless the sentence says admitted or hospitalized.
 - People dying or falling ill in a named place with no count is a trend item, not a deaths item with no
   number.
 - Do not record: vaccination figures; age shares; death rates (the share of sick people who die, such as
   "about half of those infected die"); past events the article does not tie to the current one; patient
   details (age, home town, pregnancy); animal outbreaks; forecasts; numbers for other diseases.
 - Roundup and briefing pages: a line printed next to a flu item belongs to it only if it refers to flu
   (same event, same place). Read what the line is about before using it.

Trend items:
 - A trend item says what flu is doing: growth, decline, a stable or low level, or a declared or ongoing
   status. Low activity is a current signal.
 - Fallback to a trend: when the article is useful but a statement cannot be written as a tangible cases,
   deaths or hospitalized item (no count and nothing usable to count), the place is known, and the
   article is published during an ongoing flu period, write it as a trend item instead. Examples: people
   are dying in named places with no count; "the flu season is ongoing". If the place is unknown, or
   nothing shows that the flu period is ongoing, do not write it.
 - A first case or first death of the year that the article states is a cases or deaths item (number 1,
   see step 3), not a trend.
 - words: use the article's own phrase when it has one ("seasonal influenza is increasing statewide",
   "ramping up", "Activity is low", "33 per cent rise", "one of the worst flu seasons in years"). When the
   article describes the trend over several sentences, write a short summary in plain words ("peak season
   is over", "no cases received so far for this flu season", "ongoing flu season", "several students with
   swine flu"). Keep a stated range as written ("eight-10 cases per day"). A summary must not add facts the
   article does not state.
 - A season that the article shows is active at the article date is a trend whose end_date is the article date.

Status:
 - A reported case of a named flu strain ("a case of swine flu", "tested positive for H1N1", "diagnosed")
   is "confirmed" unless the text hints that it is suspected, probable or negative.
 - "Suspected", "on suspicion", "samples sent", "report awaited" is "suspected".
 - Flu-like illness for named people or a place with no other cause or test named may be a cases item with
   status "suspected", strain null, number only if given. If the article names another cause or test
   (dengue, malaria, COVID), do not write it.
 - Deaths: "suspected" or "confirmed" as in the deaths rule above; otherwise null.
 - Trend items and hospitalized items: null unless the article says otherwise.

STEP 4. PLACES.
 - country must be a real country ("USA", "India", "Australia"); state a real state or province; city a
   real city. Anything else is null. Never put "global", "worldwide", "Africa", "Asia", "Europe" or
   "Northern Hemisphere" in a place field; a worldwide or regional statement has no country.
 - A territory uses its sovereign country: Guam and American Samoa are USA; French Polynesia and New
   Caledonia are France; Hong Kong and Macau are China.
 - A county is not a city: use a same-named city only if one exists (Santa Barbara), otherwise null.
 - The city is where the cases or the hospital are, not the patient's home town. A hospital's city or
   suburb counts. A region such as "Central Coast" is not a city.
 - A national agency's statement (the CDC, a ministry of health) gives a country and no state.
 - A place the article does not name may be filled in only when you are certain it is real and follows
   from the places the article names (Kolkata is in West Bengal, India).
 - Whenever a sentence supports a place you give (a headline, a dateline, a sentence naming the region or
   agency), add it to evidence (step 6).

STEP 5. DATES (start_date and end_date, YYYY-MM-DD, start never after end).
 - A single day (an event, a death, "yesterday", "on Tuesday"): start and end are the same day.
 - A newly reported case or event with no time wording: the article date for both.
 - "Today": the article date. "Yesterday": the article date minus 1.
 - "On Tuesday" or "last Tuesday": the most recent Tuesday before the article date. If the article
   states the date of that day, use it.
 - "Last week": the Monday to Sunday week before the article's week.
 - "This week" or "earlier this week" for one event: one day of that week (the Monday), start and end the
   same. "In the last week" or "in the past week" for a count or a rise: the Monday of the article's week
   to the article date. "The week ending <day>" and "week-on-week" in a weekday report: the 7 days ending
   that day. "The past N weeks": the article date minus N weeks, to the article date.
 - "In July": the whole month. "Last month": the whole previous calendar month. "Over the last three
   months": the three full calendar months before the article's month. "The first fortnight of April":
   April 1 to April 14.
 - "Since <date>" and "stats from <date>": start is that date, end is the article date. "As of <date>":
   end is that date, start null (unless the text says "this year").
 - "So far this year", "since January", "year to date": start is January 1 of the article's year, end is
   the article date or the stated update date. "This season", "so far this season": start null, end is
   the article date.
 - "About two weeks back": the article date minus 14 days for both dates.
 - A running total up to a day ("until Wednesday", "as of Oct. 8"): end is that day, start null.
 - A week number ("EpiWeek 18"): only if the article states the calendar range for that week; copy that
   range and add the sentence that gives it to evidence.
 - A forecast is never the period of a count. If you cannot work a date out from the article, use null.

STEP 6. EVIDENCE.
 - evidence is a list of strings, each copied exactly from the article: whole sentences, with typos, odd
   spacing and broken characters as printed.
 - Put the parts in the order they appear in the article. Never join sentences yourself.
 - Add the supporting sentences described in steps 4 and 5 (for a place or for a date that comes from a
   different sentence). Headline and bullet lines printed above the story may be used exactly as printed.

STEP 7. FINDINGS.
If the article states when the flu season starts, ends, how long it lasts, or when it peaks for a place,
return it as a finding with the country and the sentence copied exactly. Do this even when the article is
not useful. A forecast for the current year ("will peak in late August") is not a finding, and neither is
a statement about one past year ("last year it peaked in early December").

STEP 8. SELF-CHECK, then reply with the JSON only. Check that:
 - every evidence part and finding sentence is found word for word in the article
 - the only kinds are cases, deaths, hospitalized, trend, and words is null except on trend items
 - no number comes from a percentage, a forecast, a past year, or another disease
 - no two items of the same kind overlap, and same-day kinds keep only the most severe
 - every place field is a real country, state or city (no regions); territories use their country
 - start_date is not after end_date
 - if useful is false, items is empty
```

---

## 2. Examples (solved articles; the answers are the human labels)

The 43 examples are real rows of `Jahnavi_labels.csv`, with the answers copied from `Jahnavi_items.csv` and
`Jahnavi_findings.csv`; only `reason` was added, to teach the label. They are mixed on purpose: 26
`useful = true` and 17 `useful = false`. Each heading says which rule the example teaches. Long articles
are cut to the paragraphs that carry the evidence (marked "[article trimmed]"); the evidence is still word for
word. No row from the recheck list is used, so none of them is a borderline case; the borderline flag is
explained in step 2 only. Rules that have no clean labeled example yet are listed in section 6.

### Example 1 (teaches: first case of the year; the day named by a weekday)

<example>
Scan date: 2018-07-31
Link: https://timesofindia.indiatimes.com/city/kolkata/health-dept-issues-swine-flu-alert-in-kolkata/articleshow/65213324.cms
Article:
KOLKATA: In the wake of the yearâs first swine flu case, reported by The Times of India on Monday, the health department went into a huddle and sounded an alert. All health officials and hospitals across the city have been asked to look out for 
swine flu symptoms
 in patients and take precautionary measures. Screening will be stepped up, said director of health services Ajay Chakrabarty.
âWe have discussed the situation in todayâs meeting and steps are being taken. A vigil is already on. Now that the first case has been detected, we need to strengthen the vigil. The situation is under control,â said Chakrabarty.
Experts said that since this is the 
swine flu
 season, the first case should be taken seriously. âIn 2016, we have had several deaths. Swine flu or H1N1 is an air-borne infection which spreads fast and easily. In a crowded city like Kolkata, number of cases could multiply in a matter of days,â warned AMRI Hospital consultant Debashish Saha.
He added that crowded places like schools, colleges, auditoria, public transport and shopping malls were likely places where the virus could spread. âChildren should be made to wear masks to schools. You canât avoid every public place so itâs necessary to be cautious,â said Saha.
The state had 130 swine flu cases in 2009 during a major outbreak around the country. More than 10 cases were reported in 2015. More than a hundred cases were reported from Bengal last year.
Masks were not a fool-proof protection unless it was a M95 mask, pointed out consultant Arindam Biswas. âSince swine flu is a droplet infection, itâs difficult to contain. So, diagnosis should happen and treatment begin as early as possible,â said Biswas.
While some Saha felt that preventive treatment may begin even before diagnosis, Biswas differed. âThe principal drug for swine flu is Tamiflu and it should be used only after conformation of the virusâ presence,â said Biswas. Saha, on the other hand, pointed out that those who have had exposure to swine flu patients need to be careful.

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "First swine flu case of the year reported in Kolkata two days before the article.",
  "items": [
    {"kind": "cases", "strain": "swine flu", "number": 1, "status": "confirmed", "total_or_new": "new", "city": "Kolkata", "state": "West Bengal", "country": "India", "start_date": "2018-07-30", "end_date": "2018-07-30", "words": null, "evidence": ["KOLKATA: In the wake of the yearâs first swine flu case, reported by The Times of India on Monday"]}
  ],
  "findings": []
}
</example>

### Example 2 (teaches: not useful: vaccination advice only)

<example>
Scan date: 2016-12-22
Link: http://www.hngnews.com/cambridge_deerfield/article_fcdfa654-c7b4-11e6-ac8e-fb6a0d37fa3f.html
Article:
This year, as we embark on holiday trips to see our parents and grandparents, I’d like to offer a thought. If your loved ones are over 65, please take a moment to really check on them while you’re there.
How are they doing? Are they keeping physically active and getting around OK? Is their hygiene good, home winterized and warm, refrigerator stocked, prescriptions well-marked and being taken? How is their memory? Note everything you see and hear and if something seems amiss, ask them about it. If there’s a concern, gently encourage them to get help, see a doctor, or help them yourself if that works better. Wisconsin’s aging and disability resource centers can also be an excellent resource, along with non-profit organizations that deal with issues like mental health and Alzheimer’s and dementia.
Are their vaccinations current? Two vaccine preventable diseases common to seniors in winter months are the flu and pneumonia. The flu is tough to shake once contracted and pre-existing conditions like chronic obstructive pulmonary disease, asthma, congestive heart failure and diabetes put seniors at higher risk of pneumonia. Sadly, more than half of Wisconsinites 65+ skip these vaccinations. Getting our loved ones immunized can make a difference.
I realize these aren’t typical gifts found under a tree, but given with love and care, they may just help ensure many more holidays to come.
Rob Gundermann
Madison, WI

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "Letter about vaccinating seniors; no current flu activity.",
  "items": [],
  "findings": []
}
</example>

### Example 3 (teaches: active season: last month, a count plus an ongoing trend; a finding)

<example>
Scan date: 2017-07-10
Link: http://www.dailytelegraph.com.au/newslocal/central-coast/not-too-late-to-get-flu-jab-as-dreaded-lurgy-hits-coast/news-story/b030052216f2a3d72c63756ba805eaa9?nk=40b9f54b6d576106c1e509e5589b9808-1499673010
Article:
Not too late to get flu jab as dreaded lurgy hits Coast
THIS winter is shaping up as one of the worst flu seasons in years with five and a half times the number of confirmed cases last month than the same period last year.
While the traditional “flu season” usually kicks off in July, Central Coast Local Area Health has already recorded 88 flu cases last month compared to 16 in June, 2016.
But experts have urged it is not too late to get vaccinated against the dreaded lurgy even if people have already been battling sore throats and runny noses.
New studies suggest the flu shot can modify and lesson symptoms in people already suffering influenza and better protect themselves from the highly contagious respiratory illnesses caused by viruses.
District Director of Public Health Dr Peter Lewis said with the flu vaccine taking about two weeks to become effective, there was still time to get the flu jab.
“For people who are susceptible to the flu — such as those with a chronic medical condition like asthma — the yearly seasonal influenza vaccination is the best way to protect against flu,” Dr Lewis said.
“Influenza is a vaccine-preventable illness but a new vaccine needs to be given each year because influenza viruses change or mutate constantly.
“Influenza makes people quite unwell, and is different to a severe cold which people often mistakenly call the flu.
“The influenza virus causes fever, chills, headache, dry cough, weakness and aching limbs.
“The fever usually passes in a few days, but the feeling of weakness and the cough can last for a week or more.”
With numbers increasing last month, the local health district is anticipating a rise in flu cases over the next four to six weeks.
Dr Lewis said despite the common misconception, the flu shot cannot cause flu illness.
“Flu vaccines used in Australia are made with vaccine viruses that have been ‘inactivated’ so they are not infectious,” he said.
Free flu jabs are available for all people aged 65 years and over, Aboriginal and Torres Strait Islander children aged up to five years and over 15, and pregnant women.
Free flu shots are also available to people with certain chronic medical conditions such as asthma, diabetes or heart disease.
Well known Kincumber GP Dr Ian Charlton said influenza was diagnosed with blood tests and or a nasal swab with most conditions turning out to be common colds.
He said when people contracted influenza it felt “88-times worse than any cold they’ve ever had before”.
Dr Charlton said new studies suggested “even if you’ve got the flu, the flu shot can go a long way to modifying the symptoms”.
CENTRAL COAST HEALTH’S TIPS TO AVOID THE FLU
• Get the flu vaccine
• Avoid people you know are sick with flu
• Avoid crowded places where there may be other people sick with flu
• If you have the symptoms, don’t visit vulnerable people or aged care facilities. Cover your mouth when coughing or sneezing, use disposable tissues, and dispose of tissues immediately after use.
• Wash your hands regularly, especially after coughing, sneezing or blowing your nose.

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "June cases and an ongoing bad season, published ten days after the month ended; the article says the season starts in July, so the season is active.",
  "items": [
    {"kind": "cases", "strain": null, "number": 88, "status": "confirmed", "total_or_new": "total", "city": null, "state": "New South Wales", "country": "Australia", "start_date": "2017-06-01", "end_date": "2017-06-30", "words": null, "evidence": ["While the traditional “flu season” usually kicks off in July, Central Coast Local Area Health has already recorded 88 flu cases last month compared to 16 in June, 2016."]},
    {"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null, "city": null, "state": "New South Wales", "country": "Australia", "start_date": "2017-06-01", "end_date": "2017-07-10", "words": "one of the worst flu seasons in years", "evidence": ["THIS winter is shaping up as one of the worst flu seasons in years with five and a half times the number of confirmed cases last month than the same period last year.", "“Flu vaccines used in Australia are made with vaccine viruses that have been ‘inactivated’ so they are not infectious,” he said."]}
  ],
  "findings": [
    {"country": "Australia", "finding": "While the traditional “flu season” usually kicks off in July"}
  ]
}
</example>

### Example 4 (teaches: a named death with a stated day)

<example>
Scan date: 2017-12-04
Link: https://www.buzzfeed.com/carolinekee/arizona-woman-dies-from-flu-day-after-diagnosis
Article:
Alani "Joie" Murrieta, a 20-year-old mother of two from Phoenix, Arizona, died last Tuesday — only one day after being diagnosed with the flu.
Murrieta is remembered as a proud mother, a hard worker, and an amazing friend. "She did everything she could for her two boys — she was the best mother to them," her aunt Stephanie Gonzales told BuzzFeed News. Murrieta was also described by her family as being healthy and having no preexisting health conditions.
several minutes passed and they told us there was nothing they could do," Gonzales says. Murrieta arrived at the hospital around 7 a.m. and was declared dead at 3:25 p.m. on Tuesday, Nov. 28, 2017.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "A named woman died of flu on a stated day in Phoenix.",
  "items": [
    {"kind": "deaths", "strain": null, "number": 1, "status": null, "total_or_new": "new", "city": "Phoenix", "state": "Arizona", "country": "USA", "start_date": "2017-11-28", "end_date": "2017-11-28", "words": null, "evidence": ["Alani \"Joie\" Murrieta, a 20-year-old mother of two from Phoenix, Arizona, died last Tuesday — only one day after being diagnosed with the flu.", "Murrieta arrived at the hospital around 7 a.m. and was declared dead at 3:25 p.m. on Tuesday, Nov. 28, 2017."]}
  ],
  "findings": []
}
</example>

### Example 5 (teaches: not useful: animal-only flu)

<example>
Scan date: 2023-01-13
Link: https://www.thehindu.com/news/national/kerala/bird-flu-confirmed-at-punnapra/article66374358.ece
Article:
Bird flu has been confirmed at one more place in Alappuzha. Officials of the Animal Husbandry Department (AHD) on Friday said the disease had been detected in chickens at a poultry farm in Punnapra.
“The Centre has not yet notified the outbreak of bird flu in Punnapra. Once the notification comes, rapid response teams of the AHD will cull all domesticated birds within a 1-km radius of the hotspot. The bird culling operation is likely to be held on Monday. The farm was housing over 1,000 birds and less than 100 remain there on Friday as the rest perished to the disease in recent days,” said an AHD official.
Following the mass death of ducks at the farm, the AHD sent samples of dead birds to the National Institute of High-Security Animal Diseases (NIHSAD), Bhopal, for analyses, which tested positive for avian influenza.
Published - January 13, 2023 07:21 pm IST

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "Bird flu in poultry only; no human cases.",
  "items": [],
  "findings": []
}
</example>

### Example 6 (teaches: season starting with no cases yet (trend in summary words); suspected patients)

<example>
Scan date: 2016-12-18
Link: http://www.hindustantimes.com/delhi/delhi-hospitals-gear-up-as-swine-flu-season-arrives/story-5JhRMG5eFwP0piZV1QygdP.html
Article:
Delhi hospitals gear up as swine flu season arrives
All the major hospitals of the city, however, on Saturday said they had not received any swine flu cases so far.
With temperatures dipping, hospitals across the Capital have begun preparing for treating swine flu patients.
All the major hospitals of the city, however, on Saturday said they had not received any swine flu cases so far.
“Usually, we start getting swine flu cases by this time of the year. However, we have not received a single case yet, which is a good sign, given that dengue and chikungunya affected so many people,” said Dr JC Passi, medical director of Lok Nayak hospital.
The hospital has a dedicated 80-bed ward, which can be used for isolating patients suffering from swine flu in case there is an outbreak.
At Safdarjung hospital, two patients were kept in isolation on suspicion that they had swine flu. “There are a number of seasonal flu cases that mimic the symptoms of swine flu. So, we have to be careful. But, to my knowledge, neither of the two patients have tested positive for swine flu,” said Dr AK Rai, medical superintendant of Safdarjung hospital.
At Baba Saheb Ambedkar hospital, the administration has alerted doctors and staff to the possibility of receiving swine flu cases, demarcated a ward for taking in swine flu patients and taken stock of supplies like masks, personal protective equipment and oseltamivir, an antiviral medication prescribed for swine flu.
Dr Suranjit Chatterjee, senior consultant of internal medicine at Indraprastha Apollo, said: “This is the season for swine flu. There is an increase in the seasonal influenza due to change in temperature. But, unlike the first time that swine flu came to Delhi, now we are prepared and now how to deal with it.”

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "Delhi hospitals prepare as the swine flu season begins: none has a confirmed case yet and two patients are isolated on suspicion.",
  "items": [
    {"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null, "city": "Delhi", "state": "Delhi", "country": "India", "start_date": null, "end_date": "2016-12-17", "words": "no cases received so far for this flu season", "evidence": ["Delhi hospitals gear up as swine flu season arrives\nAll the major hospitals of the city, however, on Saturday said they had not received any swine flu cases so far."]},
    {"kind": "hospitalized", "strain": "swine flu", "number": 2, "status": "suspected", "total_or_new": "new", "city": "Delhi", "state": "Delhi", "country": "India", "start_date": "2016-12-18", "end_date": "2016-12-18", "words": null, "evidence": ["At Safdarjung hospital, two patients were kept in isolation on suspicion that they had swine flu."]}
  ],
  "findings": []
}
</example>

### Example 7 (teaches: not useful: cold-type illness with other causes named)

<example>
Scan date: 2022-12-23
Link: https://www.thehindu.com/news/cities/Mangalore/jamboree-children-report-cold-cough-and-fever/article66298057.ece
Article:
Second PU student Darshan, who is part of the scouts and guides team from Shivamogga, had to take care of a class 6 student of his team till 4 a.m in Alva’s hospital following a bout of cold, cough, and fever.
“As the teammate did not like the food offered to him, he had not eaten anything since Wednesday. He had throat infection that led to cold, cough, and fever. Following treatment in the hospital, the child has been moved to the hostel where he is taking rest,” Mr. Darshan said.
The class 6 student from Shivamogga is among many children attending the Scouts and Guides International Cultural Jamboree who have reported cold, cough, and fever at the Alva’s Health Centre and the hospital. “Some have got this as they have not eaten food that is different from the one that they regularly eat. Difference in the climate condition from their native places and the one in Moodbidiri has also resulted in infection. This is common infection among children and it’s being treated effectively,“ D.V. Chirag, the nodal officer of the health centre on Alva’s College campus, told The Hindu.
Dr. Chirag said there were some cases of infection among a few participants following eating food outside the jamboree area. There were also a few who got injured during the activity session, he said.
District Reproductive Child Health Officer B.V. Rajesh, who is overseeing arrangements at the jamboree, said a team of 14 members comprising medical officers, health inspectors, ASHA workers and pharmacist, are deputed every day at the health centre on the campus. Three specialists and personnel from Rashtriya Bala Swasthya Karyakram have also been deputed. Four ambulances have been made available for the health centre.
Dr. Rajesh said 10 beds each are available at the emergency section and observation room at the health centre. Those requiring additional care are being referred to Alva’s Hospital, G.V. Pai Hospital and Moodbidri Community Health Centre. Food provided to the participants and to general public at 20 different points were tested regularly.
Dr. Rajesh said most of the medicines are being provided by the State government. Health staff are testing infected patients for dengue and malaria. Those having symptoms of influenza like illness and severe acute respiratory infection will be tested for COVID, he said.
Published - December 23, 2022 09:02 pm IST

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "Children have cold, cough and fever, but the article names other causes and tests (dengue, malaria, COVID); flu is not named as the cause.",
  "items": [],
  "findings": []
}
</example>

### Example 8 (teaches: earlier this week; about two weeks back; an outbreak trend)

<example>
Scan date: 2023-02-04
Link: https://timesofindia.indiatimes.com/city/vadodara/swine-flu-scare-at-godhra-medical-college/articleshow/97593955.cms
Article:
VADODARA: Several students at the Godhra GMERS Medical College were advised to rest and some were also allowed to go home after 
swine flu
 cases were reported among them.
According to sources, the first case of swine flu was reported about two weeks back in the college. It came to light later that several other students complained of cough and cold. Those having serious symptoms similar to flu were either advised to take rest in their hostel rooms or allowed to go home.
Cases of respiratory infections kept trickling in on the campus among students even later.
One more student tested positive earlier this week even as others were found suspicious along with this student too.
Around a dozen students with upper respiratory tract infections have been examined after the second case was reported on the campus. However, no fresh positive cases have come to light so far. Some students are running high fever and are being treated in a private hospital.

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "Swine flu cases among students at one college in the two weeks before the article.",
  "items": [
    {"kind": "cases", "strain": "swine flu", "number": 1, "status": "confirmed", "total_or_new": "new", "city": "Godhra", "state": "Gujarat", "country": "India", "start_date": "2023-01-21", "end_date": "2023-01-21", "words": null, "evidence": ["Several students at the Godhra GMERS Medical College were advised to rest and some were also allowed to go home after swine flu cases were reported among them.", "According to sources, the first case of swine flu was reported about two weeks back in the college."]},
    {"kind": "cases", "strain": "swine flu", "number": 1, "status": "confirmed", "total_or_new": "new", "city": "Godhra", "state": "Gujarat", "country": "India", "start_date": "2023-01-30", "end_date": "2023-01-30", "words": null, "evidence": ["Several students at the Godhra GMERS Medical College were advised to rest and some were also allowed to go home after swine flu cases were reported among them.", "One more student tested positive earlier this week even as others were found suspicious along with this student too."]},
    {"kind": "trend", "strain": "swine flu", "number": null, "status": null, "total_or_new": null, "city": "Godhra", "state": "Gujarat", "country": "India", "start_date": "2023-01-21", "end_date": "2023-02-04", "words": "several students with swine flu", "evidence": ["Several students at the Godhra GMERS Medical College were advised to rest and some were also allowed to go home after swine flu cases were reported among them."]}
  ],
  "findings": []
}
</example>

### Example 9 (teaches: last three months; trend words in summary; a finding)

<example>
Scan date: 2016-01-29
Link: http://beyazgazete.com/haber/2016/1/29/turkey-aciklamasi-57-people-died-from-swine-flu-in-3-months-3090462.html
Article:
Turkey Açıklaması 57 People Died From Swine Flu İn 3 Months
Turkey's top health official says peak season of flu over.
Ekleme: 29.01.2016 - 02:13
Güncelleme: 29.01.2016 - 02:13 / Editör: AA
/ Kaynak: AA
At least 57 people have died from H1N1 -- so-called “swine flu” -- in Turkey over the last three months, Turkey’s health minister said on Thursday.
“We have collected a total of 480 samples from patients, out of which 280 were cases of H1N1,” Health Minister Mehmet Muezzinoglu told an Ankara meeting about Turkey's health vision and future projections.
The minister said that the transmission of the virus in November and the early December was slow. 'The virus peaked in late December and early January, but the peak season of the flu is over,' Muezzinoglu said.
Authorities define the flu season as spanning the period from October to April.
The minister said that the government had taken all necessary measures to deal with the situation and there was no need to panic. 'Hand hygiene is vital for preventing the virus from spreading. Healthy nutrition as well as drinking more water is also important,' the minister said.
Swine flu was first reported in Turkey in 2009. The flu had killed over 30 people in the country in 2014-2015 flu season.
Mezzinoglu also assured that no Zika virus has been recorded in Turkey so far.
Originating in Latin America, the mosquito-borne virus causes symptoms in roughly one in five adults, including fever, rash and conjunctivitis.
There is currently no vaccine or cure for the virus, which has spread to 21 countries and territories in the Americas, according to the Pan American Health Organization.
The virus is expected to spread to every country where Aedes mosquitoes are known to live, according to the organization.
The World Health Organization predicted on Thursday that the virus could be contracted by as many as four million people over the next 12 months.

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "Turkey reports 57 swine flu deaths in three months and the health minister says the peak season is over.",
  "items": [
    {"kind": "deaths", "strain": "H1N1", "number": 57, "status": null, "total_or_new": "total", "city": null, "state": null, "country": "Turkey", "start_date": "2015-10-01", "end_date": "2015-12-31", "words": null, "evidence": ["At least 57 people have died from H1N1 -- so-called “swine flu” -- in Turkey over the last three months, Turkey’s health minister said on Thursday."]},
    {"kind": "trend", "strain": "H1N1", "number": null, "status": null, "total_or_new": null, "city": null, "state": null, "country": "Turkey", "start_date": "2015-11-01", "end_date": "2015-12-10", "words": "slow", "evidence": ["The minister said that the transmission of the virus in November and the early December was slow. 'The virus peaked in late December and early January, but the peak season of the flu is over,' Muezzinoglu said.", "Turkey's top health official says peak season of flu over."]},
    {"kind": "trend", "strain": "H1N1", "number": null, "status": null, "total_or_new": null, "city": null, "state": null, "country": "Turkey", "start_date": "2015-12-21", "end_date": "2016-01-10", "words": "peaked", "evidence": ["The minister said that the transmission of the virus in November and the early December was slow. 'The virus peaked in late December and early January, but the peak season of the flu is over,' Muezzinoglu said.", "Turkey's top health official says peak season of flu over."]},
    {"kind": "trend", "strain": "H1N1", "number": null, "status": null, "total_or_new": null, "city": null, "state": null, "country": "Turkey", "start_date": "2016-01-28", "end_date": "2016-01-28", "words": "peak season is over", "evidence": ["The minister said that the transmission of the virus in November and the early December was slow. 'The virus peaked in late December and early January, but the peak season of the flu is over,' Muezzinoglu said.", "Turkey's top health official says peak season of flu over."]}
  ],
  "findings": [
    {"country": "Turkey", "finding": "Authorities define the flu season as spanning the period from October to April."}
  ]
}
</example>

### Example 10 (teaches: not useful: flu only as a comparison)

<example>
Scan date: 2022-05-31
Link: https://www.chemistryworld.com/news/what-is-the-future-of-covid-19-pharmaceuticals/4015690.article
Article:
Firms anticipate long-term markets for prevention and treatment
Sars-CoV-2 continues to infect millions of people worldwide and cause an estimated 10,000 deaths per day, as the US alone approaches one million dead. It is widely expected to become endemic, remaining in circulation for the foreseeable future, and continuing to cause substantial numbers of hospitalisations and deaths, especially among vulnerable groups. ‘Covid kills about tenfold more people than flu, based on historical information,’ says Penny Ward, professor of pharmaceutical medicine at King’s College London, UK.

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "Flu appears only as a historical comparison with COVID-19 deaths.",
  "items": [],
  "findings": []
}
</example>

### Example 11 (teaches: a territory gives its country; epidemic declared; a finding)

<example>
Scan date: 2017-09-21
Link: http://www.guampdn.com/story/news/2017/09/21/flu-epidemic-hits-guam-says-public-health-agency/687997001/
Article:
If you're aching, coughing, running a fever and shaking from chills, you aren't alone — the Department of Public Health announced the onset of a Type A influenza epidemic on the island.
The determination was made "based on the most recent available data from cooperating medical laboratories," Public Health said in a press release Thursday. "This is not entirely unexpected as Guam frequently experiences an increase of influenza illnesses soon after the start of each new school year."
The flu is very contagious and can be very serious, even deadly, especially for people who have chronic illnesses. The flu is caused by viruses that infect the nose, throat and lungs.
Symptoms include fever and chills, coughing, runny or stuffy nose, muscle or body aches, headaches and feeling very tired. Children may experience vomiting and diarrhea, according to Public Health.
To protect yourself from the flu, get a vaccine each year, especially if you are in a high-risk group. People who are more vulnerable for serious flu complications include children under 2, adults 65 and older, pregnant women, cancer patients, people with diabetes, asthma, chronic lung disease, heart disease or kidney or liver disorders. People with weakened immune systems or those living in long-term care facilities are also at risk.
You can also avoid the flu by staying away from people who are sick, washing hands frequently, and using your elbow area to block coughs. If you are sick, stay home from work or school.
For more information about the flu, speak with your primary health care provider or visit www.cdc.gov/flu, or call the DPHSS Immunization Program at 735-7143.
This article originally appeared on Pacific Daily News: Flu epidemic hits Guam, Public Health says

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "Guam, a US territory, has a Type A influenza epidemic declared today; the article also says when Guam usually sees flu rise.",
  "items": [
    {"kind": "trend", "strain": "Type A influenza", "number": null, "status": null, "total_or_new": null, "city": null, "state": null, "country": "USA", "start_date": "2017-09-21", "end_date": "2017-09-21", "words": "onset of a Type A influenza epidemic", "evidence": ["If you're aching, coughing, running a fever and shaking from chills, you aren't alone — the Department of Public Health announced the onset of a Type A influenza epidemic on the island.", "\"This is not entirely unexpected as Guam frequently experiences an increase of influenza illnesses soon after the start of each new school year."]}
  ],
  "findings": [
    {"country": "USA", "finding": "This is not entirely unexpected as Guam frequently experiences an increase of influenza illnesses soon after the start of each new school year."}
  ]
}
</example>

### Example 12 (teaches: not useful: counts ended months before the article)

<example>
Scan date: 2015-08-03
Link: http://indianexpress.com/article/cities/delhi/swine-flu-patients-spent-17-62-times-per-capita-income-on-treatment-study/
Article:
Swine flu patients spent 17-62 times per capita income on treatment: Study
The hospital stay of the patients ranged from a day to 41 days. On an average, a patient spent 7.69 days at the hospital.
Swine flu patients spent 17-62 times the per capita income of the country on treatment at a private hospital in the city this year, a study published in the journal, Current Medicine Research and Practice, says.
The study covered 209 H1N1 patients admitted at Sir Ganga Ram Hospital between January and March. It found that patients who shared wards, on an average, spent Rs 1,25,429 on cure, or 17 times India’s per capita income at Rs 7,378.17.
The cost of cure for patients kept in single rooms was, on an average, Rs 1,62,320, or 22 times the per capita income. Patients admitted in the intensive care unit (ICU), on an average, spent Rs 4,57,447 on cure, or 62 times the per capita income.
[related-post]
“The socio-economic effects of the outbreak of H1N1 have not been understood properly. We attempted to calculate the economic burden of the virus over a three-month period for the first time,” said Dr Atul Kakar, lead author of the study and senior consultant at the hospital’s department of medicine.
The study notes that the socio-economic cost could be more as the authors had not factored in the loss of productivity resulting from a patient staying away from office or school.
The study says 52.9 per cent of the patients had one or more co-existing medical conditions. Hypertension and diabetes were found in 23 per cent and 22.5 per cent of the patients, respectively.
The hospital stay of the patients ranged from a day to 41 days. On an average, a patient spent 7.69 days at the hospital.

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "The 209 hospitalized patients were counted January to March; the article is from August and is about treatment costs.",
  "items": [],
  "findings": []
}
</example>

### Example 13 (teaches: a toll up to a day; "more than" a number; an undated article)

<example>
Scan date: 2021-08-18
Link: https://eturbonews.com/109276/70-year-old-swiss-tourist-dies-swine-flu-india/
Article:
JODHPUR, India – A 70-year-old foreign tourist has died of swine flu in Jodhpur as the toll in Rajasthan has gone up to more than 120. The Swiss tourist, Anne Marie, was taken ill while she was visiting Jaisalmer where she was treated at a private hospital.
When her condition deteriorated as she suffered from acute pneumonia, Anne Marie was shifted to MDM Hospital, Jodhpur, on Wednesday. She was put on the ventilator but died on Wednesday morning. Her blood test report, which came after her death, confirmed she was suffering from H1N1 influenza.
Describing swine flu as an ‘epidemic’, Chief Minister Vasundhara Raje has asked the tourists to take medical help at the earliest if they suffered from symptoms like fever, cough and breathlessness. Speaking to a television channel, Ms. Raje said patients often went to hospitals in the last stages. “We have set up a task force and are providing diagnostic services and medicines free of cost in hospitals,” she said.
This being the peak tourist season, the government has also decided to distribute pamphlets at airports and railway stations to warn foreign visitors about the spread of swine flu and what measures to take. Masks will be provided to all patients who visit the swine flu treatment centres to prevent the infection from spreading, Ashok Panagariya, chairperson of the State Task Force on swine flu said.
The government has set up isolation wards for swine flu patients and provided ventilators for the critical ones. Leave of all doctors has been cancelled and Assembly meetings have been done away with.

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "A tourist died on a Wednesday and the state toll is above 120.",
  "items": [
    {"kind": "deaths", "strain": "swine flu", "number": 1, "status": "confirmed", "total_or_new": "new", "city": "Jodhpur", "state": "Rajasthan", "country": "India", "start_date": "2021-08-18", "end_date": "2021-08-18", "words": null, "evidence": ["JODHPUR, India – A 70-year-old foreign tourist has died of swine flu in Jodhpur as the toll in Rajasthan has gone up to more than 120.", "She was put on the ventilator but died on Wednesday morning."]},
    {"kind": "deaths", "strain": "swine flu", "number": 120, "status": "confirmed", "total_or_new": "total", "city": null, "state": "Rajasthan", "country": "India", "start_date": null, "end_date": "2021-08-18", "words": null, "evidence": ["JODHPUR, India – A 70-year-old foreign tourist has died of swine flu in Jodhpur as the toll in Rajasthan has gone up to more than 120."]}
  ],
  "findings": []
}
</example>

### Example 14 (teaches: a small group in an article about another disease)

<example>
Scan date: 2022-08-01
Link: https://bangaloremirror.indiatimes.com/bangalore/others/experts-trace-monkeypox-cases-in-india-to-us-and-thailand/articleshow/93261110.cms
Article:
Experts trace monkeypox cases in India to US and Thailand
.
Meanwhile, Minister for Cooperation ST Somashekar and Minister for Municipal Administration N Nagaraju have been down with an illness.
Sudhakar clarified, “Both the ministers are having symptomatic flu . Both have undergone Covid tests and both of them are negative. They are doing fine and are being treated for flu.”
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "The article is about monkeypox, but it states that two named ministers currently have flu.",
  "items": [
    {"kind": "cases", "strain": null, "number": 2, "status": "confirmed", "total_or_new": "new", "city": null, "state": "Karnataka", "country": "India", "start_date": "2022-08-01", "end_date": "2022-08-01", "words": null, "evidence": ["Meanwhile, Minister for Cooperation ST Somashekar and Minister for Municipal Administration N Nagaraju have been down with an illness.", "Sudhakar clarified, “Both the ministers are having symptomatic flu . Both have undergone Covid tests and both of them are negative. They are doing fine and are being treated for flu.”"]}
  ],
  "findings": []
}
</example>

### Example 15 (teaches: not useful: a vaccine launch; Hib is not flu)

<example>
Scan date: 2016-11-24
Link: http://www.business-standard.com/article/pti-stories/sanofi-pasteur-launches-6-in-1-paediatric-vaccine-in-india-116112400420_1.html
Article:
Sanofi Pasteur launches 6-in-1 paediatric vaccine in India
Sanofi Pasteur today announced the launch of paediatric 6-in-1 vaccine, Hexaxim, which provides protection against six major childhood diseases in India.
The ready-to-use fully liquid vaccine provides protection against diphtheria, tetanus, pertussis (whooping cough), polio, haemophilus influenza B and hepatitis B, Sanofi Pasteur said in a statement.
It is indicated for primary and booster vaccination of infants and toddlers from six weeks to 24 months of age, it added.
Also Read
Sanofi Pasteur India, Nepal and Sri Lanka Country Head Jean-Pierre Baylet said, "Hexaxim brings to life Sanofi Pasteur's mission to improve human health by developing superior innovative vaccination solutions against infectious diseases."
"Given the large influx of patients met by pediatricians in India, Hexaxim will offer convenience and ensure consistency in administering the right dose of each antigen every single time," he added.
Hexaxim, during its clinical study assessment, was found to be safe and well tolerated as a primary series and booster vaccination in all schedules, countries, and ethnicities tested, Sanofi Pasteur said.
Each dose of Hexaxim takes 24 to 36 months for manufacturing, of which 70 per cent of the time is spent on quality tests, it added.
Sanofi Pasteur is the vaccines global business unit of pharma major Sanofi.
Disclaimer: No Business Standard Journalist was involved in creation of this content
More From This Section
First Published: Nov 24 2016 | 2:07 PM IST

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "A vaccine product launch; \"haemophilus influenza B\" is a bacterium in a childhood vaccine, not flu.",
  "items": [],
  "findings": []
}
</example>

### Example 16 (teaches: human bird flu deaths; Hong Kong counted under China)

<example>
Scan date: 2016-12-31
Link: http://www.gdnonline.com/Details/152092
Article:
Chicago: U.S. officials are urgently seeking an agreement with South Korea that would allow imports of American eggs so farmers can cash in on a shortage caused by the Asian country's worst-ever outbreak of bird flu.
The two sides are negotiating over terms of potential shipments after South Korea lifted a ban on imports of U.S. table eggs that it imposed when the United States grappled with its own bout of bird flu last year, according to the U.S. Department of Agriculture.
If an agreement is reached, U.S. shipments could bring some relief to South Koreans who have faced soaring egg prices and rationing since the outbreak there began last month.
The egg shipments also would help U.S. farmers cope with an oversupply that is depressing prices.
The opportunity to profit by filling South Korea's shortfall with U.S. eggs has sent brokers and traders into overdrive.
About 26 million birds, more than a quarter of South Korea's poultry stock, have been culled to control the outbreak, and most of the birds have been egg-laying hens.
Strains of bird flu, which can be spread to poultry by wild birds, have been detected across Asia and in Europe in recent weeks. Two people in China and one person in Hong Kong have died in the outbreaks.
The United States could reach agreement to open trade with South Korea as early as next week, said Mark Perigen, national supervisor for shell eggs for a division of the USDA.
"Everybody's working hard to get it done," Perigen said in an interview on Friday, adding that USDA employees had worked during holiday vacations on the issue.
"They're desperate for eggs over there, and the government realizes that," Perigen said.
South Korea's embassy in Washington did not immediately respond to a phone message seeking comment.
Glenn Hickman, chief executive of Hickman's Eggs in Arizona, has received calls from brokers searching for U.S. eggs to ship to South Korea.
"Everybody in Korea who needs eggs has Googled everybody in the world who might have eggs," Hickman said.
"We're getting calls from brokers who have no idea even the right questions to ask us," he added. "It's just somebody who knows how to freight stuff from the U.S. to Korea."
With no agreement yet between the two countries, Hickman is asking employees to take contact information for the potential customers.
United States Egg Marketers, a cooperative of farmers that was established to export eggs, has received "numerous inquiries about this already, including from people who have never exported anything in their lives," said Eka Inall, the group's president.
"Our phone is blowing up, our email is blowing up," she said.
Last year, U.S. food companies imported eggs from Europe after bird flu ravaged domestic chicken flocks and sent egg prices to record highs.
Since then, U.S. prices have tumbled as farmers have ramped up production.
The United States produced 7.44 billion table eggs in November, up 11.5 percent from a year earlier, and there were 312 million hens laying table eggs on Dec. 1, up 8 percent from a year before, according to USDA.
On Dec. 26, the average price for a dozen large white U.S. eggs was $1.17, down from a high of $2.88 in August 2015, according to market data firm Urner Barry.
"Current conditions in the U.S. are definitely a motivating factor to get this thing done," Brian Moscogiuri, an Urner Barry egg analyst, said about U.S. efforts to start shipments to South Korea.
If South Korea begins importing U.S. eggs, its residents may need to adjust to a different appearance of the food staple.
Jim Sumner, president of the U.S. Poultry and Egg Export Council, said many Koreans prefer brown colored eggs, while the United States mostly produces white eggs.
"As they say, beggars can't be choosers," he said.

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "Human bird flu deaths are reported in recent weeks, inside a story about egg exports.",
  "items": [
    {"kind": "deaths", "strain": "bird flu", "number": 3, "status": "confirmed", "total_or_new": "total", "city": null, "state": null, "country": "China", "start_date": null, "end_date": "2016-12-31", "words": null, "evidence": ["Strains of bird flu, which can be spread to poultry by wild birds, have been detected across Asia and in Europe in recent weeks. Two people in China and one person in Hong Kong have died in the outbreaks."]}
  ],
  "findings": []
}
</example>

### Example 17 (teaches: not useful: totals of a closed year)

<example>
Scan date: 2016-01-05
Link: http://timesofindia.indiatimes.com/city/ahmedabad/In-2015-city-saw-65-rise-in-fever-related-emergencies/articleshow/50449784.cms
Article:
AHMEDABAD: Last year, the city alone reported record 2,200 cases of swine flu, 1,700 cases of dengue and over 8,200 cases of malaria. The disease out breaks took the number of emergencies related to fevers in city and periphery to 7,945.
 EMRI 108 services recorded 65.38% rise in this category in 2015 as compared to 2014 the highest for any emergencies.
Ahmedabad city and district recorded 20.85% rise in emergencies where primary causes were abdominal pain, respiratory problems, road accidents and other trauma. The percentage rise was higher than overall emergencies in Gujarat that recorded 13.04% rise.
 Critical care specialist Dr Pratibha Dileep said hat year 2015 saw a significantly high number of dengue fever emergencies as city reported a viral outbreak. There were also unidentified viral fevers which were not H1N1, dengue, leptospirosis, etc. but gave high morbidity . 
 âWe saw many cases of unidentified viral fevers which could not be diagnosed but gave critical sickness including atypical pneumonia and acute respiratory distress. There were also cases wherein person was extremely unwell with viral hepatitis but did not test positive for Hepatitis A, B, C or E,â said Dr Dileep. 
 EMRI officials said that the outbreaks were the primary reason for the rise. â A number of citizens were not in favour of taking risks while they saw symptoms for the diseases,â said an official.
 Jashvant Prajapati, chief operating officer of GVK EMRI in Gujarat, said: âPregnancy-related emergencies top the chart as it is on 108's agenda to promote institutional delivery in places not well connected to medical facilities. The other major cause for emergencies are road accidents. On an average we have to cater to 15 road accidents every hour,â he said. 
 EMRI officials said that in 2015 108 services set a new record of attending 3,814 emergencies in a single day on November 12. The number of diabetics attended by paramedics across Gujarat also jumped from 5,452 emergencies in 2014, to 7,029 in 2015. In Ahmedabad, the figures were 1,397 in 2014 and 1,824 n 2015.

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "The 2,200 swine flu cases are the whole of 2015 in Ahmedabad, in an article published on January 5, 2016; a summary of a closed year.",
  "items": [],
  "findings": []
}
</example>

### Example 18 (teaches: a statewide trend stated today)

<example>
Scan date: 2018-12-07
Link: https://katu.com/news/local/oregon-schools-reporting-increase-in-student-flu-cases
Article:
Oregon schools reporting increase in flu cases, but numbers still low statewide
OREGON CITY, Ore. — Local public schools are starting to see an uptick in flu cases as the Oregon Health Authority says seasonal influenza is increasing statewide.
Flu season usually runs November through April or May, with peak illnesses reported between December and February.
However, health leaders say overall numbers across Oregon are still relatively low.
"So far, it's not too bad," said Dr. Paul Lewis, Multnomah County Health Officer. "But it's going to come. It always does, usually in February or March -- sometimes earlier."
Health officials recommend that parents get their children vaccinated for the flu early, as it can take up to two weeks to become effective.
"People look at the flu as sort of a bad cold," said Dr. Corey Fish of Pacific Crest Children's Urgent Care. "But I think it can be much more of a bad actor than that for sure."
You can find your local flu shot clinic on the state’s website.
Vaccinated people typically face shorter and less severe symptoms than those who skip the flu shot.
Healthy people can get the flu and only face mild symptoms. They may not even realize they have it. But they can still pass it on to others who are more vulnerable.
Officials urge parents to "do the little things that seem inconsequential," such as washing hands, getting the flu vaccine, and keeping sick students at home.

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "Oregon health authority says influenza is increasing statewide today.",
  "items": [
    {"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null, "city": null, "state": "Oregon", "country": "USA", "start_date": "2018-12-07", "end_date": "2018-12-07", "words": "seasonal influenza is increasing statewide", "evidence": ["OREGON CITY, Ore. — Local public schools are starting to see an uptick in flu cases as the Oregon Health Authority says seasonal influenza is increasing statewide."]}
  ],
  "findings": [
    {"country": "USA", "finding": "Flu season usually runs November through April or May, with peak illnesses reported between December and February."},
    {"country": "USA", "finding": "It always does, usually in February or March -- sometimes earlier."}
  ]
}
</example>

### Example 19 (teaches: events on different days for one patient)

<example>
Scan date: 2015-06-12
Link: http://indianexpress.com/article/cities/mumbai/45-year-old-woman-dies-of-swine-flu/
Article:
45-year-old woman dies of swine flu
Sassoon hospital authorities said the woman’s swab report had tested positive for H1N1 virus.
Even as the state’s expert committee on communicable diseases has been crying hoarse to introduce vaccines against swine flu and build immunity among citizens ahead of the monsoon season, a 45-year-old woman died due to H1N1 virus at Sassoon General Hospital.
While authorities both at Sassoon hospital and a private hospital at Hadapsar where the woman was earlier treated refused to be quoted, they confirmed that the Pune resident, who was both diabetic and obese, had been infected with H1N1 virus.
According to sources, the woman, who was admitted to a private hospital for nearly 10 days, had been recovering from swine flu. However, since the recovery was slow, her relatives decided to shift her to Sassoon General Hospital on June 8. Sassoon hospital authorities said the woman’s swab report had tested positive for H1N1 virus.
[related-post]
Dr Subash Salunke, chairman of the state expert committee on communicable diseases that has been recommending use of vaccines against swine flu, told The Indian Express that sporadic cases of swine flu were bound to occur throughout the year.
“Worldwide, it has been proved that vaccines are useful. Only recently, we told the state to step up surveillance measures and introduce vaccines for the high-risk group, including paramedical staff that come in contact with swine flu patients,” Salunke said.
He also criticised the municipal corporations in Pune and Nagpur for allegedly taking inadequate measures to prevent swine flu. “We strongly feel the preparations are inadequate,” Salunke said.
“The PMC has been asked to make presentations and inform us about measures taken,” he said, adding that municipal health authorities were “not taking their jobs seriously”.
Reacting to Salunke’s criticism, Dr S T Pardeshi, acting medical chief at the PMC, said it was not fair to blame civic health officials.
“Surveillance is underway and there is continuous reporting of diseases from officials at hospitals. We have provided vaccines to 200 health workers and informed the state government that there was a need to introduce intra-nasal vaccines,” Pardeshi said.

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "A Pune woman was admitted on one day and died on a later day, so there are two items.",
  "items": [
    {"kind": "hospitalized", "strain": "H1N1", "number": 1, "status": null, "total_or_new": "new", "city": "Pune", "state": "Maharashtra", "country": "India", "start_date": "2015-05-29", "end_date": "2015-05-29", "words": null, "evidence": ["While authorities both at Sassoon hospital and a private hospital at Hadapsar where the woman was earlier treated refused to be quoted, they confirmed that the Pune resident, who was both diabetic and obese, had been infected with H1N1 virus.", "According to sources, the woman, who was admitted to a private hospital for nearly 10 days, had been recovering from swine flu. However, since the recovery was slow, her relatives decided to shift her to Sassoon General Hospital on June 8. Sassoon hospital authorities said the woman’s swab report had tested positive for H1N1 virus."]},
    {"kind": "deaths", "strain": "H1N1", "number": 1, "status": "confirmed", "total_or_new": "new", "city": "Pune", "state": "Maharashtra", "country": "India", "start_date": "2015-06-12", "end_date": "2015-06-12", "words": null, "evidence": ["a 45-year-old woman died due to H1N1 virus at Sassoon General Hospital.", "While authorities both at Sassoon hospital and a private hospital at Hadapsar where the woman was earlier treated refused to be quoted, they confirmed that the Pune resident, who was both diabetic and obese, had been infected with H1N1 virus.", "According to sources, the woman, who was admitted to a private hospital for nearly 10 days, had been recovering from swine flu. However, since the recovery was slow, her relatives decided to shift her to Sassoon General Hospital on June 8. Sassoon hospital authorities said the woman’s swab report had tested positive for H1N1 virus."]}
  ],
  "findings": []
}
</example>

### Example 20 (teaches: not useful: flu only in a caption)

<example>
Scan date: 2018-03-05
Link: https://article.wn.com/view/2018/03/05/The_killer_disease_with_no_vaccine/
Article:
Since the beginning of the year, Nigeria has been gripped by an outbreak of a deadly disease. Lassa fever is one of a number of illnesses which can cause dangerous epidemics, but for which no vaccine currently exists. ... read full story
Photo: A healthcare professional puts a band aid over the site of an injection after providing a flu vaccine to a patient during a Community influenza vaccination event held by Naval Hospital Camp Lejeune aboard Marine Corps Base Camp Lejeune, Oct. 20.

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "A Lassa fever story; the only flu text is a photo caption about a vaccination event.",
  "items": [],
  "findings": []
}
</example>

### Example 21 (teaches: a positive test with unknown cause of death is a case, not a death)

<example>
Scan date: 2015-07-13
Link: http://www.medindia.net/news/public-health-officials-in-south-india-on-alert-after-one-case-of-swine-flu-150993-1.htm
Article:
Forty-seven-year-old woman succumbs to the virus in Chennai and cases of swine flu are reported in other districts of south India, alerting health officials.
Referring to the woman’s death he said, “The patient was suffering from asthma and she also tested positive for H1N1 virus. This made her condition worse and she died without responding to the treatment. If not for the infection, she would have lived with asthma. However, we are yet to categorise it into swine flu death. Pulmonologist have to conform it.”
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "A woman in Chennai tested positive for H1N1; her death is not yet categorised as a swine flu death, so the positive test is written as a case and there is no deaths item.",
  "items": [
    {"kind": "cases", "strain": "H1N1", "number": 1, "status": "confirmed", "total_or_new": "new", "city": "Chennai", "state": "Tamil Nadu", "country": "India", "start_date": "2015-07-13", "end_date": "2015-07-13", "words": null, "evidence": ["Forty-seven-year-old woman succumbs to the virus in Chennai and cases of swine flu are reported in other districts of south India, alerting health officials.\nReferring to the woman’s death he said, “The patient was suffering from asthma and she also tested positive for H1N1 virus. This made her condition worse and she died without responding to the treatment. If not for the infection, she would have lived with asthma. However, we are yet to categorise it into swine flu death. Pulmonologist have to conform it.”"]}
  ],
  "findings": []
}
</example>

### Example 22 (teaches: not useful: a plan to teach about flu)

<example>
Scan date: 2018-08-24
Link: http://www.xinhuanet.com/english/2018-08/24/c_137415414.htm
Article:
SYDNEY, Aug. 24 (Xinhua) -- An Australian hospital is trialing the use of a humanoid robot this month to provide information and direct visitors, much to the fascination of patients and staff alike.
Pepper, a model of robot developed by Japanese company SoftBank Robotics, has been used internationally in customer support positions due to its engaging and humanlike features, Belinda Ward from the Queensland University of Technology (QUT) told Xinhua on Friday.
Now, for the first time in Australia, Pepper has been providing patients and visitors at Townsville Hospital in the State of Queensland with information regarding 10 simple aspects of the hospital, such as how they can wash their hands, where to get a coffee and where to find parking meters.
The trial is a joint initiative between the Australian Centre of Excellence in Robotic Vision at QUT, James Cook University and the Queensland government.
Enrolled nurse Anne Elvin, whose idea it was to bring Pepper to Townsville, said that while initially people are unsure of the robot they tend to warm to her very quickly, "when they notice the little fingers moving and the little gestures of the arms, they start to imagine that it's got some human instinct to it."
"We've found it a really positive experience for patients, visitors and any of the staff that engage with it," Elvin said.
While Pepper can't yet help nursing staff with complex tasks, it still has an important and helpful role to play within the hospital environment.
"The advantage that Pepper has over just being a touch screen for example, is that she really does feel like she's listening and engaging with you," Ward said.
"People coming into a hospital might be a bit stressed or worried and it can be quite reassuring and I guess a little bit fun to interact with a robot like Pepper."
The next aspect of the trial will involve Pepper taking on an education role and informing people about the influenza virus, which the hospital will gauge people's reactions to.
But for now, Pepper's job is mostly just to put a smile on to people's faces, something it succeeds in doing, sometimes unconventionally.
"An emergency department consultant once asked Pepper where to find a doctor, which was not a line we had it programmed to answer, and Pepper replied with information about where the shops and cafes were," Elvin recalled.
"Everybody had a big laugh because it was kind of accurate."

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "A hospital robot may later teach visitors about the flu virus; this is a plan, not flu activity.",
  "items": [],
  "findings": []
}
</example>

### Example 23 (teaches: trend fallback: people dying, no count)

<example>
Scan date: 2016-02-14
Link: http://indianexpress.com/article/cities/delhi/will-use-every-inch-of-space-to-double-beds-in-hospitals-satyendar-jain/
Article:
Will use every inch of space to double beds in hospitals: Satyendar Jain
The work we have done in the power sector has gone largely unrecognised. The rates of power have increased in Haryana and UP by multiple folds. We did not let rates increase in Delhi. I think that is a huge achievement. Take health… despite all the criticism on the dengue crisis, there were no deaths in Delhi government hospitals from dengue. People are dying of swine flu in Gujarat and Rajasthan but we have kept the situation in control in Delhi.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "Swine flu deaths are reported in Gujarat and Rajasthan with no count, so each state gets a trend item.",
  "items": [
    {"kind": "trend", "strain": "swine flu", "number": null, "status": null, "total_or_new": null, "city": null, "state": "Gujarat", "country": "India", "start_date": "2016-02-14", "end_date": "2016-02-14", "words": "People are dying of swine flu", "evidence": ["People are dying of swine flu in Gujarat and Rajasthan but we have kept the situation in control in Delhi."]},
    {"kind": "trend", "strain": "swine flu", "number": null, "status": null, "total_or_new": null, "city": null, "state": "Rajasthan", "country": "India", "start_date": "2016-02-14", "end_date": "2016-02-14", "words": "People are dying of swine flu", "evidence": ["People are dying of swine flu in Gujarat and Rajasthan but we have kept the situation in control in Delhi."]}
  ],
  "findings": []
}
</example>

### Example 24 (teaches: so far this year; a national agency gives a country only)

<example>
Scan date: 2024-11-09
Link: https://www.bemidjipioneer.com/health/public-health-services-in-southeast-minnesota-urge-farms-to-take-advantage-of-free-seasonal-flu-shots
Article:
AUSTIN, Minn. — Dairy and poultry farmers in three southeast Minnesota counties can get free seasonal flu shots on their farm thanks to a new public health initiative to remove vaccination barriers.
Poultry and dairy farmers are at the greatest risk of being simultaneously exposed to seasonal flu and H5N1. In its Nov. 1 update on confirmed human cases of H5N1 so far this year, the CDC listed 41 cases in six states.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "The CDC lists 41 human H5N1 cases so far this year; a national agency gives a country and no state.",
  "items": [
    {"kind": "cases", "strain": "H5N1", "number": 41, "status": "confirmed", "total_or_new": "total", "city": null, "state": null, "country": "USA", "start_date": "2024-01-01", "end_date": "2024-11-01", "words": null, "evidence": ["In its Nov. 1 update on confirmed human cases of H5N1 so far this year, the CDC listed 41 cases in six states.", "AUSTIN, Minn. — Dairy and poultry farmers in three southeast Minnesota counties can get free seasonal flu shots on their farm thanks to a new public health initiative to remove vaccination barriers."]}
  ],
  "findings": []
}
</example>

### Example 25 (teaches: not useful: an investment remark)

<example>
Scan date: 2017-07-13
Link: http://www.fool.com.au/2017/07/13/where-i-would-invest-25000-in-the-share-market-today/
Article:
With interest rates at record lows and unlikely to improve any time soon, if I had $25,000 sitting in a savings account I would consider putting it to work in the share market instead.
After all, the local share market has provided an average annual return of 5.5% over the last 10 years according to Russell Investments.
While there's no guarantee that the market will provide a return of that level again over the next 10 years, I feel reasonably confident that it will.
It is for this reason that I would suggest investors skip savings accounts and term deposits and focus instead on investing it in some quality shares.
Three shares which I think are worth considering are as follows:
CSL Limited (ASX: CSL)
In my opinion this biotherapeutics giant would have to be one of the best long-term buy and hold investment options on the Australian share market. Due to its industry leading immunoglobulins business and fast-growing influenza vaccine business, I believe CSL is positioned perfectly to deliver above-average earnings growth for at least the next decade.
GetSwift Ltd (ASX: GSW)
I think investors with a high tolerance for risk and an interest in small-cap shares should consider an investment in this logistics platform provider. The cash-rich and debt-free GetSwift recently raised capital with a significantly oversubscribed placement. The company plans to use these funds to accelerate its growth and expand into other lucrative verticals.
Ramsay Health Care Limited (ASX: RHC)
Like healthcare sector peer CSL, I think this private hospital operator would be a fantastic buy and hold investment option. As the global population ages, I believe demand for healthcare services will increase substantially. I feel this puts Ramsay and its global network of private hospitals in a strong position to deliver solid earnings growth for decades to come.

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "An investment article that mentions CSL's influenza vaccine business only.",
  "items": [],
  "findings": []
}
</example>

### Example 26 (teaches: a death and a hospital total; the hospital city; since April)

<example>
Scan date: 2018-07-13
Link: https://www.2gb.com/child-influenza-death-sparks-flu-vaccine-warning/
Article:
Child influenza death sparks flu vaccine warning
One child has died and more than a dozen others have been hospitalised after coming down with the flu.
19 children have been admitted to Westmead Children’s hospital with influenza since April.
The dominant flu strain in New South Wales this year hits young children and pregnant women the hardest.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "One flu death in New South Wales on the day, and 19 patients in hospital since April at Westmead.",
  "items": [
    {"kind": "deaths", "strain": null, "number": 1, "status": null, "total_or_new": "new", "city": null, "state": "New South Wales", "country": "Australia", "start_date": "2018-07-13", "end_date": "2018-07-13", "words": null, "evidence": ["One child has died and more than a dozen others have been hospitalised after coming down with the flu.", "The dominant flu strain in New South Wales this year hits young children and pregnant women the hardest."]},
    {"kind": "hospitalized", "strain": null, "number": 19, "status": null, "total_or_new": "total", "city": "Westmead", "state": "New South Wales", "country": "Australia", "start_date": "2018-04-01", "end_date": "2018-07-13", "words": null, "evidence": ["19 children have been admitted to Westmead Children’s hospital with influenza since April.", "The dominant flu strain in New South Wales this year hits young children and pregnant women the hardest."]}
  ],
  "findings": []
}
</example>

### Example 27 (teaches: not useful, but with a finding on season timing)

<example>
Scan date: 2019-10-10
Link: https://www.wptv.com/news/state/publix-offers-10-gift-cards-to-get-your-flu-shot
Article:
Publix is basically paying you to get your flu shot.
The Centers for Disease Control and Prevention recommends everyone 6 months of age and older get a flu vaccine by the end of October.
The CDC says while seasonal influenza viruses are detected year-round in the United States, flu viruses are most common during the fall and winter.
Influenza activity often begins to increase in October.
Typically flu activity peaks between December and February, although activity can last as late as May.
[article trimmed]

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "A gift card for flu shots; the CDC lines on when flu season runs are a finding even though the article is not useful.",
  "items": [],
  "findings": [
    {"country": "USA", "finding": "The CDC says while seasonal influenza viruses are detected year-round in the United States, flu viruses are most common during the fall and winter. Influenza activity often begins to increase in October. Typically flu activity peaks between December and February, although activity can last as late as May."}
  ]
}
</example>

### Example 28 (teaches: week ending and between two dates; the scan date as article date)

<example>
Scan date: 2018-07-12
Link: http://www.dailymail.co.uk/wires/aap/article-5948789/Child-death-spurs-NSW-flu-vaccine-warning.html
Article:
NSW health authorities are urging parents to get their kids vaccinated with the free flu shot after a child died from influenza.
The child was one of 19 admitted to Sydney's children's hospital between April 3 and July 8 with the flu, with only two of those infants fully vaccinated.
News of the death comes as the authority predicts a slow start to this year's flu season in NSW, with 256 cases confirmed in the week ending July 8, compared with 6449 cases in the equivalent week in 2017.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "Sydney hospital and New South Wales figures for the weeks before the article; the scan date is the article date.",
  "items": [
    {"kind": "hospitalized", "strain": null, "number": 19, "status": null, "total_or_new": "total", "city": "Sydney", "state": "New South Wales", "country": "Australia", "start_date": "2018-04-03", "end_date": "2018-07-08", "words": null, "evidence": ["NSW health authorities are urging parents to get their kids vaccinated with the free flu shot after a child died from influenza.\nThe child was one of 19 admitted to Sydney's children's hospital between April 3 and July 8 with the flu, with only two of those infants fully vaccinated."]},
    {"kind": "deaths", "strain": null, "number": 1, "status": null, "total_or_new": "new", "city": "Sydney", "state": "New South Wales", "country": "Australia", "start_date": "2018-07-12", "end_date": "2018-07-12", "words": null, "evidence": ["NSW health authorities are urging parents to get their kids vaccinated with the free flu shot after a child died from influenza.\nThe child was one of 19 admitted to Sydney's children's hospital between April 3 and July 8 with the flu, with only two of those infants fully vaccinated."]},
    {"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null, "city": null, "state": "New South Wales", "country": "Australia", "start_date": "2018-07-12", "end_date": "2018-07-12", "words": "slow start", "evidence": ["News of the death comes as the authority predicts a slow start to this year's flu season in NSW,"]},
    {"kind": "cases", "strain": null, "number": 256, "status": "confirmed", "total_or_new": "total", "city": null, "state": "New South Wales", "country": "Australia", "start_date": "2018-07-02", "end_date": "2018-07-08", "words": null, "evidence": ["News of the death comes as the authority predicts a slow start to this year's flu season in NSW, with 256 cases confirmed in the week ending July 8,"]}
  ],
  "findings": []
}
</example>

### Example 29 (teaches: this week)

<example>
Scan date: 2024-04-05
Link: https://kffhealthnews.org/morning-breakout/as-bird-flu-spreads-to-more-cows-top-expert-explains-threat-to-humans/
Article:
News that H5N1 avian influenza has breached another mammalian species — this time dairy cows — has taken the flu science community aback. Though cows previously had been seen to be susceptible to human flu viruses, and could be experimentally infected with H5 in a lab, the absence of cow involvement until now in H5’s nearly 30-year history lulled scientists into thinking the species was outside the virus’s remit. Further elevating the concern this discovery has triggered is the fact that a dairy farm worker in Texas was infected with H5N1, though the unnamed individual’s only symptom was conjunctivitis. (Branswell, 4/5)
The first human case of avian influenza in Texas this week has prompted Congress to gather information about the risks to public health and agriculture. The Centers for Disease Control and Prevention held a bipartisan briefing with congressional agriculture staff about the person infected after exposure to infected dairy cattle, according to a congressional aide. And members of Congress plan to schedule a meeting with the Agriculture Department, which announced last month that “there is no concern about the safety of the commercial milk supply or that this circumstance poses a risk to consumer health.” (Bridges, 4/4)
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "A dairy worker in Texas has H5N1 this week.",
  "items": [
    {"kind": "cases", "strain": "H5N1", "number": 1, "status": "confirmed", "total_or_new": "new", "city": null, "state": "Texas", "country": "USA", "start_date": "2024-04-01", "end_date": "2024-04-05", "words": null, "evidence": ["Further elevating the concern this discovery has triggered is the fact that a dairy farm worker in Texas was infected with H5N1, though the unnamed individual’s only symptom was conjunctivitis.", "The first human case of avian influenza in Texas this week has prompted Congress to gather information about the risks to public health and agriculture."]}
  ],
  "findings": []
}
</example>

### Example 30 (teaches: not useful: norovirus and "stomach flu")

<example>
Scan date: 2016-12-12
Link: http://kingfm.com/norovirus-outbreaks-reported-in-cheyenne-casper/
Article:
Norovirus Outbreaks Reported In Cheyenne, Casper
A virus that is often confused with food poisoning or stomach flu is being reported in Cheyenne and Casper, according to a release from the Wyoming Department of Health.
[article trimmed]

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "Norovirus outbreaks; \"stomach flu\" is not influenza.",
  "items": [],
  "findings": []
}
</example>

### Example 31 (teaches: first fortnight; a percentage goes in words)

<example>
Scan date: 2023-04-21
Link: https://www.bendigoadvertiser.com.au/story/8167589/waning-immunity-and-omicron-sublineages-the-cause-of-covid-rise/
Article:
Greater Bendigo has recorded 137 new COVID-19 cases in the past week.
Professor Sutton said notified influenza cases in Victoria rose by 38 per cent in the first fortnight of April compared to the fortnight prior - indicating seasonal influenza activity has returned for 2023.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "Victoria reports a 38 per cent rise in notified influenza cases in the first fortnight of April; the percentage goes in words, not in number.",
  "items": [
    {"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null, "city": null, "state": "Victoria", "country": "Australia", "start_date": "2023-04-01", "end_date": "2023-04-14", "words": "rose by 38 per cent", "evidence": ["Professor Sutton said notified influenza cases in Victoria rose by 38 per cent in the first fortnight of April compared to the fortnight prior - indicating seasonal influenza activity has returned for 2023."]}
  ],
  "findings": []
}
</example>

### Example 32 (teaches: not useful: flu as a metaphor)

<example>
Scan date: 2023-12-12
Link: https://www.the-star.co.ke/counties/coast/2023-12-12-new-sh50m-mikindani-market-to-open-in-january/
Article:
Mikindani residents in Jomvu constituency will from January no longer have to travel to Kongowea Market, 10.8km away to buy foodstuff and other goods.
“But now the traffic jams will be a thing of the past. That traffic problem was like a flu to us. But now we have sneezed that disease away and it is now affecting the Nyali people where there is constant jam from the Nyali bridge especially at peak hours,” Twalib said.
[article trimmed]

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "Flu is used as a metaphor for a traffic jam.",
  "items": [],
  "findings": []
}
</example>

### Example 33 (teaches: past four weeks; a percentage goes in words)

<example>
Scan date: 2023-12-20
Link: https://www.cnn.com/2023/12/20/health/holiday-virus-rsv-covid-flu-winter-wellness/
Article:
Get inspired by a weekly roundup on living well, made simple. Sign up for CNN’s Life, But Better newsletter for information and tools designed to improve your well-being.
The coronavirus subvariant JN.1 is now the fastest growing strain of the virus in the United States. The strain now constitutes about 20% of new Covid-19 infections, according to the US Centers for Disease Control and Prevention. In the Northeast, JN.1 has become the dominant variant.
Meanwhile, the CDC has issued an alert to clinicians about the need to increase immunizations for influenza, Covid-19, and respiratory syncytial virus, or RSV. The public health agency reported that in the past four weeks, hospitalizations across all age groups increased by 200% for influenza, 60% for RSV and 51% for Covid-19.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "US flu hospitalizations rose 200% over the past four weeks; the percentage goes in words, not in number.",
  "items": [
    {"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null, "city": null, "state": null, "country": "USA", "start_date": "2023-11-22", "end_date": "2023-12-20", "words": "hospitalizations across all age groups increased by 200% for influenza", "evidence": ["The coronavirus subvariant JN.1 is now the fastest growing strain of the virus in the United States. The strain now constitutes about 20% of new Covid-19 infections, according to the US Centers for Disease Control and Prevention. In the Northeast, JN.1 has become the dominant variant.", "Meanwhile, the CDC has issued an alert to clinicians about the need to increase immunizations for influenza, Covid-19, and respiratory syncytial virus, or RSV. The public health agency reported that in the past four weeks, hospitalizations across all age groups increased by 200% for influenza, 60% for RSV and 51% for Covid-19."]}
  ],
  "findings": []
}
</example>

### Example 34 (teaches: last week (Monday to Sunday))

<example>
Scan date: 2022-10-10
Link: https://nystateofpolitics.com/state-of-politics/new-york/ny-state-of-politics/2022/10/10/new-york-health-officials-launch-campaign-for-flu--covid-shots
Article:
Health officials in New York are launching a public awareness campaign to urge people to get their COVID-19 boosters and flu shots this season.
Bassett last week warned of an "early and substantial increase" in flu cases found in New York. Gov. Kathy Hochul's office on Friday reported 20 COVID cases per 100,000 residents in New York, and 2,433 people are hospitalized with the virus.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "New York reports an early and substantial increase in flu last week.",
  "items": [
    {"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null, "city": null, "state": "New York", "country": "USA", "start_date": "2022-10-03", "end_date": "2022-10-09", "words": "early and substantial increase", "evidence": ["Bassett last week warned of an \"early and substantial increase\" in flu cases found in New York."]}
  ],
  "findings": []
}
</example>

### Example 35 (teaches: not useful: flu-like symptoms as a side effect)

<example>
Scan date: 2017-10-18
Link: https://www.prnewswire.com/news-releases/novartis-drug-promacta-shows-long-term-disease-control-for-chronicpersistent-immune-thrombocytopenia-itp-300538507.html
Article:
EAST HANOVER, N.J., Oct. 18, 2017 /PRNewswire/ -- Novartis today announced long-term study results supporting the positive safety and efficacy of Promacta (eltrombopag) in adults with chronic/persistent (enrolling patients that were 6 or more months from diagnosis) immune (idiopathic) thrombocytopenia (ITP) were published online in Blood. The EXTEND study found that a majority of patients maintained a substantial clinical response and many no longer needed concomitant ITP medications. The research evaluated patients for up to 8 years of continuous treatment (median exposure of 2.4 years)1,2.
The most common side effects of Promacta when used to treat chronic ITP in adults are: nausea; diarrhea; upper respiratory tract infection (symptoms may include runny nose, stuffy nose, and sneezing); vomiting; muscle aches; urinary tract infection (symptoms may include frequent or urgent need to urinate, low fever in some people, pain or burning with urination); pain or swelling (inflammation) in the throat or mouth (oropharyngeal pain and pharyngitis); abnormal liver function tests; back pain; flu-like symptoms (influenza), including fever, headache, tiredness, cough, sore throat, and body aches; skin tingling, itching, or burning; and rash.
The most common side effects when Promacta is used in combination with other medicines to treat chronic HCV are: low red blood cell count (anemia); fever; tiredness; headache; nausea; diarrhea; decreased appetite; flu-like symptoms (influenza), including fever, headache, tiredness, cough, sore throat, and body aches; feeling weak; trouble sleeping; cough; itching; chills; muscle aches; hair loss; and swelling in the ankles, feet, and legs.
[article trimmed]

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "A drug press release; \"flu-like symptoms\" is only a listed side effect.",
  "items": [],
  "findings": []
}
</example>

### Example 36 (teaches: the broader total is kept over its parts)

<example>
Scan date: 2024-12-07
Link: https://www.turlockjournal.com/news/local/county-records-first-flu-death-of-season/
Article:
While the winter flu season has just begun, the Stanislaus County Public Health Department reported on Friday the county's first flu-related death of an individual under age 65.
Influenza is a contagious virus that spreads easily from person to person, affecting families and communities nationwide each year. Flu symptoms can range from mild to severe. Common symptoms include fever, cough, sore throat, runny or stuffy nose, muscle or body aches, headaches, and fatigue. In severe cases, flu complications may result in hospitalization or even death. While anyone can experience severe flu illness, certain groups are at higher risk, including young children, adults aged 65 and older, pregnant women, and individuals with chronic medical conditions.
According to the Centers for Disease Control, California has an influenza mortality rate of 11.5% and recorded 5,308 deaths due to influenza in 2022.
There have been a confirmed total of 58 human cases of avian flu in the United States, with 32 of them in California.
In November, the CDC confirmed that a child from Alameda County tested positive for avian influenza. The child had no known contact with an infected animal, but public health experts are investigating a possible exposure to wild birds.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "A California death and 58 US avian flu cases; the 32 California cases and the child are parts of the 58, so only the national total is kept.",
  "items": [
    {"kind": "deaths", "strain": null, "number": 1, "status": null, "total_or_new": "new", "city": null, "state": "California", "country": "USA", "start_date": "2024-12-06", "end_date": "2024-12-06", "words": null, "evidence": ["While the winter flu season has just begun, the Stanislaus County Public Health Department reported on Friday the county's first flu-related death of an individual under age 65.", "According to the Centers for Disease Control, California has an influenza mortality rate of 11.5% and recorded 5,308 deaths due to influenza in 2022."]},
    {"kind": "cases", "strain": "avian flu", "number": 58, "status": "confirmed", "total_or_new": "total", "city": null, "state": null, "country": "USA", "start_date": null, "end_date": "2024-12-07", "words": null, "evidence": ["There have been a confirmed total of 58 human cases of avian flu in the United States, with 32 of them in California."]}
  ],
  "findings": []
}
</example>

### Example 37 (teaches: not useful: the nickname "little flu" for COVID-19)

<example>
Scan date: 2021-11-25
Link: https://www.justiceinfo.net/en/84739-bolsonaro-against-brazil-resuming-carnival.html
Article:
President Jair Bolsonaro said Thursday he was against Brazil resuming carnival celebrations in February, a rare nod to Covid-19 social distancing measures from the far-right leader.
He did not mention his more controversial handling of the virus, which he downplayed as a "little flu," attacking stay-at-home measures, face masks and vaccines.
[article trimmed]

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "President Bolsonaro called COVID-19 \"a little flu\"; a figure of speech, not influenza.",
  "items": [],
  "findings": []
}
</example>

### Example 38 (teaches: hospitalized over cases when the patient has gone home from hospital)

<example>
Scan date: 2024-06-21
Link: https://en.antaranews.com/news/316620/indonesia-amps-up-surveillance-to-prevent-bird-flu-in-humans
Article:
In a statement received here on Friday, director for surveillance and health quarantine at the Health Ministry, Achmad Farchanny Tri Adryanto, said that the ministry is consistently monitoring the avian influenza strain which can infect humans.
He said that based on the WHO's June 11, 2024, report, a type-A Avian Influenza (H9N2) case was detected in a child from West Bengal, India. The child, who contracted the infection after coming in contact with an avian source of the virus, has recovered and gone home from hospital.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "WHO reports an H9N2 case in a West Bengal child who has gone home from hospital; hospitalized is the more severe kind, so it is written and not cases.",
  "items": [
    {"kind": "hospitalized", "strain": "H9N2", "number": 1, "status": null, "total_or_new": "new", "city": null, "state": "West Bengal", "country": "India", "start_date": "2024-06-11", "end_date": "2024-06-11", "words": null, "evidence": ["He said that based on the WHO's June 11, 2024, report, a type-A Avian Influenza (H9N2) case was detected in a child from West Bengal, India. The child, who contracted the infection after coming in contact with an avian source of the virus, has recovered and gone home from hospital."]}
  ],
  "findings": []
}
</example>

### Example 39 (teaches: a week number with a stated range; several items in one article)

<example>
Scan date: 2024-05-15
Link: https://reliefweb.int/map/world/epidemic-and-emerging-disease-alerts-pacific-14-may-2024
Article:
Highlights/updates since the last map was sent on PacNet on 07 May 2024:
Influenza A
- French Polynesia: In EpiWeek 18, there were 43 new confirmed cases of influenza out of 107 tests conducted, comprising 42 cases of Influenza A and 1 case of Influenza B. Among the reported cases, 22 were hospitalised, including two in the ICU, and one death occurred in a person aged over 60, bringing the total deaths between April and May 2024 to 3. Of the hospitalised cases, 10 were aged over 60 and 2 were aged below 4 years old. The positivity rate increased from 24.2% in EpiWeek 17 to 40.2% in EpiWeek 18. The red alert is maintained. - Source: Bulletin de surveillance sanitaire de Polynésie française n°18 -2024 shared with PPHSN focal point on 08 May 2024.
- Australia, Victoria: On May 10, the Victoria Health department issued an alert due to increased COVID-19 activity, as evidenced by rising 7-day average hospitalisation figures (208), a 30% increase in notifications of influenza and RSV over the past fortnight and elevated detection of COVID-19 in wastewater indicating high levels of COVID-19 transmission- Source: Increase in COVID-19 activity | health.vic.gov.au accessed on 14 May 2024.
- Tonga: In EpiWeek 17, the Tonga Health Department reported two dengue cases from Vaiola Hospital: a 22-year-old female tested positive for IgG, and a 25-year-old female tested positive for both IgM and IgG, with both results returning negative for NS1. No outbreak has been declared, but the situation is being closely monitored. - Source: Tonga Ministry of Health Communicable Diseases Syndromic Surveillance Epidemic week 17 (22/04/2024 - 28/04/2024) reported shared PPHSN focal point on 09 May 2024.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "French Polynesia (France) reports weekly influenza figures by EpiWeek; the dates come from a week range stated elsewhere in the article.",
  "items": [
    {"kind": "cases", "strain": null, "number": 43, "status": "confirmed", "total_or_new": "new", "city": null, "state": null, "country": "France", "start_date": "2024-04-29", "end_date": "2024-05-05", "words": null, "evidence": ["- French Polynesia: In EpiWeek 18, there were 43 new confirmed cases of influenza out of 107 tests conducted, comprising 42 cases of Influenza A and 1 case of Influenza B.", "- Source: Tonga Ministry of Health Communicable Diseases Syndromic Surveillance Epidemic week 17 (22/04/2024 - 28/04/2024) reported shared PPHSN focal point on 09 May 2024."]},
    {"kind": "hospitalized", "strain": null, "number": 22, "status": null, "total_or_new": "new", "city": null, "state": null, "country": "France", "start_date": "2024-04-29", "end_date": "2024-05-05", "words": null, "evidence": ["- French Polynesia: In EpiWeek 18, there were 43 new confirmed cases of influenza out of 107 tests conducted, comprising 42 cases of Influenza A and 1 case of Influenza B.", "Among the reported cases, 22 were hospitalised, including two in the ICU, and one death occurred in a person aged over 60, bringing the total deaths between April and May 2024 to 3.", "- Source: Tonga Ministry of Health Communicable Diseases Syndromic Surveillance Epidemic week 17 (22/04/2024 - 28/04/2024) reported shared PPHSN focal point on 09 May 2024."]},
    {"kind": "deaths", "strain": null, "number": 1, "status": null, "total_or_new": "new", "city": null, "state": null, "country": "France", "start_date": "2024-04-29", "end_date": "2024-05-05", "words": null, "evidence": ["- French Polynesia: In EpiWeek 18, there were 43 new confirmed cases of influenza out of 107 tests conducted, comprising 42 cases of Influenza A and 1 case of Influenza B.", "Among the reported cases, 22 were hospitalised, including two in the ICU, and one death occurred in a person aged over 60, bringing the total deaths between April and May 2024 to 3.", "- Source: Tonga Ministry of Health Communicable Diseases Syndromic Surveillance Epidemic week 17 (22/04/2024 - 28/04/2024) reported shared PPHSN focal point on 09 May 2024."]},
    {"kind": "deaths", "strain": null, "number": 3, "status": null, "total_or_new": "total", "city": null, "state": null, "country": "France", "start_date": "2024-04-01", "end_date": "2024-05-05", "words": null, "evidence": ["- French Polynesia: In EpiWeek 18, there were 43 new confirmed cases of influenza out of 107 tests conducted, comprising 42 cases of Influenza A and 1 case of Influenza B.", "Among the reported cases, 22 were hospitalised, including two in the ICU, and one death occurred in a person aged over 60, bringing the total deaths between April and May 2024 to 3.", "- Source: Tonga Ministry of Health Communicable Diseases Syndromic Surveillance Epidemic week 17 (22/04/2024 - 28/04/2024) reported shared PPHSN focal point on 09 May 2024."]},
    {"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null, "city": null, "state": null, "country": "France", "start_date": "2024-04-22", "end_date": "2024-05-05", "words": "increased from 24.2% in EpiWeek 17 to 40.2% in EpiWeek 18", "evidence": ["- French Polynesia: In EpiWeek 18, there were 43 new confirmed cases of influenza out of 107 tests conducted, comprising 42 cases of Influenza A and 1 case of Influenza B.", "The positivity rate increased from 24.2% in EpiWeek 17 to 40.2% in EpiWeek 18.", "- Source: Tonga Ministry of Health Communicable Diseases Syndromic Surveillance Epidemic week 17 (22/04/2024 - 28/04/2024) reported shared PPHSN focal point on 09 May 2024."]},
    {"kind": "trend", "strain": null, "number": null, "status": null, "total_or_new": null, "city": null, "state": "Victoria", "country": "Australia", "start_date": "2024-04-27", "end_date": "2024-05-10", "words": "30% increase in notifications of influenza and RSV", "evidence": ["Australia, Victoria: On May 10, the Victoria Health department issued an alert due to increased COVID-19 activity, as evidenced by rising 7-day average hospitalisation figures (208), a 30% increase in notifications of influenza and RSV over the past fortnight and elevated detection of COVID-19 in wastewater indicating high levels of COVID-19 transmission"]}
  ],
  "findings": []
}
</example>

### Example 40 (teaches: not useful: a forecast for the coming winter)

<example>
Scan date: 2022-04-19
Link: https://www.dailymail.co.uk/news/article-10730175/Babies-extreme-risk-severe-sickness-winter-NOT-Covid.html
Article:
- Experts warn children are 'immune naïve' after lengthy Covid lockdowns
- The flu could severely impact kids with suppressed immune systems this winter
Babies and toddlers are at risk getting seriously ill with colds and the flu this winter as they are 'immune naïve', doctors have warned.
Parents who avoided Covid for the past two years likely also kept their babies and toddlers from encountering the common cold or flu.
Experts are warning parents to brace for a horror flu that could potentially be worse than Covid for 'immune naïve' babies and toddlers
'If there is a large winter epidemic, influenza will sweep through schools and the adult population, and in many children, this disease is more severe than Covid.
'These children have not had the opportunity to build up their immune system and are now very susceptible to catching bronchiolitis or influenza.'
She said parents could protect their children from the flu and other serious viral infections with good nutrition and by having clean flowing air through their home.
The National Health and Medical Research Council recommends an annual flu shot for babies and children from the time they are six months old.
Children under five are at high risk of severe influenza infections that require hospitalisation.
An Australian review of the 2015 influenza season at two major hospitals found 7.3 per cent of children admitted with confirmed influenza needed intensive care.
[article trimmed]

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "A forecast about babies and the coming winter; there is no current flu statement.",
  "items": [],
  "findings": []
}
</example>

### Example 41 (teaches: first death of the season; a roundup line that is not about flu is left out)

<example>
Scan date: 2016-12-02
Link: http://californiahealthline.org/morning-briefing/friday-december-2-2016/
Article:
Latest From California Healthline:
Although the state just confirmed the first death, 11 others have had to be admitted to the ICU this season.
					California health officials on Thursday confirmed the state’s first death of this year’s influenza season and reminded everyone to get a flu shot before more people get sick. “As this unfortunate case illustrates, the flu can be deadly and causes thousands of fatalities each year in the United States,” said Karen Smith, director of the California Department of Public Health. “Fortunately, people can get vaccinated to help keep them from getting sick and spreading the flu to others.” (Karlamangla, 12/1)				
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "California reports the state's first flu death of the season; a nearby line about 11 others in intensive care is not about flu and is left out.",
  "items": [
    {"kind": "deaths", "strain": null, "number": 1, "status": null, "total_or_new": "new", "city": null, "state": "California", "country": "USA", "start_date": "2016-12-01", "end_date": "2016-12-01", "words": null, "evidence": ["California health officials on Thursday confirmed the state’s first death of this year’s influenza season and reminded everyone to get a flu shot before more people get sick."]}
  ],
  "findings": []
}
</example>

### Example 42 (teaches: not useful: the 1918 pandemic only)

<example>
Scan date: 2015-11-18
Link: http://www.theobserver.com/2015/11/honoring-americas-veterans/
Article:
KEARNY –
Mayor Alberto Santos read a list of the Kearny WWI dead: Arthur McEntevy, killed in action at Gallipoli, 1915; Hugh Fleming, died of wounds, 1917; Edward W. McWhirter, killed in action, 1918; Casswell Gross, died of wounds, 1918; James Corbett, killed in action in Cambri, France, 1918; and Arthur Perring Heward, died of influenza pneumonia, 1918.
Santos noted that America did not enter WWI until April 2017 – 19 months before the armistice – but, “in that short time span, 110,000 American soldiers made the ultimate sacrifice – many killed in action, many died from wounds and over 40,000 died from the influenza pandemic.”
[article trimmed]

Answer:
{
  "useful": false,
  "borderline": false,
  "reason": "A Veterans Day article; influenza appears only as 1918 deaths.",
  "items": [],
  "findings": []
}
</example>

### Example 43 (teaches: a suspected case; the place filled in from the city)

<example>
Scan date: 2017-01-11
Link: http://www.hindustantimes.com/lucknow/magh-mela-area-faces-swine-flu-scare/story-V0s9btZSDrboEAhE7NMx1I.html
Article:
Magh Mela area faces swine flu scare
The scare started after one of the saints showed symptoms similar to H1N1 flu virus in Magh Mela area. He was later taken to Delhi for treatment. According to the CMO, 650 vials of swine flu vaccine have already arrived, and another batch of 500 vaccines would come in the next 2-3 days.
“We can’t say that it was swine flu as we don’t have H1N1 testing facility in Allahabad. However, after this suspected case reported in Mela area we started preparations to ensure that the virus does not spread in the Mela area ,” says chief medical officer Dr Alok Verma.
[article trimmed]

Answer:
{
  "useful": true,
  "borderline": false,
  "reason": "A suspected H1N1 case in Allahabad; the state and country follow from the city.",
  "items": [
    {"kind": "cases", "strain": "H1N1", "number": 1, "status": "suspected", "total_or_new": "new", "city": "Allahabad", "state": "Uttar Pradesh", "country": "India", "start_date": "2017-01-11", "end_date": "2017-01-11", "words": null, "evidence": ["Magh Mela area faces swine flu scare\nThe scare started after one of the saints showed symptoms similar to H1N1 flu virus in Magh Mela area", "“We can’t say that it was swine flu as we don’t have H1N1 testing facility in Allahabad.", "However, after this suspected case reported in Mela area we started preparations to ensure that the virus does not spread in the Mela area ,” says chief medical officer Dr Alok Verma."]}
  ],
  "findings": []
}
</example>

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
  "required": ["useful", "borderline", "reason", "items", "findings"],
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
        "country": {"type": ["string", "null"]},
        "start_date": {"type": ["string", "null"], "format": "date"},
        "end_date": {"type": ["string", "null"], "format": "date"},
        "words": {"type": ["string", "null"]},
        "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1}
      }}},
    "findings": {"type": "array", "items": {
      "type": "object", "required": ["country", "finding"],
      "properties": {"country": {"type": "string"}, "finding": {"type": "string"}}}}
  }
}
```

If `useful` is false, `items` is an empty list; `findings` may still have entries. To save a result into
the labeling sheets: join `evidence` parts with a line containing `||`; `reason` and `borderline`
go into extra columns (the human sheets do not have them).

---

## 5. How to check and improve it

1. Score on the development rows only, never on the locked test set. Remove the 43 example rows from the
   development set before scoring (rows 202, 216, 207, 203, 243, 49, 231, 208, 83, 282, 143, 298, 210, 211, 215, 251, 264, 129, 192, 225, 197, 297, 171, 76, 315, 80, 128, 46, 105, 302, 97, 149, 140, 30, 150, 95, 111, 137, 87, 173, 185, 188, 117), and check them against the team's test-set list.
2. Score `useful` first (precision and recall). Then score items: an item matches when kind, place,
   strain and both dates agree. Report precision, recall and F1 per kind. Rows 109 and 152 have no human
   label; leave them out.
3. Automatic checks: (a) every evidence part occurs in the article; (b) `words` is null unless the kind is
   trend; (c) only four kinds; (d) no region words in place fields; (e) start_date is not after end_date;
   (f) no two overlapping items of the same kind; (g) `useful = false` has no items.
4. Read the borderline flags: the human recheck list (20 rows, learnings 18.5) shows which articles the
   human also found hard.
5. Change one rule or one example at a time and record it as v2.1, v2.2, ...

## 6. Notes and open points

- The soft spots are still undecided by the team (learnings 18.6): the window for "near the article date";
  nested totals; whether human bird flu on farms (rows 252, 308, 309, 310) and "common flu" (row 212)
  count; worldwide statements (row 109). The examples show the labeler's current choice.
- The suspected flu-like illness rule is in the learnings file, but no labeled example uses it yet; row 231
  is the `no` side of that rule. Row 49 shows `suspected` for patients isolated on suspicion.
- The prompt uses the scan date as the article date. In the human sheets the article date was the printed date, then the link date, then the scan date; they differ on three useful rows (40, 47 and 90), so item dates on those rows can be one day off when scoring.
- Rules with no labeled example yet (so the prompt states them but does not show them): suspected flu-like
  illness with no other cause, a vague outbreak line that becomes a trend, a worldwide statement with no
  country, one patient with several kinds on the same day, a hospital that counts "patients affected", a
  death that is suspected to be flu (status suspected), and `borderline = true`.
- Examples never come from the recheck list. Because every hard row is on that list, no example shows
  `borderline = true`; the team may add one after the recheck rows are settled.
- Examples are trimmed where the article was long (marked "[article trimmed]"); all evidence is still word
  for word.
- If the context is short, drop examples in pairs, one useful and one not useful: drop the later ones first, keeping the order
  of the rest; the examples headed "not useful" and "useful" should stay in about the same ratio.
