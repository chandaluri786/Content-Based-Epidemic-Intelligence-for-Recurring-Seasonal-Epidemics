# LLM Extraction Prompt (v1.0, few-shot)

Written for: the team building and testing the extractor. This version replaces v0.1. It is built from Jahnavi's hand labeling of all 320 sample articles (rows 1 to 320) and from `labeling/LABELING_PROCESS_LEARNINGS.md` (sections 12, 17 and 18). Every rule below was applied by hand on real articles; the rows in brackets show where.

## How it is used

For each article the program sends one request made of three parts, in this order:

1. The **instructions** (section 1)
2. The **examples** (section 2), 14 solved articles with the human answers
3. The **article** to process (section 3)

The LLM replies with one JSON object (section 4). Ask for it in the API's structured-output (JSON schema) mode.

---

## 1. Instructions (copy as is)

```
You read one news article and fill in a flu record. Follow the steps in order.

STEP 1. FIND THE ARTICLE DATE.
Use the first that exists:
 a) a date printed in the article text (a "Published ..." line, a dateline, a "First Published" line)
 b) a date in the link (for example /2024/06/19/ or -20240619-)
 c) the scan date given with the article
Report the date as YYYY-MM-DD and say which source you used ("printed", "link" or "scan_date").
Every relative word ("yesterday", "on Tuesday", "last week") is worked out from this date.
Do not use dates from your own knowledge to invent a reporting week or a holiday date.

STEP 2. DECIDE IF THE ARTICLE IS USEFUL.
Useful means the article says something about HUMAN flu that covers a period at or near the article date:
 - people with flu now: cases, deaths or hospital admissions, even one named person or a small group
   (for example two ministers with flu), even when the article is mainly about something else
 - the level or direction of flu for a named place now: rising, falling, peaking, low, high,
   widespread, an epidemic declared, an early or bad season, "first case of the year"
 - a flu season that is active at the article date. Counts that ended a few days before the article
   count when the article shows the season is still going (for example June counts in an article from
   July 10 that says the season starts in July). Counts that ended months earlier do not.
 - human cases of bird flu, swine flu or other flu strains (H5N1, H7N9, H9N2, ...) with a place
 - suspected flu (see Status in step 3), including flu-like illness when the article gives no other cause
Not useful (useful = false):
 - flu only in a list, comparison, metaphor, nickname or figure of speech
   ("Spanish flu", "a little flu", "Kung flu", "like the flu"), a symptom or remedy mention,
   a product, drug, vaccine-development, investment or business item
 - vaccination, awareness, advice, tips, clinics, vaccine coverage
 - other diseases: COVID-19, RSV, dengue, measles, norovirus, "stomach flu", "gastric flu", cat flu,
   Hib ("haemophilus influenzae"); and cold, cough or fever illnesses where the article names another
   cause or test (dengue, malaria, COVID)
 - flu in animals only (poultry, cattle, dogs, horses, cats, wild birds, lab mice) with no human cases
 - forecasts, predictions, preparedness, "the season is coming", "expected to rise"
 - past seasons, past years, the 1918 pandemic, annual totals for a year that has closed, studies and
   reports about past periods, and counts that ended months before the article
 - stories that may be old events retold (undated personal stories), unless they give current facts
 - text that does not mention flu, error pages, page fragments, listings of unrelated headlines
If you are not sure which way it goes, choose your best label and set borderline = true with a short
reason. Borderline examples: human bird flu cases as the main story, an undated single case, a
self-reported case, "this year" with no direction, a fresh announcement of an old case, loose terms
like "common flu", a prediction that says the season is now underway.
If useful is false, return an empty items list. Still return findings (step 7) if the article has any.

STEP 3. PULL OUT THE ITEMS (only if useful).
Write one item for each statement about cases, deaths, hospitalizations or the trend of flu.
Allowed kinds are exactly: "cases", "deaths", "hospitalized", "trend". There is no other kind.
Fields of an item:
 - kind
 - strain: as the article words it for THAT item ("swine flu", "H1N1", "bird flu", "H5N1"); null if none
 - number: a whole number only if the article gives one. "More than 120" is 120. Never guess. A
   percentage or ratio is never a number (put it in words on a trend item). Do not add numbers up.
 - status: "confirmed" or "suspected" or null
 - total_or_new: "total" for running totals ("so far", "since", "to date", "year to date", a toll),
   "new" for a newly reported event or number on a date, null if not stated
 - city, state, country, start_date, end_date, words, evidence, inferred (below)

Choosing the kind and avoiding double counting:
 - One patient or event gives one item. If a person is diagnosed, admitted and dies on the SAME day,
   keep only the most severe (deaths over hospitalized over cases). If the events are on DIFFERENT
   days, write separate items.
 - Never write two items of the same kind that overlap. If a total and its parts are both given
   (58 in the USA, 32 in California, one child), keep only the broader total. Different places that
   are not parts of one total are separate items.
 - A death whose cause is not yet confirmed as flu is not a deaths item. Record the positive test as a
   cases item instead.
 - "Patients affected" at a hospital is cases, unless the sentence says admitted or hospitalized.
 - A statement that people are dying or falling ill in a named place with no count is a trend item,
   not a deaths item with no number.
 - Do not record: vaccination figures, age shares, case-fatality rates, past events that the article
   does not tie to the current one, patient details (age, home town, pregnancy), animal outbreaks,
   forecasts, COVID or other-disease numbers.
 - Roundup and briefing pages: a line printed next to a flu item belongs to it only if it refers to
   flu (same event, same place). Read what the line is about before using it.

Trend items:
 - words: copy the article's own words ("seasonal influenza is increasing statewide", "ramping up",
   "Activity is low", "33 per cent rise", "one of the worst flu seasons in years").
 - A trend shows growth, decline, a stable or low level, or a declared or ongoing status. Low
   activity is a current signal. A season that the article shows is active at the article date is a
   trend whose end_date is the article date.
 - words is used ONLY on trend items. Leave it null on cases, deaths and hospitalized.

Status:
 - A reported case of a named flu strain ("a case of swine flu", "tested positive for H1N1",
   "diagnosed") is "confirmed" unless the text hints it is suspected, probable or negative.
 - "Suspected", "samples sent", "report awaited" is "suspected".
 - Flu-like illness (cold, cough, fever) that the article reports for named people or a place, with
   NO other cause or test named, may be written as a cases item with status "suspected", strain null,
   number only if given. If the article names another cause or test (dengue, malaria, COVID), do not.
 - Deaths: "suspected" if the death is suspected to be flu-related; "confirmed" if the text says flu
   was confirmed; otherwise null.

STEP 4. PLACES.
 - country must be a real country ("USA", "India", "Australia"). state must be a real state or
   province. city must be a real city. Anything else goes null. Never put "global", "worldwide",
   "Africa", "Northern Hemisphere", "Asia" or "Europe" in a place field.
 - A territory uses its sovereign country: Guam and American Samoa are USA; French Polynesia and
   New Caledonia are France; Hong Kong and Macau are China.
 - A county is not a city: use a same-named city only if one exists (Santa Barbara), otherwise null.
 - The city is where the cases or hospital are, not the patient's home town. A hospital's suburb or
   city counts. A region such as "Central Coast" is not a city.
 - A place the article does not name may be filled in only when you are certain it is real and
   follows from the places the article names (Kolkata is in West Bengal, India). List the fields you
   filled this way in "inferred" (for example ["state","country"]).
 - For every place field that is stated or inferred, include in evidence a sentence that supports it
   when one exists (a headline, a dateline, a sentence naming the region or agency).
 - A national agency's statement (the CDC, a ministry of health) gives a country and no state.

STEP 5. DATES FOR EACH ITEM (start_date, end_date, YYYY-MM-DD).
 - A single day (an event, a death, "yesterday", "on Tuesday"): start and end are the same day.
 - A newly reported case or event with no time wording: the article date for both.
 - "today": the article date. "yesterday": the article date minus 1.
 - "on Tuesday" or "last Tuesday": the most recent Tuesday before the article date. Use a date the
   article states for that day if there is one.
 - "last week": the Monday to Sunday week before the article's week.
 - "this week" or "earlier this week" for one event: one day of that week (use the Monday); "in the
   last week" or "in the past week" for a count or rise: the Monday of the article's week to the
   article date. "The week ending <day>" and "week-on-week" in a weekday report: the 7 days ending
   that day. "The past N weeks": the article date minus N weeks, to the article date.
 - "in July", "in February": the whole month. "Last month": the whole previous calendar month.
   "Over the last three months": the three full calendar months before the article's month.
   "The first fortnight of April": April 1 to April 14.
 - "since <date>": start is that date, end is the article date. "Stats from <date>" with no end:
   same. "As of <date>": end is that date, start null (unless the text says "this year").
 - "So far this year", "since January", "year to date": start is January 1 of the article's year,
   end is the article date or the stated update date. "This season", "so far this season":
   start null, end is the article date.
 - "About two weeks back": the article date minus 14 days for both dates.
 - A running total up to a day ("until Wednesday", "as of Oct. 8"): end is that day, start null.
 - A week number ("EpiWeek 18") only if the article states the calendar range for that week;
   then copy that range and include the sentence with the range in evidence.
 - A forecast ("expected to rise for several weeks") is never the period of a count.
 - If you cannot work a date out from the article, use null.

STEP 6. EVIDENCE.
 - evidence is a list of strings. Each string is copied exactly from the article, whole sentences,
   including typos, odd spacing and broken characters as printed.
 - Put the parts in the order they appear in the article. Never join sentences yourself.
 - Include a supporting part for any inferred or distant place (rule in step 4) and for any
   date that comes from a different sentence (for example a date range for a week number).
 - Headline and bullet lines printed above the story may be used exactly as printed.
 - Every part must be found in the article. An item whose evidence is not found is an error.

STEP 7. FINDINGS.
If the article states when the flu season starts, ends, how long it lasts, or when it peaks for a
place, return it as a finding with the country and the sentence copied exactly. Do this even when
the article is not useful. A forecast for the current year ("will peak in late August") is not a
finding. Year-specific statements ("last year it peaked in early December") are not findings.

STEP 8. REPLY with the JSON only.
```

