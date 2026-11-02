# How each article is scored: a worked example

Each article gets two separate results:

1. **Useful or not**: one cell of the standard confusion matrix.
2. **Items**: an item score for that article.

The item scores are then averaged over articles. This page works through both on a real article
from the full run (`results/run_full_k8`): **Jahnavi:203** (article id `20171204234500-813`), the
Phoenix flu death from December 2017. The code is in `flu_extractor/metrics.py` (`item_similarity`,
`align_items`, `score_article`, `macro_average`).

## Step 1: Useful or not

Gold says useful and the model says useful, so this article adds 1 to the true positives (TP) of the
useful/not-useful confusion matrix. Every article contributes exactly one cell there, whatever
happens with its items.

## Step 2: The two item lists

| | kind | number | place | start → end date |
|---|---|---|---|---|
| **Gold 1** | cases | 1 new, confirmed | Phoenix, Arizona, USA | 2017-11-27 → 2017-11-27 |
| **Gold 2** | hospitalized | 1 new, confirmed | Phoenix, Arizona, USA | 2017-11-28 → 2017-11-28 |
| **Gold 3** | deaths | 1 new, confirmed | Phoenix, Arizona, USA | 2017-11-28 → 2017-11-28 |
| **Model 1** | deaths | 1 new, confirmed | Phoenix, Arizona, USA | 2017-11-28 → 2017-11-28 |
| **Model 2** | hospitalized | 1 new, confirmed | Phoenix, Arizona, USA | 2017-11-**27** → 2017-11-**27** |

## Step 3: Pair model items with gold items

- **Which items can pair:** only items with the same `kind` and the same `country`. Items of a
  different kind or country describe different events and never pair.
- **Similarity of a pair:** the share of the remaining fields that agree.
  - Count items (cases, hospitalized, deaths) compare 8 fields: number, count_type, status,
    strain, city, state, start_date, end_date.
  - Trend items compare 6 fields: words, strain, city, state, start_date, end_date.
  - Evidence is never compared.
- **Pairing order:** the most similar pairs are taken first (greedy), and each item can be used
  only once.
- **What counts as an exact match:** a pair whose every field (evidence excluded) agrees.

The pairs for this article:

| Pair | Fields that differ | Similarity | Exact? |
|---|---|---|---|
| Gold 3 ↔ Model 1 (deaths) | none | 8/8 = **1.00** | yes |
| Gold 2 ↔ Model 2 (hospitalized) | start_date and end_date: the model used Monday (the day of the diagnosis), gold used Tuesday (the day of the hospital visit) | 6/8 = **0.75** | no |
| Gold 1 (cases) | no model item of this kind | 0 | missed |

## Step 4: This article's scores

| | Precision (out of 2 model items) | Recall (out of 3 gold items) | F1 = 2 × matched ÷ (gold + model) |
|---|---|---|---|
| **Exact** (1 item fully right) | 1/2 = 0.50 | 1/3 = 0.33 | 2 × 1 / 5 = **0.40** |
| **Soft** (partial credit 1.00 + 0.75 = 1.75) | 1.75/2 = 0.875 | 1.75/3 = 0.58 | 2 × 1.75 / 5 = **0.70** |

- **Exact score:** gives no credit for the hospitalization item, even though only its date is
  wrong.
- **Soft score:** gives that item 0.75 credit, so it shows that the model got most of this
  article right.

These numbers are in this article's row of `results/run_full_k8/row_results.csv` (columns
`exact_precision`, `exact_recall`, `exact_f1`, `soft_precision`, `soft_recall`, `soft_f1`).

## Step 5: Combine the articles

Every article that has items is scored this way, and the overall figure is the plain average
(macro average) of the article F1 scores. Each article counts the same, however many items it has.

- **Which articles get an item score:** articles with items in gold, in the model's reply, or both.
  In the full run there are 297.
- **Articles with no items on either side** have no item score. They are already counted in the
  useful/not-useful confusion matrix.
- **Items on only one side** score F1 = 0. Examples are a false alarm where the model wrote extra
  items, or a useful article the model left empty.
- **Result in the full run:**
  - Exact per-article F1 is **6.5%** and soft per-article F1 is **30.7%**.
  - Each comes with a 95% interval, found by resampling the articles (bootstrap, 1,000 resamples).

## Why per article instead of pooling all items

If all items from all articles are pooled, one article with 20 items counts as much as twenty
one-item articles. Averaging per article answers a more useful question: "for a typical article,
how much of it did the extractor get right?" The pooled item scores are still reported in
`report.md` (section 2.4) for reference.

## Checking another article

```
python inspect_row.py results/run_full_k8 Jahnavi:203
```

This shows the gold and model items of any article side by side. Use an article id or a set
position such as `Manoj:94`.
