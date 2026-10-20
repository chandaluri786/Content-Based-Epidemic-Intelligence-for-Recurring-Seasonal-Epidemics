# Sampling and Labeling Guide

Written for: the labeling team, and anyone writing or checking the LLM extraction prompt. Sections 2 and 3 are the rulebook. The prompt copies its rules from here, so change a rule here first.

## 1. Goal

Pick 1,200 news articles, label them by hand, and use the labels to test an LLM that does two jobs:

1. Decide whether an article is useful.
2. For useful articles only, pull out the flu information in the text.

The extracted information is used later to find when a flu season starts.

## 2. Which articles are useful

The article date is the **scan date**. Use it even when the article or its link shows another date.

An article is **useful** if it has at least one item that passes every rule in sections 2 and 3. Otherwise it is not useful. So a `yes` article always has items, and a `no` article never has any.

### 2.1 What counts

A current statement about flu in people, in a named country. It is one of these:

1. **People ill with flu:** cases, deaths or hospital admissions. At least one person ill with flu of any strain is enough (seasonal flu, swine flu, bird flu, H5N1, H9N2). The first case or first death of the year counts. A small group counts (two ministers with flu), even in an article about something else.
2. **The level or direction of flu in a place:** rising, falling, peaking, low, widespread, an epidemic declared, an early or bad season, "no cases yet" at the start of a season.
3. **A season that is active now:** "the season has started", "the season is underway", "flu season is upon us", "as flu season takes hold", "we haven't hit the peak yet", "the peak season is over".
4. **Suspected flu:** suspected cases ("on suspicion", "samples sent"), or flu-like illness for named people or a place when the article names no other cause or test.
5. **Which strain is going around:** "86% of positive samples were H1N1", when it is about one country and is current.

Human cases of animal flu count (H5N1 in a farm worker, H9N2 in a child).

### 2.2 What does not count

- flu in animals only (poultry, cattle, dogs, wild birds)
- illnesses that are not flu: "stomach flu", norovirus, cat flu, Hib ("haemophilus influenzae"), and cold-type illness where the article names another cause or test (dengue, malaria, COVID)
- an unexplained illness that the article describes only as "flu-like" while officials are still finding the cause (a "mystery illness" under investigation) is not suspected flu
- flu named only in passing: in a list, a comparison, a metaphor, a nickname ("Spanish flu", "Kung flu"), a symptom or drug side effect, a photo caption, or a business, investment or vaccine-development remark
- prevention only: vaccination, tips, clinics, vaccine coverage. A prevention article that also gives a current flu statement is useful; only that statement is recorded.
- forecasts: "the season is coming", "could be severe", "may peak in January", "likely to increase"
- risk statements: "the risk to humans is low", "no person-to-person spread"
- general seasonal facts: "flu usually peaks in winter", "the season runs from October to April"
- the past (section 2.3)
- worldwide or regional statements with no country ("the southern hemisphere", "across Asia")
- an undated personal story that may be an old event retold, or an old event mentioned as background ("Tensions were heightened when a child … was confirmed")
- illness or hospital demand in general that the article does not tie to flu or flu-like illness ("a surge in viral illnesses", "rising demand for medical attention")
- spam, ads, and pages whose text does not match the link (the page changed after it was collected)

An article that has these and also a current statement is still useful. The others are just not recorded.

**Other diseases.** An article mainly about COVID-19, RSV or dengue is useful only if it has its own current flu statement. Never record the other disease's numbers, or a figure that mixes flu with another disease ("a 30% rise in influenza and RSV"). A statement that flu itself is rising alongside other viruses is still a flu trend ("a surge in RSV and the flu and Covid").

**Mixed sentences.** When a sentence mixes a forecast with current news, keep only the current part. "Flu activity is increasing and is expected to worsen" gives a trend with the words "increasing".

### 2.3 How recent is current

Check every item twice. Keep it only if it passes both.

1. **Did the period end recently?** The article date minus `end_date` must be 30 days or less. Measure from the **end** of the period. A running total that ends now is current, however long ago it started ("since January, 170 tested positive").
2. **Is its period a completed calendar year or a completed flu season?** If yes, it is past, even if it ended a few days before the article. This catches year-in-review numbers. A statement about today that the season is over ("the peak season is over") is a current trend and passes.
   - Finished: "last year", "in 2015", "last season", "last winter", "the 2017–18 season", "the season ended with 300 deaths".
   - Ongoing, so it passes: "so far this year", "this season", "since September 1", "to date".
   - Check 2 is only about a whole year or season. "Last month" and "over the last three months" only need check 1.

