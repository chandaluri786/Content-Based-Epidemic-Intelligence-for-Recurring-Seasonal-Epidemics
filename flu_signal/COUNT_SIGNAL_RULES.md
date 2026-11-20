# Country-level weekly count signals: construction rules

Date: 2026-11-18. Status: agreed with Jahnavi; not yet implemented. Source of the item rules: prompt v5.2
(`llm-extractor/prompts/system_prompt_v5.2.txt`).

## 1. Purpose

These rules turn the count items extracted by the LLM (prompt v5.2) into **one number per country, ISO week, kind
and status**. Every item is placed in exactly one week, and a complete total is never added to.

Each country gets six weekly series:

| | confirmed | suspected |
|---|---|---|
| **cases** | series 1 | series 2 |
| **hospitalized** | series 3 | series 4 |
| **deaths** | series 5 | series 6 |

The six series are built **separately** with identical rules. An item in one series never affects another.

## 2. Terms

| Term | Meaning |
|---|---|
| **Item** | One count extracted from one article: `kind, number, count_type, status, city, state, country, start_date, end_date`. Strain is ignored. |
| **Article** | The news article an item came from. Several items can come from one article. |
| **ISO week** | Monday to Sunday, labelled by ISO year and week (for example `2015-W06`). Days near New Year can belong to the neighbouring year's week; always use the ISO label. |
| **Item days** | Every day from `start_date` to `end_date`, both included. A `new` item has one day. |
| **Level** | The lowest place field the item fills: **city** if `city` is filled, else **state**, else **country**. |
| **Place** | The full combination of filled place fields. "Pune, Maharashtra, India" is a city place, "Maharashtra, India" a state place, "India" a country place. Two items are at the same place only if all their filled place fields are equal. |
| **Children** | A country's children are its states; a state's children are its cities. A city with no state is a direct child of its country. |
| **Open days** | The days of the week a place may use. A country starts with all 7 days open. A child gets the days its parent passes down (Section 6). |
| **Closed day** | A day a higher level has finished with (Rule 2). Nothing below that level may use it. |
| **Used / dropped** | A used item adds its `number` to the signal. A dropped item adds nothing, closes no days and guards nothing. |

**The three count types** (prompt v5.2, Section 7):

| `count_type` | What it means for its place | Its days | Effect on the levels below |
|---|---|---|---|
| `cumulative_region` | the **complete** total for that place over the period | the period | **closes** its days |
| `new` | events on one single day (says nothing about completeness) | one day | **does not close** its day |
| `cumulative_subset` | a total for only **part** of the place, or one group of people | the period | **does not close** its days |

## 3. Stage 1: Which items are used

An item enters a series only if all of these hold:

- **1.1** `kind` is `cases`, `hospitalized` or `deaths`. Trend items are never used.
- **1.2** `status` matches the series (`confirmed` or `suspected`).
- **1.3** `start_date` is filled. Prompt 4.2 leaves it null only for running totals with an unknown start; these
  cannot be placed in a week.
- **1.4** `start_date` and `end_date` fall in the **same ISO week**. The period can be the whole week or any part
  of it.

**Figure 1: Which periods fit (ISO week Mon 2 – Sun 8 Feb 2015)**

```
              Sun1 │ Mon2 Tue3 Wed4 Thu5 Fri6 Sat7 Sun8 │ Mon9
A  new             │       ●                            │        ✔ one day
B  region          │  ████ ████ ████ ████ ████ ████ ████│        ✔ whole week
C  region          │  ████ ████ ████                    │        ✔ part of week
D  subset          │                 ████ ████          │        ✔ part of week
E  region     ████ │  ████ ████                         │        ✘ spans two weeks
F  region          │                           ████ ████│ ████   ✘ spans two weeks
G  region  start = null ─────────────────────────────── ┤        ✘ start unknown
```

The prompt already guarantees recency (end date within 30 days of the scan date, 4.7) and that no end date is after
the scan date (4.2). The data is trusted as delivered.

## 4. Stage 2: Which level owns each day

> **Rule 2.** Work from the country down to states, then cities. A day covered by a used **`cumulative_region`**
> item at a level is **closed** to every level below it. Days covered only by used **`new`** or
> **`cumulative_subset`** items stay **open**: the levels below are still looked at on those days, and their used
> items are **added**.

Reason: only `cumulative_region` is a complete count for its place (prompt 7.1). `new` and `cumulative_subset`
report part of what happened, and the places below are the only way to recover the rest.

**Figure 2: Ownership of days in one week**

```
                         Mon  Tue  Wed  Thu  Fri  Sat  Sun
India region             ███  ███  ███                       closes Mon–Wed
India new                                    ●               does NOT close
India subset                            ░░░  ░░░  ░░░  ░░░   does NOT close
─────────────────────────────────────────────────────────────────────
Passed to every state:                  Thu  Fri  Sat  Sun

Maharashtra region                      ███  ███  ███  ███   closes Thu–Sun for its cities
Passed to Maharashtra's cities:         (none)

Gujarat (no state items)
Passed to Gujarat's cities:             Thu  Fri  Sat  Sun
Ahmedabad (city items)                  ███
```