---

## 2. Examples (solved articles; the answers are the human labels)

The 14 examples cover: a first case of the year, a named death with a stated day, an active-season
article with a count and a trend, two cases plus an outbreak trend, a toll and a death, a small group
in an article about another disease, human bird flu deaths, an ongoing-season statement, a statewide
trend, and six `useful = false` articles including one borderline. They were taken from rows of
`Jahnavi_labels.csv`; the answers are copied from `Jahnavi_items.csv` and `Jahnavi_findings.csv`.

### Example 1

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
  "article_date": "2018-07-31",
  "article_date_source": "scan_date",
  "useful": true,
  "borderline": false,
  "reason": "First swine flu case of the year reported in Kolkata two days before the article.",
  "items": [
    {
      "kind": "cases",
      "strain": "swine flu",
      "number": 1,
      "status": "confirmed",
      "total_or_new": "new",
      "city": "Kolkata",
      "state": "West Bengal",
      "country": "India",
      "start_date": "2018-07-30",
      "end_date": "2018-07-30",
      "words": null,
      "evidence": [
        "KOLKATA: In the wake of the yearâs first swine flu case, reported by The Times of India on Monday"
      ],
      "inferred": [
        "state",
        "country"
      ]
    }
  ],
  "findings": []
}
</example>

### Example 2

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
  "article_date": "2017-12-04",
  "article_date_source": "scan_date",
  "useful": true,
  "borderline": false,
  "reason": "A named woman died of flu on a stated day in Phoenix.",
  "items": [
    {
      "kind": "deaths",
      "strain": null,
      "number": 1,
      "status": null,
      "total_or_new": "new",
      "city": "Phoenix",
      "state": "Arizona",
      "country": "USA",
      "start_date": "2017-11-28",
      "end_date": "2017-11-28",
      "words": null,
      "evidence": [
        "Alani \"Joie\" Murrieta, a 20-year-old mother of two from Phoenix, Arizona, died last Tuesday — only one day after being diagnosed with the flu.",
        "Murrieta arrived at the hospital around 7 a.m. and was declared dead at 3:25 p.m. on Tuesday, Nov. 28, 2017."
      ],
      "inferred": []
    }
  ],
  "findings": []
}
</example>

