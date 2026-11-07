# usefulness_filter

Written for: the capstone team, to see which pool articles went to the LLM extractor and why.

This is a free, local keyword filter. It decides which of the 50,640 pool articles (one per story) are sent
to the LLM extractor. It skips articles that have no flu word at all, so we make fewer calls.

## The rule

1. **Always keep.** Every article in a P_ bucket (counts, trends, case events) or the Z_ bucket (bird flu in
   people) is sent, flu word or not.
2. **No flu word, drop.** Any other article must contain a flu word (`flu_bucketing/flu_keywords.py`).
3. **Gold is not sent again.** The 1,120 gold articles already have labels.

## Numbers

| | Articles |
| --- | --- |
| Pool (one per story, 2015–2024) | 50,640 |
| Kept: P_/Z_ bucket | 9,752 |
| Kept: has a flu word | 30,557 |
| Dropped: no flu word | 10,331 (20.4%) |
| Sent to the LLM (kept, not in gold) | **39,248** |

- **In gold, the keyword layer drops 0 of the 328 useful articles.** That is why it is safe.
- The dropped articles are mostly N_no_flu_text (6,157), X_too_short (3,786), X_spam_stub (307) and
  X_listing_garbled (78).
- No P_/Z_ article lacks a flu word, so layer 1 changes nothing today. It is a safety net.

## Why there is no classifier

We also tried a classifier for the kept articles: TF-IDF + logistic regression, and sentence embeddings
(bge-small-en-v1.5). TF-IDF could have dropped about 9,700 more articles and saved about $12. But only 46 gold
useful articles reach that stage, so gold cannot prove that the classifier loses few useful articles.
Embeddings did worse than TF-IDF. The team chose the keyword filter only, and the classifier code was not kept.

## Use

Run from this folder, with the extractor's venv:

```bash
../llm-extractor/.venv/bin/python pool_texts.py      # 1. texts of the 50,640 out of the 2 GB pool (~10 s)
../llm-extractor/.venv/bin/python pool_articles.py   # 2. layers, the gold check, the extractor input (~10 s)
../llm-extractor/.venv/bin/python -m unittest discover tests   # offline tests
```

Then run the extractor on the output:

```bash
cd ../llm-extractor
.venv/bin/python run_extraction.py --articles-file ../usefulness_filter/output/pool_articles.json
```

## Inputs (read only)

| File | Where it comes from |
| --- | --- |
| `llm-extractor/data/gold_labels.json` | The 1,120 gold articles and their v5.2 labels |
| `repo-sampling/sampling/output/all_articles_buckets.csv` | The 50,640 pool articles and their buckets (Drive, gitignored) |
| `repo/output/pool/pooled_articles.jsonl` | The article texts (2 GB, streamed) |

## Outputs (gitignored)

| File | What it holds |
| --- | --- |
| `data/pool_texts.jsonl` | The texts of the 50,640 pool articles |
| `output/filter_decisions.csv` | Every pool article: bucket, country, year, layer, flu-word count, and whether it is in gold |
| `output/pool_articles.json` | The 39,248 articles to send, in the format of `llm-extractor/data/articles.json` |
