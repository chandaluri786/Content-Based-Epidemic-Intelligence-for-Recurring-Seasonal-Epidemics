# flu_bucketing

Sorts articles into **flu related** and **non flu related** by keyword presence in the article body.

**Scope: English only.** Flu words in other languages (Vogelgrippe, gripa, 流感, грипп ...) are deliberately not in the vocabulary. Non-English articles are out of scope: they are not validated and are bucketed only by the English-attested terms they happen to contain (strain codes, brand names, "influenza"). This is a keyword sort only. It is not a usefulness label and it follows no labeling rules.

## Files
| File | What it is |
|---|---|
| `flu_keywords.py` | The rules (`is_flu_related`, `flu_hits`). Read the module docstring first. |
| `bucket_articles.py` | Command line sorter for the `*_texts.txt` labeling files |
| `test_flu_keywords.py` | 9 tests for the rules (`python3 -m unittest test_flu_keywords`) |

## Use
```bash
python3 bucket_articles.py INPUT_DIR --dry-run                 # counts only, writes nothing
python3 bucket_articles.py INPUT_DIR [--out OUTPUT_DIR]        # writes the files below
```
For each `<Name>_texts.txt` it writes `<Name>_texts_flu.txt` and `<Name>_texts_nonflu.txt`. Article blocks are copied unchanged (same header, same `#N` number, same text), so labels that point to `#N` still line up. It also writes `bucket_audit.csv` (bucket, number of hits, matched terms and whether each came from the sample or from general knowledge).

## What counts as flu related
The article body matches at least one of these. The link, header and scan date are never searched.

1. **Flu words**: any word containing flu or influenza, including words glued to others in URLs and hashtags (swineflu, flulike, theraflu, wuflu), plus typos (influeza, lnfluenza, infuenza). Lookalikes are denied (influence, influx, fluid, fluctuate, flush, flurry, fluoride, flue, affluent ...).
2. **Strains**: any H#N# code (H1N1, H5N1, H7N9 ...) in any case, also glued to a word (h5n1strain).
3. **Lineages**: B/Victoria, B/Yamagata, Yamagata, A/California ..., pdm09, clade 2.3.4.4b.
4. **Antivirals**: oseltamivir, zanamivir, peramivir, baloxavir, favipiravir, Tamiflu (and typos), Relenza, Xofluza, amantadine, rimantadine.
5. **Vaccine brands and flu programs**: Flumist, Fluzone, Flublok, Flucelvax, Fluad, Afluria, FluGen, Influvac, Fluenz, Efluelda, Vaxigrip, Agrippal, Grippol, NanoFlu, mFlusiva ...
6. **Surveillance names**: ILI (uppercase only), ILINet, FluNet, FluView, FluSurv, FluWatch, FluTracking, GISRS, NREVSS, national influenza centre.
7. **Animal flu terms**: HPAI, LPAI, highly pathogenic avian, fowl plague.
8. **Text repair before matching**: ligatures (ﬂ), "In?uenza", "influ-enza" at a line break, soft hyphens, and the garbled characters (â) that break word boundaries.

## Deliberately not counted
`SARI` (mostly the garment), `ARI`, RSV, "respiratory illness", Haemophilus **influenzae**, **parainfluenza**, `flu/cy` (a chemotherapy regimen), the COVID variant name FLuQE, the plain English word "gripe" (a complaint), and all non-English flu words.

## How the rules were checked
- Built from the 1,280 labeled entries, then checked against the full GDELT corpus (230,409 articles, 2015 to 2024, `raw_data/extracted_articles`): every word containing flu, grip, influ, enza, amivir or tamif was listed with context and sorted into accept or deny. Words glued to others were reviewed one by one.
- Terms are tagged `seen` (found in the sample or corpus) or `ext` (general knowledge, never seen) in the code and in the audit file.
- In the corpus, 196,683 of 230,409 articles match. The rest are mostly stub pages, error pages or text that does not match the link (GDELT tagged the original page, the page was fetched later).

## Limits
- Passing mentions count. One "flu" in an article about something else makes it flu related.
- Stomach flu, tomato flu, dog flu, bird flu all contain the word, so they are flu related here.
- A keyword list cannot find articles about flu that never use any of these words.