### Example 3

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
  "article_date": "2017-07-10",
  "article_date_source": "scan_date",
  "useful": true,
  "borderline": false,
  "reason": "June cases and an ongoing bad season, published ten days after the month ended; the article says the season starts in July, so the season is active.",
  "items": [
    {
      "kind": "cases",
      "strain": null,
      "number": 88,
      "status": "confirmed",
      "total_or_new": "total",
      "city": null,
      "state": "New South Wales",
      "country": "Australia",
      "start_date": "2017-06-01",
      "end_date": "2017-06-30",
      "words": null,
      "evidence": [
        "While the traditional “flu season” usually kicks off in July, Central Coast Local Area Health has already recorded 88 flu cases last month compared to 16 in June, 2016."
      ],
      "inferred": [
        "state",
        "country"
      ]
    },
    {
      "kind": "trend",
      "strain": null,
      "number": null,
      "status": null,
      "total_or_new": null,
      "city": null,
      "state": "New South Wales",
      "country": "Australia",
      "start_date": "2017-06-01",
      "end_date": "2017-07-10",
      "words": "one of the worst flu seasons in years",
      "evidence": [
        "THIS winter is shaping up as one of the worst flu seasons in years with five and a half times the number of confirmed cases last month than the same period last year.",
        "“Flu vaccines used in Australia are made with vaccine viruses that have been ‘inactivated’ so they are not infectious,” he said."
      ],
      "inferred": [
        "state",
        "country"
      ]
    }
  ],
  "findings": [
    {
      "country": "Australia",
      "finding": "While the traditional “flu season” usually kicks off in July"
    }
  ]
}
</example>

