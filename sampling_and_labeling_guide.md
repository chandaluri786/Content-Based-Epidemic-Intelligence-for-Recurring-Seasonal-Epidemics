# Sampling and Labeling Guide

Written for: the labeling team.

## 1. Goal

Pick 1,200 news articles, label them by hand, and use the labels to test an LLM that does two jobs:

1. Decide whether an article is useful.
2. For useful articles only, pull out the flu information in the text.

The extracted information is used later to find when a flu season starts.

## 2. Which articles are useful

**Useful:** the article talks about flu in people happening now, for example:
- people currently sick with flu, or suspected to have flu, and where they are (even one person counts)
- how flu is changing now: rising, falling, peaking, widespread, low, quiet

"Now" means the time the article was collected (the scan date).

- An article that mixes now and past is useful.
- An article that is only about the past (last year, last season, a named earlier year) is not useful.

**Not useful:** everything else, including:
- flu precautions, tips, vaccination drives
- flu in animals (bird flu, pig flu, dog flu) with no human cases
- other diseases
- games, ads, spam
- pages whose text has nothing to do with the link or headline (the page changed since it was collected)

All articles in the set are English. Non-English articles are removed before sampling.

**Articles that only list symptoms** (many people with cough, fever, cold): treat as useful only if the article names flu or a flu-like illness and describes people sick now. In our data this is almost never the case (5 candidates found, none real), so don't expect to find many.

## 3. What to pull out of a useful article

Copy the information from the article as it is written. Do not change it into a fixed form.

- Disease
- Strain, if given (H1N1, H3N2, type A or B)
- Number of confirmed cases and total cases, with the city, state, country and time they refer to
- Suspected cases
- Causes
- Symptoms
- Any words that describe how the flu season is going (rising, spreading, peaked, mild, severe, widespread, low)

Rules:
- If a number is not given, leave it blank. Do not guess.
- If the article gives a running total and also new cases, record both and say which is which.
- Convert any time in the article ("on Saturday", "this week") to exact dates. Count from the date printed in the article; if none is printed, use the scan date. "On Saturday" is the most recent Saturday before that date.
  - A single day gives one date: start_date and end_date are the same.
  - A period ("this week", "since October", "between 1 and 5 January") gives the first day of the period as start_date and the last day as end_date. A period that is still going on ends on the article date.
  - If it cannot be worked out, leave both empty.
- Numbers from past seasons are not current cases.

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

One row per article, kept in a spreadsheet while labeling and saved as a JSON lines file (one article per line) afterwards.

| Column | What goes in it |
|---|---|
| article_id | The record ID |
| link | The article URL |
| scan_date | The date it was collected |
| useful | yes or no |
| extracted | For useful articles only: the items from section 3, a list of items as described below. Empty for not useful. |
| labeler | Who labeled it |
| notes | Anything unclear |

### What `extracted` looks like

`extracted` is a list. Each item is one statement from the article. An article can have many items. Any part that the article does not state is left empty (null), never guessed.

Every item has the same parts:

| Part | Meaning |
|---|---|
| kind | What the statement is about: cases, deaths, hospitalized, trend, or other |
| number | The number, if given |
| status | confirmed or suspected, if stated |
| total_or_new | Whether the number is a running total or new cases, if stated |
| city | The city or town the statement is about. Leave empty if the article gives none. |
| state | The state or province. Leave empty if the article gives none; fill it in if the city makes it clear. |
| country | The country. Always filled, even if the article does not name it (work it out from the place named). |
| start_date | First day the statement covers (YYYY-MM-DD). For a single day, that day. |
| end_date | Last day the statement covers (YYYY-MM-DD). For a single day, the same day. |
| words | Trend words, as written ("spreading", "widespread", "low") |
| evidence | The exact sentence copied from the article that the details came from |

Details that belong to the whole article, not to one statement, are written once: disease, strain, causes, symptoms.

Example (the Visakhapatnam swine flu article):

```
{
  "article_id": "...",
  "useful": true,
  "disease": "swine flu",
  "strain": "H1N1",
  "causes": null,
  "symptoms": null,
  "items": [
    {"kind": "cases", "number": 20, "status": "confirmed", "total_or_new": "total",
     "city": null, "state": "Andhra Pradesh", "country": "India", "start_date": "2016-02-06", "end_date": "2016-02-06", "words": null,
     "evidence": "..."},
    {"kind": "hospitalized", "number": 3, "status": "suspected", "total_or_new": "new",
     "city": "Visakhapatnam", "state": "Andhra Pradesh", "country": "India", "start_date": "2016-02-06", "end_date": "2016-02-06", "words": null,
     "evidence": "..."},
    {"kind": "trend", "number": null, "status": null, "total_or_new": null,
     "city": null, "state": null, "country": "India", "start_date": null, "end_date": null, "words": "spreading", "evidence": "..."}
  ]
}
```

### Why this form

It stays close to the article's words, and it lets later steps work without reading the text again:
- **Dates:** the labeler gives exact start and end dates, so code can group items by week directly.
- **Weekly counts:** code groups items by date, city, state and country, and adds up `new` numbers. Running totals are not added together; they are compared with the previous total instead.
- **Trend words:** `words` are matched to a short list (rising, falling, peak, widespread, low) after labeling, not during it.
- **Checking:** `evidence` lets anyone confirm an item against the article.

How it is used:
- **Development set:** pick a handful of clear examples (a useful one, a not-useful one, a tricky one) and put each article with its `useful` and `extracted` answer into the LLM prompt as examples. No model training is needed; the LLM follows the format from these examples.
- **Test set:** keep the same columns but hide the answers from the LLM. Run it on `text`, then compare its `useful` and `extracted` with the human answer.
- Keep the evidence sentence with each item so any answer can be checked against the article.
