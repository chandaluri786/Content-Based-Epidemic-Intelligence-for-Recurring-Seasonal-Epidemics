# Feedback on llm_extraction_prompt_v2.1.md (section 1, Instructions)

Written for: the teammate who will edit the extraction prompt (v2.1 → next version).

Source of the feedback: Jahnavi, from her review of the four labeled sets. Each item below says which
statement of the prompt it is about, what the problem is, and what to change. Items marked
**Jahnavi's decision** are firm. Items marked **Suggestion (Claude)** are proposals from the review for
the team to accept or reject. Every example row is from the labeled sets; see `labeling/` for the data.

v2.1 section 1 is the text inside the code fence. Step numbers below are the prompt's own.

---

## A. Changes requested (Jahnavi's decisions)

### A1. Step 2, type 1: "People ill with flu ... One person is enough"
- **Change:** replace "one person is enough" with wording that says **at least one person must be affected by
  flu, of any strain or variant, or by a flu-related disease.**

### A2. Step 2, type 5: "Which strain is going around"
- **Change: remove type 5 entirely** (strain shares such as "86% of positive samples were H1N1").
- **Why:** an article will often carry only cases, deaths, hospitalizations or a trend. Making a strain share
  count as a statement widens what the model looks for in a way that is hard to meet, and the extra
  condition would push more samples into "not useful". The strain-share clause in the `trend` kind
  definition in step 4 ("or which strain dominates") should go too.

### A3. "These are NOT items", bullet 3 (the "mystery illness" rule)
- Currently: an unexplained illness that the article describes only as "flu-like" while officials are
  finding the cause is not an item.
- **Change:** this needs rewording, because elsewhere the prompt treats **flu-like illness as a possible
  suspected flu case** (step 2 type 4; step 4 `status`). Check every place that uses "flu-like" so that it is
  used consistently: flu-like illness is a suspected case unless the article names another cause or test.

### A4. "These are NOT items", bullet 4 (nickname example)
- Currently: `a nickname ("a little flu")`.
- **Change:** "a little flu" is **not a nickname**. Go back to the nickname list in v2.0, and drop "a little flu"
  from it.
- **Note for the editor:** v2.0's list reads `("Spanish flu", "a little flu", "Kung flu")`, so a literal
  fallback to v2.0 would bring "a little flu" back. Jahnavi's intent is to keep real nicknames only, i.e.
  "Spanish flu" and "Kung flu".

### A5. "These are NOT items", bullet 5 ("prevention only")
- **Change:** tweak the wording (Jahnavi: "needs to be tweaked a little bit"). She did not give the new text.
- **Suggestion (Claude):** keep "vaccination, tips, clinics, vaccine coverage" as not items, but say plainly that
  a prevention article that also states a current flu count or level is still useful (the prevention
  sentences are just not recorded). This is how the labeled sets treated vaccine/awareness articles with a
  year-to-date count (Learnings U2, U3).

### A6. "These are NOT items", bullet 12 ("illness or hospital demand in general that the article does not tie to flu")
- **Change:** say **"flu and flu-like"**, because flu-like can be a suspected flu case.

