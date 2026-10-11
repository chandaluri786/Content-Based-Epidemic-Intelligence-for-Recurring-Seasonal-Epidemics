# How to label (round 1)

## The files

**Already shared**
- `sample_1200.jsonl` holds all 1,200 articles with their full text, one article per line. The LLM will be run on this file later. You don't need to open it.
- `sample_1200.csv` lists the same 1,200 articles without the text: id, link, date, country, season, phase, bucket and reason. It shows us the mix. **The bucket is only a guess from word rules, so never use it to decide a label.**

**Your packet** (`<you>` is your name: Jahnavi, Thanya, Manoj or Aditya)
- `<you>_texts.txt`: read the articles here. Each one has a header like `#7 [1-own] <article_id>`, then the scan date, the tagged country, the places mentioned and the link.
  - The **tagged country** is the one GDELT linked the article to, used only to pick the sample. It is often not where the story happened (a Bangkok Post story can be tagged Indonesia). Always take `country` in the items tab from the article text.
  - **Places mentioned** are the places GDELT found in the article (`[US]`, `[NZ]`… are its two-letter FIPS country codes, which don't always match the usual ones: `[RP]` is the Philippines, `[SN]` Singapore, `[VM]` Vietnam; `x2` means mentioned twice). They help you see where the story is, but GDELT makes mistakes (e.g. "Belgian" is a nationality, not a place), and it read the page when it was published, so the list can differ from the text we have. Use it as a hint and check the text.
- `<you>_labels.csv`: one row per article. You write the article-level labels here.
- `<you>_items.csv`: one row per statement you extract. It starts empty.

## The split

Each person has 300 articles, and nobody shares articles with anyone else. Every bucket is split evenly across the four of us, so everyone gets the same mix: about 150 likely useful and 150 likely not useful. The likely-useful ones take much longer because you have to extract from them. This way nobody gets all the hard ones, and everyone sees every kind of article, which the agreement check needs.

## Round 1 (now)
- **Rows 1–20, marked `1-own`:** your own 20 articles.
- **Rows 21–40, marked `1-check-<partner>`:** label your partner's 20 yourself, blind. Don't look at their answers until you're both done.
  - Jahnavi checks Thanya, Thanya checks Manoj, Manoj checks Aditya, Aditya checks Jahnavi.
- Upload `<you>_labels.csv` and `<you>_items.csv` when you finish. We then compare answers, agree on the hard cases, and fix the guide.
- **Round 2 (rows 41–300) starts after that.**

## How to label one article

1. Import `<you>_labels.csv` and `<you>_items.csv` into one Google Sheet as two tabs.
2. Find the article in `<you>_texts.txt` by its row number.
3. **useful**: write `yes` or `no`.
   - **yes** means flu in people right now (around the scan date), such as cases, deaths, hospitalizations, or how the season is going (rising, peaking, widespread, low). A single case counts. An article that mixes current and past news counts.
   - **no** covers:
     - only past seasons
     - tips, vaccines or awareness
     - animal flu with no human cases
     - other diseases
     - spam or ads
     - text that doesn't match the link (the page changed after it was collected). For example, a 2024 link about "Disease X" whose text is about a 2026 hantavirus outbreak is a `no`.
4. **If `no`**: leave the other columns empty. Use `notes` if you're unsure.
5. **If `yes`**:
   - In the labels tab, fill `disease`, `strain`, `causes` and `symptoms` as the article words them. Leave a field empty if the article doesn't give it.
   - In the items tab, add **one row per statement**, starting with the `article_id`:

| column | what to write |
|---|---|
| kind | `cases`, `deaths`, `hospitalized`, `trend`, or `other` |
| number | Only if the article gives one. Never guess. |
| status | `confirmed` or `suspected`, if the article says |
| total_or_new | `total` (running total) or `new`, if the article says |
| city | The city or town, if the article names it. Otherwise leave it empty. |
| state | The state or province, if the article names it or it can be worked out from the city (e.g. Visakhapatnam → Andhra Pradesh). If neither, leave it empty. |
| country | Always fill it. Work it out from the places named. |
| start_date / end_date | YYYY-MM-DD, worked out from the date in the article (or the scan date if it has none). For a single day, both dates are the same. For a period ("this week", "since October"), use its first and last day; a period still going on ends on the article date. If you can't tell, leave both empty. |
| words | Trend words exactly as written, e.g. "spreading", "peaked" |
| evidence | The exact sentence from the article, copied |

   Example item row:
   `2016…-123, cases, 20, confirmed, total, , Andhra Pradesh, India, 2016-02-06, 2016-02-06, , "20 swine flu cases have been confirmed in the state so far"`

6. Write anything you're unsure about in `notes`. These notes are how we fix the guide.

The full rules are in `sampling_and_labeling_guide.md`, sections 2, 3 and 5.