### Example 4

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
  "article_date": "2023-02-04",
  "article_date_source": "scan_date",
  "useful": true,
  "borderline": false,
  "reason": "Swine flu cases among students at one college in the two weeks before the article.",
  "items": [
    {
      "kind": "cases",
      "strain": "swine flu",
      "number": 1,
      "status": "confirmed",
      "total_or_new": "new",
      "city": "Godhra",
      "state": "Gujarat",
      "country": "India",
      "start_date": "2023-01-21",
      "end_date": "2023-01-21",
      "words": null,
      "evidence": [
        "Several students at the Godhra GMERS Medical College were advised to rest and some were also allowed to go home after swine flu cases were reported among them.",
        "According to sources, the first case of swine flu was reported about two weeks back in the college."
      ],
      "inferred": [
        "state",
        "country"
      ]
    },
    {
      "kind": "cases",
      "strain": "swine flu",
      "number": 1,
      "status": "confirmed",
      "total_or_new": "new",
      "city": "Godhra",
      "state": "Gujarat",
      "country": "India",
      "start_date": "2023-01-30",
      "end_date": "2023-01-30",
      "words": null,
      "evidence": [
        "Several students at the Godhra GMERS Medical College were advised to rest and some were also allowed to go home after swine flu cases were reported among them.",
        "One more student tested positive earlier this week even as others were found suspicious along with this student too."
      ],
      "inferred": [
        "state",
        "country"
      ]
    },
    {
      "kind": "trend",
      "strain": "swine flu",
      "number": null,
      "status": null,
      "total_or_new": null,
      "city": "Godhra",
      "state": "Gujarat",
      "country": "India",
      "start_date": "2023-01-21",
      "end_date": "2023-02-04",
      "words": "several students with swine flu",
      "evidence": [
        "Several students at the Godhra GMERS Medical College were advised to rest and some were also allowed to go home after swine flu cases were reported among them."
      ],
      "inferred": [
        "state",
        "country"
      ]
    }
  ],
  "findings": []
}
</example>

### Example 5

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
  "article_date": "2021-08-18",
  "article_date_source": "scan_date",
  "useful": true,
  "borderline": false,
  "reason": "A tourist death on a Wednesday and a state toll; the article has no printed date, so the scan date is used.",
  "items": [
    {
      "kind": "deaths",
      "strain": "swine flu",
      "number": 1,
      "status": "confirmed",
      "total_or_new": "new",
      "city": "Jodhpur",
      "state": "Rajasthan",
      "country": "India",
      "start_date": "2021-08-18",
      "end_date": "2021-08-18",
      "words": null,
      "evidence": [
        "JODHPUR, India – A 70-year-old foreign tourist has died of swine flu in Jodhpur as the toll in Rajasthan has gone up to more than 120.",
        "She was put on the ventilator but died on Wednesday morning."
      ],
      "inferred": []
    },
    {
      "kind": "deaths",
      "strain": "swine flu",
      "number": 120,
      "status": "confirmed",
      "total_or_new": "total",
      "city": null,
      "state": "Rajasthan",
      "country": "India",
      "start_date": null,
      "end_date": "2021-08-18",
      "words": null,
      "evidence": [
        "JODHPUR, India – A 70-year-old foreign tourist has died of swine flu in Jodhpur as the toll in Rajasthan has gone up to more than 120."
      ],
      "inferred": []
    }
  ],
  "findings": []
}
</example>