### A7. "Other diseases" paragraph (step 2)
- Currently it says an article mainly about COVID-19, RSV or dengue is useful only if it has "its own current
  flu statement", and says never to record "a figure that mixes flu with another disease ('a 30% rise in
  influenza and RSV')".
- **Problems:**
  1. "Its own current flu statement" is unclear. It should say what that means.
  2. The example "a 30% rise in influenza and RSV" is dropped by that sentence, but the **next sentence says a
     statement that flu is rising alongside other viruses is still a flu trend** ("a surge in RSV and the flu and
     Covid"). The two sentences contradict each other.
- **Change (Jahnavi's rule):**
  - **Cases, hospitalizations and deaths** are written only when the number is **for flu alone**, not a combined
    total of flu and other diseases, and only when it is **current**.
  - **Trend items** may be written even when the statement is a combination: "a 30% rise in flu and RSV" is
    acceptable as a flu trend, as long as it is current.
  - Remove the example that contradicts this ("a 30% rise in influenza and RSV" as something to drop).

### A8. Step 4, `hospitalized`: "A patient who has gone home from hospital is still hospitalized"
- **Change: remove this sentence** and replace it with: **a `hospitalized` item records the event of admission.**
  Its `start_date` and `end_date` are both the admission day. It does not span the length of the stay.
- **Why:** Jahnavi: "just record the event of admission. That is the only start and end date. We don't need it
  to span through the entire duration." This also matches the item she accepted for a discharged patient
  (Manoj row 200, former president Moi: admitted Thursday 13 December, discharged the day before the article;
  the item is dated 2018-12-13 to 2018-12-13).

### A9. Step 6, dates
- **Add / confirm:** `start_date` can never be after `end_date` (already in v2.1) and **`end_date` can never be
  after the publish (article) date.**
- Where v2.1 says "to the article date or the stated update date", the end date still must not pass the article
  date.

---

## B. Open questions for the team (Jahnavi asked for verdicts or suggestions)

### B1. The `borderline` flag: remove it or improve it?
Jahnavi: "seems very vague".

**Suggestion (Claude): keep it, but define it by a closed list**, so the model can decide. The flag is useful
as a review queue for humans, since many rows in the review were genuine judgement calls. Proposed triggers
(each with a row from the labeled sets):

| Set `borderline` = true when ... | Example row |
|---|---|
| a named person has flu but the article does not say where | Manoj 190 (singer treated for flu symptoms; where unknown) |
| a single case has no date | Jahnavi 126 (toddler in ICU) |
| a self-reported case has no test | Manoj 198 ("battling the flu") |
| the period ended 31 to 45 days before the article | Aditya 211 (a death on 24 April in a 6 June article, 43 days) |
| "this season/year" with no direction | Thanya 117 ("flu season ramps up") |
| the flu mention sits in a story about something else | Manoj 142, Manoj 158 |
| human cases are in a mostly-animal article and are undated | Manoj 57 |

Output: `borderline` is true if any trigger applies, otherwise false; items are still written when `useful` is true.

### B2. Step 3, Check 1: "The article date minus end_date must be 30 days or less" — a hard limit?
**Verdict (Claude): keep a 30-day limit as the default, but do not make it a cliff.**
- v2.0 had **no numeric limit**. It was a judgement: counts that ended "a few days before" count when the
  article shows the season is still going; counts that ended "weeks or months earlier, with nothing showing the
  season is still going" do not.
- The 30-day number comes from the rulebook (2.3) and matches almost every decision in the review: Jahnavi 199
  and 152 and Aditya 207 and 211 (about 40 to 50 days, `no`), Jahnavi 54 (29 days, `yes`).
- Risk: a cliff at 30 days will mis-handle an ongoing outbreak whose last dated count is 31+ days old but whose
  article clearly describes the situation now. Measure from the **end of the period** (v2.1 already does), let a
  **running total that ends at the article date** pass whatever its start, and mark `borderline` for 31 to 45 days.

### B3. Step 3, Check 2 ("a whole year or season that is already over")
**Suggestion (Claude):** the idea is right but the wording is vague about what "a whole year or season" means.
Proposed rewrite:

> An item whose period is a **completed calendar year or a completed flu season** is past, even if it ended
> inside 30 days (an article from 5 January with "last year, 2,200 cases"). A period that is still running
> ("so far this year", "this season", "since September 1", "to date") passes. A statement about the present
> that the season is over ("the peak season is over") is a current trend and passes.

Reasons: (1) Check 2 only changes the result when a year or season ended within 30 days, which is exactly the
January and the end-of-season case (Jahnavi 264); say so. (2) Southern and Northern Hemisphere seasons end
at different times; name "completed" explicitly. (3) Keep the worked examples in v2.1 and add the
"season is over" example.

---

## C. Other issues Claude found while comparing v2.1 with the review decisions
These conflict with decisions Jahnavi gave during the review. Please confirm with her before changing.

1. **"Parts and subsets of a total are dropped" and "keep only the confirmed" (step 4, counting each thing once).**
   Jahnavi kept nested items throughout the review (a single death inside a total, a weekly count inside a
   two-month total, 57 confirmed inside 183): Jahnavi 50, 51, 200; Aditya 51, 55; Manoj 19, 55; Thanya 39, 78,
   93. The v2.1 rule would drop them. The rule that "a new event next to its running total is kept" matches her
   decisions; the "subsets dropped" part does not.
2. **`status` for a named person "battling the flu".** v2.1 would leave it null; Jahnavi decided `confirmed`
   (Manoj 198).
3. **The `findings` step was removed in v2.1.** Jahnavi is **fine with the step staying removed**, so no change is
   needed. (The two findings sheets created in the review, `Manoj_findings.csv` and `Thanya_findings.csv`, are
   outside the prompt.)
4. **A story's outlet or language does not place a person.** "Korean news" is not "in Korea" (Manoj 190). Add an
   explicit rule: a country is filled only if the article places the illness; the publisher's country does not
   count.
5. **Inferred places need a supporting evidence part.** Learnings E3/E4: when a city, state or country is not in
   the item's own sentence, add the sentence that supports it as a further evidence part. Step 7 mentions this
   only for places and dates "from a different sentence"; make it explicit for inferred values.
6. **Week dates from a link.** v2.1 says never work a week's dates out yourself. In the review the week 26
   dates of a bulletin (24 to 30 June) were accepted from the calendar and the link text (Manoj 63). Decide
   whether the prompt should allow dates from the link when the article names a week number.
7. **City, state and country: the rule (Jahnavi's decision).** The city field holds a **real city only**. A suburb
   (Westmead) or a hospital is not a city: if the article names only a suburb or a hospital, the city is the
   **city it belongs to** (Westmead Children's Hospital is in Sydney, so the city is "Sydney"). That is why
   Sydney was kept on Aditya row 80. Sydney itself is a city, so there is nothing to change about it; the older
   Learnings P1 wording ("a hospital's suburb or city is the city value", with Westmead as the example) is the
   part that is inconsistent and should be updated to this rule. **Fill in whatever parts of the city, state and
   country can be worked out with certainty from what the article names** (Houston gives Texas, Kolkata gives
   West Bengal, Brisbane gives Queensland and Australia), and add the supporting sentence to the evidence when
   the value is not in the item's own sentence. This replaces the Learnings P2 wording ("never add a state from
   outside knowledge"), which should also be updated.
8. *(merged into item 7)*
9. **`total` for any count over a stated period vs. a single day.** "182 students sick on Thursday" was set
   `new` by Jahnavi (Manoj 56). The rule should say a single day stays `new`.
10. **Comparison numbers are kept (step 3).** Jahnavi did not record comparisons with last year (Manoj 97,
    Thanya 7). Limit the "kept" rule to comparisons with the immediately previous period that pass the 30-day
    check.

---

## D. Additional feedback (added later, Jahnavi's decisions)

### D1. Change how the prompt decides duplicates for nested totals
- **Problem:** the prompt and the rulebook disagree on what to do when a single event sits inside a running
  total in the same sentence. Learnings rule I3a says keep only the broader total (so the nested item is
  removed). The way Jahnavi labeled row 18 keeps the event inside the total. In the review she kept the nested
  item.
- **Example (Jahnavi row 50, item 6, article id 20150717011500-230, "2 women in 30s die of H1N1, Mumbai toll
  touches 25"):**

  | Field | Saved value |
  |---|---|
  | strain | H1N1 |
  | kind | cases |
  | number | 7 |
  | status | confirmed |
  | total_or_new | new |
  | city / state / country | blank / Maharashtra / India |
  | start_date / end_date | 2015-07-16 / 2015-07-16 |
  | words | blank |

  Evidence: "So far, around 60 people have tested positive for the infection in July, including seven people over
  the last 24 hours."

  The same sentence also gives item 5, cases 60 (total, 2015-07-01 to 2015-07-17). The 7 cases sit inside those
  60. Under I3a item 6 would be removed; under row 18 it stays.
- **Decision (Jahnavi): keep it.** "Seven in the last 24 hours" is a new-case signal on a specific day that the
  total does not tell a reader.
- **Change requested:** rewrite the nested-totals dedup rule in step 4 ("Counting each thing once") so that a
  **single, dated event (or a short recent sub-period) inside a running total is kept as its own `new` item
  next to the total**. Only drop an item when it is the same fact stated twice, not when it is a smaller piece of
  a larger count. This is the same issue as C1 above; apply the two together.

### D2. Tell the model to learn from the evidence in the examples
- **Change requested:** the instructions must **ask the model to use the evidence in the solved examples to
  reason and understand how the items were generated**: for each example, how the sentence in `evidence` leads
  to the `kind`, the `number`, the `status`, `total_or_new`, the place and the dates. State this in the
  instructions (and in the example block) so the model studies the evidence-to-item mapping, not only the
  final answers.

### D3. Redundant items must not exist (especially `trend`)
- **Problem observed:** duplication is found mostly in `kind` = `trend`. The model writes several trend items
  that use **different words with the same meaning**, for the **same period** and the **same city, state and
  country**, as separate new items. This is redundancy and must be avoided.
- **Examples from the review (the same meaning repeated; the extra items were removed):** Aditya 140 (four
  trend items all saying the New York flu season is mild; three removed), Aditya 210 ("low level of activity"
  and "low", same sentence; one removed), Thanya 101 (the headline "increase in flu cases" repeating the
  22 per cent increase; removed).
- **Change requested:** add an explicit rule: **write one trend item per distinct meaning, per place and
  period.** If two trend items share the same place and the same period and say the same thing in different
  words, keep one (the one with the clearest statement or the most informative words) and drop the others.
  Add a self-check line for it in step 8 ("no two trend items repeat the same meaning for the same place and
  period"), and one solved example showing a repeated trend being collapsed.