## 5. Stage 3: Which items are used within one level

The same steps run at every place: country first, then each state, then each city. **Only items whose place is
exactly that place are considered.**

### Step 3.0: Same-article guard from higher levels

An item is **dropped** if it comes from the **same article** as a used `new` or `cumulative_subset` item at a
**higher level** (its parent, grandparent, ...), **and** it shares any day with that item.

Within one article, the prompt records both a figure and its parts ("5 deaths in Maharashtra on Monday, 2 of them in
Pune"; "41 cases in six states ... 10 in Texas"), so adding both would count the parts twice. Items from
**different articles** are assumed to be different events and are added.

### Step 3.1: Complete totals first (`cumulative_region`)

1. Sort the place's region items: **longer period first**, then **larger number**, then **earlier start date**.
2. Go down the list. **Use** an item only if every one of its days is open and not yet taken by a region item already
   used at this place.
3. Otherwise **drop** it: a copy of the same total in another article, a second total for the same days, or a total
   that crosses into a closed or taken day.
4. The days of the used region items are the place's **covered days**.

> **A used `cumulative_region` item is final.** For its place and its whole period, nothing else is added: no other
> region item, no `new`, no subset at that place, and nothing from any place below it.

Used region items never share a day, so their numbers are **added** (Mon–Wed = 6 and Thu–Sun = 4 give 10).

### Step 3.2: Fill the remaining days (`new` and `cumulative_subset`)

The **fill days** are the place's open days minus its covered days.

- A **`cumulative_subset`** item is used if **every** one of its days is a fill day.
- A **`new`** item is used if its day is a fill day, unless Step 3.3 drops it.
- Fill items **do not block each other**: two new items, two subsets, or a new and a subset are all added,
  including items from different articles on the same day.

### Step 3.3: A new count inside a subset from the same article (same level)

A `new` item at this place is **dropped** if it comes from the **same article** as a used `cumulative_subset` item
at this place and its day falls within that subset's days. If the subset itself was dropped, the new item is judged
on its own.

### Step 3.4: Partial overlap

An item is dropped when **some** of its days are closed or covered and others are not. Its number cannot be split by
day.

**Figure 3: Partial overlap at one place**

```
                 Mon  Tue  Wed  Thu  Fri  Sat  Sun
region (used)    ███  ███  ███                       covered: Mon–Wed
subset (4)                 ███  ███  ███             ✘ dropped: Wed already covered
subset (3)                      ███  ███             ✔ used: Thu–Fri all fill days
new (1)               ●                              ✘ dropped: Tue covered
new (1)                              ●               ✔ used: Fri is a fill day
```

### Step 3.5: What is passed down

- **Closed for the children:** the covered days (region items) only.
- **Passed down:** every other open day, including days covered by used `new` or subset items.
- Every used `new` and subset item at this place joins the list of higher items for the Step 3.0 guard further down.

## 6. Stage 4: Adding up

**Figure 4: Order of work for one week**

```
 Country ──► Step 3 at country level ──► days passed down ──┐
                                                            ▼
              ┌──────────────── each state ─────────────────┐
              │ Step 3 on the days passed down              │
              │        └──► days passed down ──┐            │
              │                                ▼            │
              │              ┌──── each city ─────┐         │
              │              │ Step 3 on the days │         │
              │              │ passed down        │         │
              │              └────────────────────┘         │
              └─────────────────────────────────────────────┘
```

> **Value of a place** = (its region items used) + (its new and subset items used) + (the values of its children)
>
> **Country weekly signal** = value of the country

Region days are never shared with children. On `new` and subset days, the children's items are added on top, to
recover the parts those items do not report. Nothing is scaled up for places with no reports: the signal is the
**sum of what was reported**.

**Implementation outline**

```
value(place, open_days, higher_items):
    own = [x for x in items whose place is exactly `place`
           if not any(g.article == x.article and days(x) ∩ days(g) ≠ ∅
                      for g in higher_items)]                         # Step 3.0
    covered, total = ∅, 0
    for r in region items of own, sorted (longer, larger, earlier):   # Step 3.1
        if days(r) ⊆ open_days and days(r) ∩ covered = ∅:
            total += r.number;  covered ∪= days(r)
    fill    = open_days − covered                                     # Step 3.2
    subsets = [s for s in subset items of own if days(s) ⊆ fill]
    news    = [n for n in new items of own if day(n) ∈ fill
               and not any(s.article == n.article and day(n) ∈ days(s)
                           for s in subsets)]                         # Step 3.3
    total  += sum(subsets) + sum(news)
    passed  = open_days − covered                                     # Step 3.5
    for child in children(place):
        total += value(child, passed, higher_items + subsets + news)
    return total

signal(country, week) = value(country, all 7 days of week, [])
```

## 7. Output

- **Signal rows:** `country, iso_week, kind, status, value, n_items_used, n_articles_used`. A week with no item used
  gets no row.
- **Drop report**, per series: the number of items dropped by 1.3 (null start), 1.4 (spans weeks), 3.0 (same-article
  guard), 3.1 (region not used), 3.2/3.4 (covered or partial overlap) and 3.3 (new inside a same-article subset),
  and the number dropped because a higher region closed the day (Rule 2).
- **Overlap-risk count**, per series: the number of place-days where a used higher-level `new` or subset item and
  used lower-level items from other articles are both counted (Section 10).

## 8. Worked example: India, deaths, confirmed, week 2015-W06 (Mon 2 – Sun 8 Feb)

**Items**

| Item | Article | Place | Level | Type | Days | No. |
|---|---|---|---|---|---|---|
| a | A | India | country | region | Mon–Wed | 20 |
| b | B | India | country | new | Fri | 1 |
| m | K | India | country | subset (children) | Thu–Sun | 7 |
| c | C | Maharashtra, India | state | new | Tue | 2 |
| d | D | Maharashtra, India | state | region | Thu–Sun | 9 |
| e | E | Rajasthan, India | state | new | Thu | 1 |
| f | E | Rajasthan, India | state | subset | Sat–Sun | 3 |
| g | E | Rajasthan, India | state | new | Sun | 1 |
| h | F | Rajasthan, India | state | new | Sat | 1 |
| i | G | Jaipur, Rajasthan, India | city | new | Sat | 2 |
| j | H | Telangana, India | state | region | Sat–Sun | 2 |
| k | H | Karimnagar, Telangana, India | city | region | Sat–Sun | 2 |
| l | J | Ahmedabad, Gujarat, India | city | new | Thu | 2 |
| n | K | Kerala, India | state | new | Sat | 1 |

**Step by step**

1. **India** (open: all 7 days). Region **a** is used, covering Mon–Wed. Fill days Thu–Sun: **b** (Fri) and **m**
   (Thu–Sun) are used. India's own value = 20 + 1 + 7 = **28**. Closed: Mon–Wed. **Passed to the states: Thu–Sun.**
   Guard list: b (article B), m (article K).
2. **Maharashtra** (open Thu–Sun). **c** (Tue) is on a closed day: dropped. **d** (Thu–Sun) is all open, article D:
   used, **9**. Its cities get no days.
3. **Rajasthan** (open Thu–Sun). **e** (Thu) and **f** (Sat–Sun) are used. **g** (Sun) is inside f, same article
   (3.3): dropped. **h** (Sat), a different article: used. Own value 1 + 3 + 1 = 5. No region, so its cities get
   Thu–Sun. **i** (Jaipur, Sat, article G) shares no article with a higher item: used, 2. Rajasthan = **7**.
4. **Telangana** (open Thu–Sun). **j** (Sat–Sun) is used, **2**, and is final for Telangana on Sat–Sun. Its cities
   get Thu–Fri. **k** (Karimnagar, Sat–Sun) is on closed days: dropped. This is the same total recorded at two
   places (prompt 7.2), counted once.
5. **Gujarat**. No state items, so Thu–Sun pass to its cities. **l** (Ahmedabad, Thu): used, **2**.
6. **Kerala**. **n** (Sat) comes from article K, the same article as India's subset m, and Sat is within m's days:
   dropped by 3.0.

**India, 2015-W06 = 28 + 9 + 7 + 2 + 2 = 48.** Used: a, b, m, d, e, f, h, i, j, l. Dropped: c, g, k, n.

## 9. Edge cases, settled

| Case | Rule |
|---|---|
| The same complete total in two articles | The second finds its days taken: dropped (3.1). Counted once. |
| The same `new` or subset count in two articles | Both used (3.2). Duplicates across articles are not removed. |
| Two region items at one place on separate days of the week | Both used and added (3.1). |
| Two region items at one place sharing some days | The first in sort order is used; the other is dropped. |
| A higher `new` or subset item and a lower item, different articles, same days | Both used and added (Rule 2). |
| A higher `new` or subset item and a lower item, same article, sharing **any** day | The lower item is dropped (3.0). |
| A higher region item and a lower item on the region's days | The lower item is dropped; region is final (3.1, Rule 2). |
| A dropped item at any level | Closes no days and guards nothing. |
| A city with no state | Treated as a direct child of the country. |
| One person suspected, then confirmed | Two items (prompt 2.4) in different series; they never interact. |
| Zero counts | Never recorded by the prompt (2.5). |

## 10. Known limits (state these in the write-up)

- **Lower bound.** The signal is what was reported, not the true number of cases, admissions or deaths.
- **Lost data.** Periods spanning two weeks, and running totals with no start date, are not used. An item that
  partly overlaps a region-covered day is dropped.
- **Possible double counts.**
  - `new` and subset copies from different articles are added.
  - On days of a higher `new` or subset item, lower-level items from other articles are added; some may be the same
    people.
  - A higher-level `new` item that is in practice a full daily figure ("50 new cases in the last 24 hours") gets
    lower-level items from other articles added on that day. The prompt has no `new_region` / `new_subset` split to
    tell these apart; a split would need a prompt change and a new extraction run.
- The drop report and the overlap-risk count (Section 7) measure the size of each of these.