### Example 6

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
  "article_date": "2022-08-01",
  "article_date_source": "scan_date",
  "useful": true,
  "borderline": false,
  "reason": "The article is about monkeypox, but it states that two named ministers currently have flu.",
  "items": [
    {
      "kind": "cases",
      "strain": null,
      "number": 2,
      "status": "confirmed",
      "total_or_new": "new",
      "city": null,
      "state": "Karnataka",
      "country": "India",
      "start_date": "2022-08-01",
      "end_date": "2022-08-01",
      "words": null,
      "evidence": [
        "Meanwhile, Minister for Cooperation ST Somashekar and Minister for Municipal Administration N Nagaraju have been down with an illness.",
        "Sudhakar clarified, “Both the ministers are having symptomatic flu . Both have undergone Covid tests and both of them are negative. They are doing fine and are being treated for flu.”"
      ],
      "inferred": [
        "state",
        "country"
      ]
    }
  ],
  "findings": []
}
</example>

### Example 7

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
  "article_date": "2016-12-31",
  "article_date_source": "scan_date",
  "useful": true,
  "borderline": false,
  "reason": "Human bird flu deaths are reported in recent weeks, inside a story about egg exports.",
  "items": [
    {
      "kind": "deaths",
      "strain": "bird flu",
      "number": 3,
      "status": "confirmed",
      "total_or_new": "total",
      "city": null,
      "state": null,
      "country": "China",
      "start_date": null,
      "end_date": "2016-12-31",
      "words": null,
      "evidence": [
        "Strains of bird flu, which can be spread to poultry by wild birds, have been detected across Asia and in Europe in recent weeks. Two people in China and one person in Hong Kong have died in the outbreaks."
      ],
      "inferred": []
    }
  ],
  "findings": []
}
</example>

### Example 8

<example>
Scan date: 2023-11-07
Link: https://www.redriverradio.org/news/2023-11-07/flu-shot-urged-as-cdc-reports-first-pediatric-deaths
Article:
The Centers for Disease Control and Prevention [CDC], confirms the first pediatric flu deaths of the 2023-24 season in the United States. The CDC urges people not to delay getting their vaccinations. But the agency reports that by mid-October fewer than 23% of adults and just under 21% of children had received their flu shot.
Peak flu season typically begins in December and ends in February. The CDC recommends that everyone six months and older - with very rare exceptions - gets a flu vaccine every season.
The acting director of the CDC’s National Center for Immunization and Respiratory Disease is Dr. Demetre Daskalakis. He recalls the last flu season [2022-23], which became the most severe we’ve had since the start of the covid-19 pandemic. “It started earlier than usual. So, when we think about the flu, it usually peaks in February. But last year, we actually had a surge in October. And we peaked in early December. And that really resulted in flu hospitalization rates that were the highest that we've seen in at least a decade.”
Dr. Daskalakis Says it's important to remember that even healthy children can get sick from flu. When you look back at last season, there were 174 pediatric deaths from the flu reported to the CDC. Eighty percent of those children were not vaccinated against the flu.
For more information visit: American Medical Association/AMA Update. Https://youtu.be/tyqi6vsf1fq?Si=TH_snotljubeb26d

Answer:
{
  "article_date": "2023-11-07",
  "article_date_source": "link",
  "useful": true,
  "borderline": false,
  "reason": "CDC confirms the first pediatric flu deaths of the 2023-24 season, so the season is ongoing.",
  "items": [
    {
      "kind": "trend",
      "strain": null,
      "number": null,
      "status": null,
      "total_or_new": null,
      "city": null,
      "state": null,
      "country": "USA",
      "start_date": null,
      "end_date": "2023-11-07",
      "words": "ongoing flu season",
      "evidence": [
        "The Centers for Disease Control and Prevention [CDC], confirms the first pediatric flu deaths of the 2023-24 season in the United States."
      ],
      "inferred": []
    }
  ],
  "findings": [
    {
      "country": "USA",
      "finding": "Peak flu season typically begins in December and ends in February."
    }
  ]
}
</example>

