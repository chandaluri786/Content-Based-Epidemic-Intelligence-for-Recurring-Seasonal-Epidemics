# LLM Extraction Prompt (v0.1, first version)

Written for: the team building the extractor. This is a starting point. It follows `sampling_and_labeling_guide.md`; if the guide changes, change the prompt to match.

## How it is used

For each article the program sends one request made of three parts, in this order:

1. The **instructions** (section 1)
2. The **examples** (section 2), taken from the development set only
3. The **article** to process (section 3)

The LLM replies with one JSON object (section 4). Ask for the reply in the API's structured-output (JSON schema) mode so it cannot come back in another shape.

---

## 1. Instructions (copy as is)

```
You read one news article and do two jobs.

JOB 1. Decide if the article is useful.
Useful means the article reports human flu happening now, for example:
- people currently sick with flu, or suspected to have flu (even one person), and where they are
- how flu is changing now: rising, falling, peaking, widespread, low, quiet
"Now" means the scan date given with the article.
An article that mixes now and past is useful.
An article only about the past (last year, last season, an earlier year) is not useful.
Not useful: flu precautions, tips or vaccination drives; flu in animals with no human cases
(bird flu, pig flu, dog flu); other diseases; stomach flu; games, ads, spam; text that has
nothing to do with flu or does not match the headline.

JOB 2. If the article is useful, pull out the flu information. If it is not useful, return
an empty list of items.

Information to pull out:
- disease, and strain if given (H1N1, H3N2, type A or B)
- causes and symptoms, if given
- items, one for each statement about cases, deaths, hospitalizations or the trend of the season

Each item has:
- kind: cases, deaths, hospitalized, trend, or other
- number: the number if given, otherwise null
- status: confirmed or suspected if stated, otherwise null
- total_or_new: "total" for a running total, "new" for new cases, null if not stated
- city: the city or town, named in full (for example "Visakhapatnam"). null if the article gives none.
- state: the state or province, named in full (for example "Andhra Pradesh"). null if the article gives no state; fill it in if the city makes it clear.
- country: the country, named in full (for example "India"). Always fill it in; if the article names only a city or state, work out the country from it.
- start_date: the first day the statement covers, as YYYY-MM-DD, otherwise null
- end_date: the last day the statement covers, as YYYY-MM-DD, otherwise null
- words: the trend words as written (rising, spreading, widespread, low, ...), otherwise null
- evidence: the exact sentence copied from the article that the details came from

Rules:
1. Only use what the article says. If something is not stated, use null. Never guess a number.
2. Copy `evidence` exactly. Do not change or join sentences.
3. Convert times to dates using the date printed in the article. If none is printed, use the
   scan date. "On Saturday" is the most recent Saturday before that date.
   - A single day: start_date and end_date are both that day.
   - A period ("this week", "since October"): start_date is the first day, end_date is the last
     day. A period that is still going on ends on the article date.
   - If you cannot work it out, use null for both.
4. Numbers from past seasons or past years are not current cases. Leave them out.
5. If the article gives a running total and also new cases, make a separate item for each.
   Never add numbers together yourself.
6. Write one item per statement. Do not merge different cities, states, countries or dates.
7. Reply with the JSON only.
```

---

## 2. Examples (fill from the development set)

Use 5 to 6 examples. Pick them from articles the team has already labeled, so the answers are the human answers, not the LLM's. Suggested mix:

| # | Kind of article |
|---|---|
| 1 | Useful, with counts and a place |
| 2 | Useful, trend words only, no numbers |
| 3 | Useful, one person sick |
| 4 | Not useful: vaccination or precautions |
| 5 | Not useful: bird flu or another disease |
| 6 | Not useful: only about a past season (optional) |

Each example is written like this:

```
<example>
Scan date: 2016-02-08
Article:
<full article text>

Answer:
<the human JSON answer, same shape as section 4>
</example>
```

Keep the articles short or trimmed to the part around the flu sentences. Do not use any test-set article here.

---

## 3. The article to process

```
Scan date: {scan_date}
Article:
{article_text}
```

---

## 4. Reply shape

```
{
  "useful": true or false,
  "disease": text or null,
  "strain": text or null,
  "causes": text or null,
  "symptoms": text or null,
  "items": [
    {
      "kind": "cases" | "deaths" | "hospitalized" | "trend" | "other",
      "number": whole number or null,
      "status": "confirmed" | "suspected" | null,
      "total_or_new": "total" | "new" | null,
      "city": text or null,
      "state": text or null,
      "country": text,
      "start_date": "YYYY-MM-DD" or null,
      "end_date": "YYYY-MM-DD" or null,
      "words": text or null,
      "evidence": text
    }
  ]
}
```

If `useful` is false, `items` is empty and the other fields are null.

---

## 5. How to improve it

1. Run the prompt on the development set only. Compare with the human answers.
2. Look at the mistakes and sort them: wrong useful/not useful, missed items, wrong numbers, wrong dates, invented items.
3. Fix the wording of the rule that failed, or swap in an example that shows the failing case. Change one thing at a time and record it as a new version (v0.2, v0.3).
4. Check that every `evidence` sentence really appears in the article. An item whose evidence is not found is an error.
5. Once the prompt stops improving, freeze it and run it once on the locked test set.

## 6. Notes on this version

- The examples are not filled in yet. They need labeled development articles.
- Date conversion is the part most likely to go wrong. Check it first.
- Rule 5 may need an example once we see how the articles state running totals.