| Article date | Statement | Check 1 | Check 2 | Result |
|---|---|---|---|---|
| 2016-01-05 | "Last year, the city reported 2,200 cases" | 5 days, passes | 2015 is over | drop |
| 2015-12-20 | "So far this year, 2,200 cases" | 0 days, passes | still running | keep |
| 2017-07-10 | "88 cases last month" | 10 days, passes | not a year or season | keep |
| 2015-08-03 | "209 patients, January to March" | 125 days, fails | | drop |
| 2016-01-29 | "The peak season of the flu is over" | a statement about today | not a count | keep (trend) |

More cases:

- **Comparison numbers** are items like any other, if each passes both checks. "2,000 cases this week, compared with 1,024 the previous week" keeps both. A comparison with last year or an earlier season never passes: "compared with 6,449 in the same week in 2017" drops the 6,449.
- **An old case announced late** is dropped when the event itself ended more than 30 days before the article.

## 3. What to pull out of a useful article

Write one item for each statement. Copy the article's facts. Never guess.

### 3.1 Kinds

There are exactly four kinds: `cases`, `deaths`, `hospitalized`, `trend`.

- **deaths:** the article links the death to flu. If the person had confirmed flu but the cause of death is unknown or "yet to be categorised", write a `cases` item and no `deaths` item. If the article does not show the person had flu, leave the death out.
- **hospitalized:** admitted, in hospital, in intensive care, isolated in a hospital. A patient who has gone home from hospital is still `hospitalized`. Emergency visits and "patients affected" at a hospital are `cases`, unless the sentence says admitted or hospitalized.
- **trend:** what flu is doing: rising, falling, stable, low, declared, ongoing, or which strain dominates.
- **A statement with no count becomes a trend.** "People are dying of swine flu in Gujarat" is a trend in Gujarat, not a deaths item with no number.
- **"No cases yet" is a trend**, never a count of 0.

### 3.2 Fields

| Field | Rule |
|---|---|
| strain | The article's own term for this item ("swine flu", "H1N1", "influenza A", "bird flu"). If the same sentence gives both a name and a subtype code, use the code. If the article gives two strains for the same item, write them as it does ("Influenza A & B"). Never list strains from elsewhere in the article. Empty if none. Do not correct the article; names are matched up when scoring. |
| number | A whole number, only if the article gives one. "More than 120" is 120. Vague amounts ("a couple of deaths", "nearly three dozen", "dozens") are not numbers: the statement becomes a trend. Never add or subtract numbers. A percentage or ratio is never a number; it goes in `words`. Trend items have no number. |
| status | Section 3.3. |
| total_or_new | `total` for running totals ("so far", "since", "to date", "a toll") **and** for any count over a stated period ("last week", "last month", "the week ending 7 May", "in the past 10 days"). `new` for a single newly reported event, even when its day is only known to a period ("a child died last week"). Empty for trend items. |
| city, state, country | Section 3.5. |
| start_date, end_date | Section 3.6. YYYY-MM-DD. |
| words | Trend items only. Use the article's own phrase when it has one ("seasonal influenza is increasing statewide", "rose by 38 per cent"). When the trend runs over several sentences, write a short plain summary ("no cases received so far this season"). A summary must not add facts. |
| evidence | Whole sentences copied word for word, typos included. Several parts go in article order, joined by ` \|\| `. If the place or the date comes from a different sentence, add that sentence too. If a city, state or country was worked out and is not in the item's own sentence, add the sentence that supports it. Do not add sentences that only give background, forecasts or past numbers. |

### 3.3 Status

| Kind | `confirmed` | `suspected` | empty |
|---|---|---|---|
| deaths | a strain is named for the death ("died of swine flu", "an H1N1 death") | the article says the death is suspected or still being investigated | otherwise ("a flu death") |
| cases | a named strain is reported ("a case of swine flu"), or the text says confirmed, lab-confirmed, tested positive or diagnosed | "suspected", "on suspicion", "samples sent", "report awaited", or flu-like illness with no other cause named | otherwise ("416 reports of flu cases") |
| hospitalized | | the article says the patients are suspected ("isolated on suspicion"), or they have flu-like illness | otherwise |
| trend | | | always |

### 3.4 Counting each thing once