### Example 9

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
  "article_date": "2018-12-07",
  "article_date_source": "scan_date",
  "useful": true,
  "borderline": false,
  "reason": "Oregon health authority says influenza is increasing statewide today.",
  "items": [
    {
      "kind": "trend",
      "strain": null,
      "number": null,
      "status": null,
      "total_or_new": null,
      "city": null,
      "state": "Oregon",
      "country": "USA",
      "start_date": "2018-12-07",
      "end_date": "2018-12-07",
      "words": "seasonal influenza is increasing statewide",
      "evidence": [
        "OREGON CITY, Ore. — Local public schools are starting to see an uptick in flu cases as the Oregon Health Authority says seasonal influenza is increasing statewide."
      ],
      "inferred": []
    }
  ],
  "findings": [
    {
      "country": "USA",
      "finding": "Flu season usually runs November through April or May, with peak illnesses reported between December and February."
    },
    {
      "country": "USA",
      "finding": "It always does, usually in February or March -- sometimes earlier."
    }
  ]
}
</example>

### Example 10

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
  "article_date": "2016-12-22",
  "article_date_source": "scan_date",
  "useful": false,
  "borderline": false,
  "reason": "Letter about vaccinating seniors; no current flu activity.",
  "items": [],
  "findings": []
}
</example>

### Example 11

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
  "article_date": "2022-12-23",
  "article_date_source": "printed",
  "useful": false,
  "borderline": false,
  "reason": "Children have cold, cough and fever, but the article names other causes and tests (dengue, malaria, COVID); flu is not named as the cause.",
  "items": [],
  "findings": []
}
</example>

### Example 12

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
  "article_date": "2023-01-13",
  "article_date_source": "printed",
  "useful": false,
  "borderline": false,
  "reason": "Bird flu in poultry only; no human cases.",
  "items": [],
  "findings": []
}
</example>

### Example 13

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
  "article_date": "2015-08-03",
  "article_date_source": "scan_date",
  "useful": false,
  "borderline": false,
  "reason": "The 209 hospitalized patients were counted January to March; the article is from August and is about treatment costs.",
  "items": [],
  "findings": []
}
</example>

### Example 14

<example>
Scan date: 2024-11-07
Link: https://www.yahoo.com/news/dairy-workers-may-bird-flu-212519531.html
Article:
- CDC reports 46 farmworkers diagnosed with bird flu this year, some infected workers never felt sick, prompting expanded testing recommendations.
Dairy workers who've been exposed to bird flu should be tested for the virus even if they don't have symptoms and be offered Tamiflu to cut their risk of getting sick, the Centers for Disease Control and Prevention said Thursday.
The recommendation coincides with a new report finding asymptomatic bird flu infection in some workers. Those cases were discovered using blood, or serology, testing and seem to have been transmitted from sick animals, not people.
"There is nothing that we've seen in the new serology data that gives us any concern about person-to-person transmission," Dr. Nirav Shah, the CDC's principal deputy director, said during a media briefing.
To date, 46 people have been diagnosed with bird flu, also known as H5N1, in the United States this year. All but one of those patients had been exposed to sick cattle or poultry on farms.
Most cases have been reported in California (21), Washington (11) and Colorado (10).
The new CDC study looked at blood tests from workers at 115 dairy farms who were exposed to H5N1 over the summer in either Colorado or Michigan.
Of those 115, eight (7%) had antibodies showing they'd been infected with the bird flu.
"All eight reported milking cows or cleaning the milking parlor," Dr. Demetre Daskalakis, who heads the CDC's National Center for Immunization and Respiratory Diseases, said during the call. Masks and safety goggles were rare.
"None wore respiratory protection, and less than half wore eye protection," Daskalakis said.
Most of those found with H5N1 said they'd had red, itchy eyes with drainage.
But four of the eight who were infected didn't recall ever being sick.
Until now, workers who had a known exposure to bird flu but didn't have symptoms haven't been routinely tested. The new results clearly show cases have been missed — a concern that veterinarians have had since the spring.
The CDC is now "intensifying" recommendations meant to protect farmworkers, Shah said. "We in public health need to cast a wider net in terms of who is offered a test so that we can identify, treat and isolate those individuals," he said.
The new advice is to test anyone with a significant bird flu exposure, such as an unprotected worker who's been splashed in the face with raw milk on a dairy farm with known H5N1 infections in the herds.
Even if the person never feels ill, that worker should be tested and given the antiviral drug Tamiflu to reduce their risk of ever developing symptoms or passing the virus to close contacts.
It was unclear Thursday where the money for extra tests would come from, but a CDC spokesman said the cost would not fall on individual farms.
This is a move the CDC should have made months ago, said Jennifer Nuzzo, director of the Pandemic Center at the Brown University School of Public Health.
"We've always suspected strongly and now have confirmation that that was going to miss people who are infected," Nuzzo said. "This is very bad because one of these infections could turn out to be serious."
All the H5N1 cases reported so far this year have been mild, including pinkeye and some minor coughs or sneezes. No one has died.
That runs counter to previous H5N1 mortality rate estimates from other parts of the world suggesting more than half of those who become infected die.
Daskalakis said that could be because "not all H5N1s are built the same. These are potentially different genotypes."
There is no indication that the commercial milk or beef supplies have been affected, the Food and Drug Administration has said.
This article was originally published on NBCNews.com

Answer:
{
  "article_date": "2024-11-07",
  "article_date_source": "scan_date",
  "useful": false,
  "borderline": true,
  "reason": "Human H5N1 cases among US dairy workers are reported with counts, but they are avian flu in farm workers rather than seasonal flu; a careful reader could go either way.",
  "items": [],
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

## 4. Reply shape

```
{
  "article_date": "YYYY-MM-DD",
  "article_date_source": "printed" | "link" | "scan_date",
  "useful": true or false,
  "borderline": true or false,
  "reason": one short sentence,
  "items": [
    {
      "kind": "cases" | "deaths" | "hospitalized" | "trend",
      "strain": text or null,
      "number": whole number or null,
      "status": "confirmed" | "suspected" | null,
      "total_or_new": "total" | "new" | null,
      "city": text or null,
      "state": text or null,
      "country": text or null,
      "start_date": "YYYY-MM-DD" or null,
      "end_date": "YYYY-MM-DD" or null,
      "words": text or null,          (trend items only)
      "evidence": [text, ...],        (exact parts, in article order)
      "inferred": ["state", "country", ...]
    }
  ],
  "findings": [ { "country": text, "finding": exact sentence } ]
}
```

If `useful` is false, `items` is an empty list. `findings` may still have entries.
When the program saves a result into the labeling sheets, `evidence` parts are joined with a line
containing `||`, and `reason`, `borderline`, `inferred` and `article_date_source` go into extra
columns (they are not in the human sheets).

---

## 5. How to check and improve it

1. Run it on the development rows only, never on the locked test set. The 14 example rows must be
   removed from the development set used for scoring (their answers are in the prompt).
2. Score by item, not by article. Match an item when kind, place, strain and the dates agree; report
   precision, recall and F1 per kind. Score `useful` separately (precision, recall, and the rate of
   borderline flags among the human recheck rows).
3. Automatic checks: (a) every evidence part occurs in the article; (b) `words` is null unless the kind
   is trend; (c) only the four kinds appear; (d) place fields are real values and no region words;
   (e) start_date is not after end_date; (f) no two overlapping items of the same kind.
4. Look first at: usefulness errors (the labeled sample is about 24% useful, so over-calling is the
   likeliest failure), date arithmetic, and overlapping items.
5. Change one rule or one example at a time and record it as v1.1, v1.2, ...

## 6. Notes on this version

- The examples must not be test-set articles. Confirm the 14 rows against the team's test-set list before use.
- Rows 109 and 152 of the human sheet have no label (no team opinion yet); they are not used here.
- Known soft spots, still undecided by the team (see `LABELING_PROCESS_LEARNINGS.md`, section 18.6):
  the window for "near the article date"; how to aggregate nested totals; whether human bird flu
  (rows 252, 308, 309, 310) and "common flu" (row 212) count; worldwide statements (row 109).
- For few-shot use, keep the 14 examples in this order (positive cases first, negatives last). If the
  context is short, drop examples 3 and 8 first, then 12.