- **One patient, same day:** keep only the most severe kind (deaths over hospitalized over cases). On different days, write separate items.
- **A new event next to its running total:** keep both. `total_or_new` tells them apart. "A tourist died on Wednesday as the state toll rose to more than 120" gives deaths 1 `new` and deaths 120 `total`.
- **A total next to its parts:** keep only the broader total. "58 human cases in the USA, 32 of them in California" gives only the 58. Parts can be places (cities inside a state total) or groups (an age group, the patients of one hospital inside the state's count).
- **Suspected next to confirmed:** when "183 suspected cases, of which 57 were positive" or "43 samples, two positive" are given, keep the confirmed count. The suspected total includes them.
- **Separate places that are not parts of one total** are separate items. "Two people in China and one person in Hong Kong died" gives deaths 2 (China) and deaths 1 (China, city Hong Kong). Never add them up.
- **Round-up pages:** a line printed next to a flu item belongs to it only if it is about the same flu event.
- **Never record:** vaccination figures, age shares, death rates ("half of those infected die"), patient details (age, home town), animal outbreaks, or other diseases' numbers.

### 3.5 Places

- **country** is always filled, and must be a real country. Write the United States as `USA` and other countries in full (`India`, `Australia`).
- **Territories** go under their country: Hong Kong and Macau are `China` (city `Hong Kong`, `Macau`); Guam and American Samoa are `USA`; French Polynesia and New Caledonia are `France`.
- **No country, no item.** Drop worldwide and regional items. Never put "global", "worldwide", a continent or a hemisphere in a place field.
- **state** is a real state or province. Fill it in from the city when you are certain (Houston is in Texas, Kolkata is in West Bengal). Fill in every place part you can work out with certainty from the places the article names; leave a part empty when you cannot be certain.
- **city** is where the cases or the hospital are, not the patient's home town. Use the city, not a suburb (Westmead is `Sydney`). A county is not a city unless a city of the same name exists. A region ("Central Coast") is not a city.
- **A national agency** (the CDC, a ministry of health) gives the country and no state.

### 3.6 Dates

Work dates out from the article date (the scan date). `start_date` is never after `end_date`, and `end_date` is never after the article date. If a date cannot be worked out, leave both empty.

- A single day (an event, a death, "yesterday", "on Tuesday"): start and end are the same day.
- A newly reported case or event with no time wording: the article date for both.
- "Today": the article date. "Yesterday": the article date minus 1.
- "On Tuesday" or "last Tuesday": the most recent Tuesday **on or before** the article date. If the article states the date of that day, use it.
- "Last week": Monday to Sunday of the week before the article's week.
- "This week" or "earlier this week" for one event: the Monday of that week, start and end the same.
- "In the last week" or "in the past week" for a count or a rise: the Monday of the article's week to the article date.
- "The week ending July 8": the 7 days ending that day. "The past N weeks": the article date minus N weeks, to the article date. "About two weeks back": the article date minus 14 days, for both dates.
- "In July": the whole month. "Last month": the whole previous calendar month. "Over the last three months": the three full calendar months before the article's month. "The first fortnight of April": April 1 to April 14.
- "Since April 3": that date to the article date. "Since March": March 1 to the article date. "Since last week": the Monday of last week to the article date. "As of Oct. 8", "till Monday": end is that day, start empty (unless the text says "this year").
- "So far this year", "since January", "year to date": January 1 of the article's year to the article date or the stated update date.
- "This season", "so far this season": start empty, end is the article date. A season shown to be active is a trend ending on the article date.
- A week number ("EpiWeek 18"): only if the article states that week's calendar range. Copy that range and add the sentence that gives it to the evidence. Never work a week's dates out yourself.

## 4. How the 1,200 are chosen

**Step 1. Clean the pool.**
- Remove exact duplicates. In our data 41% of the 36,508 articles are repeated text, so about 21,500 are unique.

**Step 2. Sort articles into likely useful and likely not useful using simple word rules.**
The rules only decide which articles go into which pile. They do not give the label. People give the label.

Likely useful: a flu sentence that has a number with cases or deaths, or says cases are rising, falling, widespread or low, or reports a flu death or hospitalization.
Likely not useful: no flu word, bird or animal flu, other diseases, vaccines and tips, research studies, business news, history, stomach flu or dog flu.

The link (URL) can help sort an article, but it is never the only reason to leave one out.

**Step 3. Draw the sample.**
- 600 from likely useful.
- 600 from likely not useful, drawn at random across its kinds (awareness, animal flu, other diseases, research, and so on) so the labelers see the realistic mix. About 120 of these come from articles that mention flu but matched none of the rules; this shows how many useful articles the rules missed.
- Spread the sample across all six countries (USA, Australia, Brazil, India, Kenya, Indonesia) and across 2015, 2016 and 2017. Take all available articles for countries with few (Kenya, Indonesia, Brazil).
- Within each country and year, include articles from early, middle and late in the flu season, because the early weeks matter most.

**Things to know:**
- The word rules are not perfect. From small checks, about 88% of the "number plus cases" group is really useful, but only about half of the "rising or falling" group is. So expect fewer than 600 useful articles after labeling, probably 430 to 480.
- Data exists only for the flu-season months of each country, not the whole year.
- Page text was downloaded in 2026, so some pages no longer match what was published. Label those not useful.

## 5. How to store the labeled data

Each labeler keeps two CSV files.

**`<you>_labels.csv`**, one row per article:

| Column | What goes in it |
|---|---|
| row, round, article_id, link, scan_date | Filled in already. |
| useful | `yes` or `no`, lower case. |
| causes | Leave empty. |
| labeler | Your name. |
| notes | Anything unclear, and why a label was changed. |

**`<you>_items.csv`**, one row per item, with the columns `article_id, strain, kind, number, status, total_or_new, city, state, country, start_date, end_date, words, evidence`. Keep the items in the same order as the `yes` articles in the labels file, with all of one article's items together.

Keep exactly these columns, with no extra ones. If you edit in Google Sheets, check the export: Sheets can turn `2024-12-20` into `12/20/2024` and `yes` into `Yes`, and both must be fixed back.

Example row (an article scanned on 2018-07-31):

```
20180731…-123,swine flu,cases,1,confirmed,new,Kolkata,West Bengal,India,2018-07-30,2018-07-30,,"KOLKATA: In the wake of the year's first swine flu case, reported by The Times of India on Monday"
```

### Why this form

It stays close to the article's words, and it lets later steps work without reading the text again:
- **Dates:** exact start and end dates let code group items by week directly.
- **Weekly counts:** `new` items are single events and can be added up by week and place. `total` items are not added together; a running total is compared with the previous report instead.
- **Trend words:** `words` are matched to a short list (rising, falling, peak, widespread, low) after labeling, not during it.
- **Checking:** `evidence` lets anyone confirm an item against the article.

How it is used:
- **Development set:** the few-shot examples in the prompt come from here, and the prompt is tuned on it.
- **Test set:** the answers are hidden from the LLM. It runs once at the end, and its `useful` and items are compared with the human answers.

## 6. Rule changes agreed on 2026-10-18

These change or sharpen the rules in `llm_extraction_prompt_v2.0.md`. Every labeling sheet has to follow them before the prompt is scored against it.

1. **Recency:** an item must end within 30 days of the scan date, and a finished year or season is always past (2.3). v2.0 only said "weeks or months earlier".
2. **Comparison numbers** are kept when they pass the recency checks, and dropped when they don't.
3. **Counts over a period are `total`.** A single event dated to a period stays `new`.
4. **Deaths status:** `confirmed` when a strain is named, otherwise empty.
5. **Cases status** follows the wording when no strain is named.
6. **Strain shares** are trend items when they are about one country and are current.
7. **No country, no item.** Worldwide and regional items are dropped.
8. **Forecasts** are dropped. In a mixed sentence the current part is kept. "The season has started" is current.
9. **Risk statements and general seasonal facts** are never items. The prompt no longer asks for "findings".
10. **A new event and its running total** are both kept. Only a total and its parts are merged.
11. **A statement with no count is a trend.** There are no counts of 0.
12. **Human cases of animal flu** are useful, not borderline.
13. **Places:** `USA`; Hong Kong is `China` with city `Hong Kong`; use the city, not the suburb.
14. **Weekdays:** "on Tuesday" is the most recent Tuesday on or before the article date.
15. **Four kinds only.** There is no `other` kind.
16. **Mystery illnesses:** an unexplained illness described only as "flu-like" while officials are still finding the cause is not suspected flu.
17. **Vague amounts** ("a couple of deaths", "nearly three dozen") are not numbers; the statement becomes a trend.
18. **Parts and subsets:** city, age-group and hospital counts inside a broader total are dropped, and so is a suspected total that includes the confirmed cases.
19. **Flu alongside other viruses:** "a surge in RSV and the flu" is a flu trend; a single figure that mixes them is not recorded.
20. **Background and general demand:** an old case mentioned as background, and illness or hospital demand not tied to flu, are not items.
21. **Strains:** only the strain the article gives for that item, never a list collected from the whole article.

## 7. Wording changes agreed on 2026-10-19

These come from Jahnavi's feedback on prompt v2.1. They make the wording clearer and do not change any label: the labels already follow them. They are in prompt v2.2. The rule changes in her feedback (strain shares, hospital dates, parts inside a total, mystery illnesses, "battling the flu", the 30-day limit, mixed-disease trends, repeated trends) wait for a team decision, and the labels change first if a rule does.

22. **One person:** at least one person ill with flu of any strain is enough (2.1).
23. **Nicknames:** "Spanish flu" and "Kung flu"; "a little flu" is no longer the example (2.2).
24. **Prevention with a count:** a prevention article that also gives a current flu statement is useful, and only that statement is recorded (2.2).
25. **General demand:** illness not tied to flu *or flu-like illness* is not an item (2.2).
26. **Completed year or season:** check 2 names a completed calendar year or flu season; "the peak season is over" is a current trend (2.3).
27. **Comparisons:** a comparison with last year or an earlier season never passes the checks (2.3).
28. **Worked-out places:** fill every place part you can work out with certainty (Houston → Texas), and add the sentence that supports it to the evidence (3.2, 3.5).
29. **End date:** `end_date` is never after the article date (3.6).
