# Handoff: finish Thanya, build the v5 extractor, measure its accuracy

Written 2026-11-01. Paths start from `/home/chandaluri/MSDSAE/capstone/`. `P` below means `Content-Based-Epidemic-Intelligence-for-Recurring-Seasonal-Epidemics`.

Do the work in this order, because each part depends on the one before:

1. Clear the open items (Section 1).
2. Finish Thanya's set (Section 2).
3. Change the extractor for v5 and the new labels (Section 3).
4. Select the few-shot examples on development data (Section 4).
5. Measure accuracy once on the locked test set (Section 5).

## 1. Where things stand

| Set | Records | Useful | Items | State |
|---|---|---|---|---|
| Jahnavi | 320 | 91 | 262 | finished, all calls settled |
| Aditya | 320 | 79 | 187 | finished, all calls settled |
| Manoj | 320 | 97 | 305 | finished, all calls settled |
| Thanya | 0 | | | not started |

Records are in `P/llm-extractor/data/chain_of_thought/<Name>_chain_of_thought_v2.jsonl`. Ignore `Jahnavi_chain_of_thought.jsonl`, the old version.

**Open item, for Jahnavi:** the rule version header. Both files still say `prompt_rules 2026-10-30`, though the 9.3.8 line was added on 2026-11-01. Records say `prompt_rules 2026-10-31`.

Do not use these four proposals, none of which was approved: the 1.2 line on a flu claim the article rejects, the 9.3.3 reassurance line, and the G5 status-split and 4.5 past-week lines from Manoj row 306. Jahnavi wants no rule changes from row 306.

## 2. How to label Thanya's set

Read `P/llm-extractor/prompt_versions/chain_of_thought_process.md` first. It is the full process. This section gives what differs for Thanya.

**Start of a new session.** Paste this, in a session opened on `/home/chandaluri/MSDSAE/capstone`:

```text
Write the chain-of-thought records for Thanya. Read Content-Based-Epidemic-Intelligence-for-Recurring-Seasonal-Epidemics/llm-extractor/HANDOFF_thanya_evaluation_fewshot.md Section 2, then chain_of_thought_process.md, then all of llm_extraction_prompt_v5.0_draft.md in prompt_versions. Continue from the row after the last line of Thanya_chain_of_thought_v2.jsonl. Decide only from the v5 prompt and the complete article.
```

**The set.** `labeling/labeling/Thanya_texts.txt` has 320 rows and 18 fail the keyword gate. I checked the overlap by article id.

| Thanya rows | Source | Action |
|---|---|---|
| 1-20 | same articles, same order as Jahnavi 21-40 | copy the records |
| 21-40 | same articles, same order as Manoj 1-20 | copy the records |
| 41-320 | 280 new articles | write from the v5 prompt |

**Rules of the work.**

- Decide only from the v5 prompt and the whole article, word for word. Never use keyword or truncated views. The longest article is 131,851 characters, so read long ones in parts.
- Reread the v5 file after any context reset. Never write a record from notes.
- Open Thanya's labels only after the record is written, through `cmpL.py`. Never open `Thanya_labels.csv` or `Thanya_items.csv` directly before that, and do not open them to decide anything.
- A `useful` flip caused by a past ruling does not stop the work. Collect it. Send real judgement calls to Jahnavi in groups at sensible stopping points, about every 100 rows.
- For each call give the statements, the reasoning, every item with all fields and evidence, the label, and the exact call needed.
- Evidence is verbatim. First the sentence stating the event, then the other sentences in article order. Never complete a cut-off sentence. Keep forum and political text out of chat.
- **No rule changes during rows 41-320.** This is new. These rows are the locked test set (Section 5). If a row exposes a gap, give it a row-level ruling and log it in the record's `hard_case` field. Propose any rule text only after the test score exists.

**Her rulings that the prompt does not spell out.** Apply these the same way:

- A food price or shortage caused by flu in animals gives the inactive fallback, even where flu is one of several causes (Manoj 255). "African swine flu" in an article that says only flu keeps the item, strain null. If the article names African swine fever, it is not flu.
- A year total with the season ahead and no current activity gets no item.
- A named person with no stated place of illness gets no item (5.2, 5.6). A person at an event while ill can be placed there.
- A WHO "informed" or "said on" date can date a case. Countries named in WHO updates get items, dated by the stated coverage or the update line. Dominance gives an extra present item.
- "Haven't exceeded the epidemic threshold" is low.
- Season remarks: "begins", "now entering", "getting underway" are present. "Yet to see peak", "gears up", and "upon us" with "upcoming" get no item.
- A ministry advisory during a season described as high risk gets the benefit of the doubt: present (Manoj 222).
- Links and teasers get no item. Personal stories told for a general point get no item (4.1).
- County breakdowns under a state are not recorded (G5). City-level parts are. Different counts for the same period are both recorded.
- 9.6 dominance applies only when explicit. A "since the outbreak" total starts from context (4.6).

**Tools.** Save the four files at the end of this section in a scratch folder. The session scratchpad has been wiped before, so do not rely on old copies. Run everything with `NAME=Thanya`.

```bash
NAME=Thanya python3 reuse40.py          # once: writes rows 1-40
NAME=Thanya python3 a3.py 41 60         # print a batch and read all of it
NAME=Thanya python3 t1.py               # your write script, same pattern as the process file
NAME=Thanya python3 cmpL.py 41 60       # compare with the labels after writing
NAME=Thanya python3 val3.py             # full check once 320 rows exist
```

Use `NF` for rows failing the gate (`is_flu_related`), `NO` for flu statements with no item, and `rec` with `it` for items. `lib3.py` refuses rows out of order, quotes not in the article, and evidence out of order.

**Finish.** `val3.py` must print 320 lines, order ok, problems 0. Then report all flips and item clashes to Jahnavi.

`lib3.py`:

```python
# Clean helpers: reads only the articles. Never loads labels or earlier records.
import json,re
P='/home/chandaluri/MSDSAE/capstone/'
import os
NAME=os.environ.get('NAME','Aditya')
F2=P+'Content-Based-Epidemic-Intelligence-for-Recurring-Seasonal-Epidemics/llm-extractor/data/chain_of_thought/'+NAME+'_chain_of_thought_v2.jsonl'
t=open(P+'labeling/labeling/'+NAME+'_texts.txt').read(); arts={}; meta={}
for p in re.split(r'\n(?==+\n#\d+ )',t):
    m=re.search(r'^#(\d+)\s+\[[^\]]*\]\s+(\S+)\nscan date: (\S*)\nlink: (.*)$',p,re.M)
    if m and '-'*80 in p:
        i=int(m.group(1)); arts[i]=p.split('-'*80,1)[1]; meta[i]=dict(article_id=m.group(2),scan_date=m.group(3),link=m.group(4))
assert len(arts)==320
FIELDS=['kind','number','count_type','status','strain','city','state','country','start_date','end_date','words','evidence']
def it(i,**k):
    d={f:None for f in FIELDS}; d.update(k)
    assert d['evidence'],(i,'evidence')
    for q in d['evidence']: assert q in arts[i],(i,q[:70])
    pos=[arts[i].find(q) for q in d['evidence']]; assert pos[1:]==sorted(pos[1:]),(i,'order')
    return d
def rec(i,summary,stmts,steps,items,reason,hard=None):
    assert len(summary.split())<=25,(i,len(summary.split()))
    R=['Step 0 (summary): '+summary,'Step 1 (Rule 1): the article mentions flu, so Rule 1 is passed. Statements: '+stmts]
    for n,(ids,txt) in enumerate(steps,2): R.append('Step %d (%s): %s'%(n,ids,txt))
    order=[]
    for s in R:
        for m in re.findall(r'\(([^()]*)\)',s):
            for c in re.split(r',\s*',m):
                c=c.strip()
                if re.fullmatch(r'(Rule 1|G[1-5]|Section \d+|\d{1,2}\.\d(\.\d)?)',c) and c not in order: order.append(c)
    order.remove('Section 11'); order.append('Section 11')
    return dict(meta[i],source_rows=[{'labeler':NAME,'row':i}],summary=summary,reasoning=R,output={'useful':bool(items),'reason':reason,'items':items},rules_used=order,hard_case=hard,rules_version='prompt_rules 2026-10-31')
NO_TAIL=[("9.7","the article has no item, and no statement shows current flu activity with a tied place, so no fallback."),("Section 11","no valid item, so not useful.")]
def NO(i,summary,stmts,steps,reason): return rec(i,summary,stmts,steps+NO_TAIL,[],reason)
def NF(i,summary):
    return dict(meta[i],source_rows=[{'labeler':NAME,'row':i}],summary=summary,reasoning=['Step 0 (summary): '+summary,'Step 1 (Rule 1): the article never mentions flu, influenza, a flu strain, a flu drug or vaccine, or a flu-like illness, so it is not useful.'],output={'useful':False,'reason':'Not useful: the article never mentions flu, influenza, a flu strain, a flu drug or vaccine, or a flu-like illness.','items':[]},rules_used=['Rule 1'],hard_case=None,rules_version='prompt_rules 2026-10-31')
def count():
    try: return sum(1 for _ in open(F2))
    except FileNotFoundError: return 0
def append(r):
    n=count(); assert r['source_rows'][0]['row']==n+1,(r['source_rows'],n)
    with open(F2,'a') as fh: fh.write(json.dumps(r,ensure_ascii=False)+'\n')
    print('row',n+1,'items',len(r['output']['items']),'useful',r['output']['useful'])
def Q(i,start,end):
    a=arts[i]; s=a.find(start); assert s>=0,(i,start); e=a.find(end,s); assert e>=0,(i,end); return a[s:e+len(end)]
```

`a3.py`:

```python
import sys
exec(open('lib3.py').read())
n,m=int(sys.argv[1]),int(sys.argv[2])
for i in range(n,m+1):
    print('='*60); print('#',i,meta[i]['scan_date'],meta[i]['link'][:110]); print(arts[i].strip())
```

`cmpL.py`:

```python
import sys,csv
exec(open('lib3.py').read())
n,m=int(sys.argv[1]),int(sys.argv[2])
D=P+'labeling/labeling/'+NAME
Lb={int(r['row']):r for r in csv.DictReader(open(D+'_labels.csv',encoding='utf-8-sig'))}
It={}
for r in csv.DictReader(open(D+'_items.csv',encoding='utf-8-sig')): It.setdefault(r['article_id'],[]).append(r)
N={json.loads(x)['source_rows'][0]['row']:json.loads(x) for x in open(F2)}
def yes(v): return str(v).strip().lower() in('yes','true','1','y')
for i in range(n,m+1):
    r=N[i]; l=Lb[i]; li=It.get(r['article_id'],[]); mi=r['output']['items']; lu=yes(l['useful'])
    f=lu!=r['output']['useful']
    A=sorted((t['kind'],t['number'],t['country']) for t in mi if t['kind']!='trend'); B=sorted((t['kind'],int(float(t['number'])) if t['number'] else None,t['country']) for t in li if t['kind']!='trend')
    if f or A!=B or sum(t['kind']=='trend' for t in mi)!=sum(t['kind']=='trend' for t in li):
        print('#%d%s useful me=%s label=%s(%s) causes=%s notes=%s'%(i,' FLIP' if f else '',r['output']['useful'],lu,l['useful'],l['causes'][:60],l['notes'][:120]))
        for t in mi: print('   me ',t['kind'],t['number'],t['count_type'],t['status'],t['strain'],t['city'],t['state'],t['country'],t['start_date'],t['end_date'],t['words'])
        for t in li: print('   lab',t['kind'],t['number'],t['total_or_new'],t['status'],t['strain'],t['city'],t['state'],t['country'],t['start_date'],t['end_date'],t['words'],'|',t['evidence'][:110])
```

`val3.py`:

```python
exec(open('lib3.py').read())
L=[json.loads(x) for x in open(F2)]
print(len(L),'lines; order ok',[r['source_rows'][0]['row'] for r in L]==list(range(1,321)))
bad=0
for r in L:
    i=r['source_rows'][0]['row']; o=r['output']
    assert r['article_id']==meta[i]['article_id']
    if o['useful']!=bool(o['items']): bad+=1; print('useful',i)
    for t in o['items']:
        assert list(t)==FIELDS,i
        for q in t['evidence']:
            if q not in arts[i]: bad+=1; print('quote',i,q[:60])
        if not t['country'] or not t['end_date'] or t['end_date']>r['scan_date']: bad+=1; print('date/country',i)
        if t['start_date'] and t['start_date']>t['end_date']: bad+=1; print('start',i)
        if (t['kind']=='trend')!=(t['words'] is not None) or (t['kind']=='trend')==(t['number'] is not None): bad+=1; print('kind',i)
print('problems',bad,'useful',sum(r['output']['useful'] for r in L),'items',sum(len(r['output']['items']) for r in L),'hard',[r['source_rows'][0]['row'] for r in L if r['hard_case']])
```

`reuse40.py`:

```python
exec(open('lib3.py').read())
assert NAME == 'Thanya' and count() == 0
D = F2.rsplit('/', 1)[0] + '/'
def load(n): return {json.loads(x)['article_id']: json.loads(x) for x in open(D + n + '_chain_of_thought_v2.jsonl')}
J, M = load('Jahnavi'), load('Manoj')
for i in range(1, 41):
    aid = meta[i]['article_id']; r = dict((J if i <= 20 else M)[aid])
    other = r['source_rows'][0]
    r['source_rows'] = [{'labeler': 'Thanya', 'row': i}, other]
    append(r)
```

## 3. Changes the extractor needs

The code in `P/llm-extractor` was built for prompt v2.0, Jahnavi's 320 rows and her human labels. It will fail on v5 as it stands. It also uses row numbers as keys, and row numbers collide across the four sets. I have not changed any code.

### 3.1 Data

| Change | Where | Why |
|---|---|---|
| Add `scripts/build_gold_files.py` | new | Reads all four `*_texts.txt` and `*_v2.jsonl` files |
| Key everything by `article_id` | `data_loading.py`, `run_extraction.py`, `evaluation.py`, `report.py`, `inspect_row.py` | Row 41 means four different articles. The union is 1,200 unique articles |
| Write `data/gold_labels.json` | build script | One record per article: `useful`, `items`, `labelers`, `split` |
| Add `split` to each article | build script | `dev` for Jahnavi, Aditya and Manoj rows, `test` for Thanya 41-320 |
| Add `passes_keyword_gate` to each article | build script | Runs `flu_bucketing/flu_keywords.py` at build time, so the extractor stays self-contained |
| Keep human labels as a second file | `data/human_labels.json` | Rebuild for all four sets, for the second comparison in 5.3 |

The 80 overlapping articles have one record each, so de-duplicate by `article_id` and check the copies are identical.

### 3.2 Prompt and request

| Change | Where | Detail |
|---|---|---|
| Point at v5 | `config.py` | `SYSTEM_PROMPT_PATH` to `prompts/system_prompt_v5.0.txt`, `EXAMPLES_PATH` to `prompts/examples_v5.0.json` |
| Make the system prompt file | build script | From the v5 file, take everything from `## Task` to the end. Drop lines 1-3, the title and the generation note. The text of the rules stays word for word |
| Raise `MAX_TOKENS` | `config.py` | 4000 is too low. The longest record reply is 15,683 characters, roughly 4,000-5,000 tokens, and 95 percent of replies are under about 5,300 characters. Use 8000 and watch `finish_reason` |
| Change the article format | `prompt.py` | `format_article` writes "Scan date / Link / Article". v5 names the inputs `scan_date`, `link`, `article`. Use those names, in both examples and the real request |
| Update docstrings | `prompt.py` | They still refer to prompt v2.0 sections |
| Apply the keyword gate in code | `extractor.py` | If `passes_keyword_gate` is false, skip the API and write the exact Rule 1 reply. v5 tells the model this check has happened, so it must actually happen. Rule 1 text is in the v5 file. `lib3.py`'s `NF` shows the output |
| Decide on `EXTRA_BODY` | `config.py` | `enable_thinking: False` can stay, because v5 puts its reasoning inside the JSON. Check the first replies really contain the `reasoning` steps |
| Check context length | run log | With 8 examples a request is about 30,000 tokens before the article (rough estimate: 4 characters per token). The longest article adds about 35,000 more. Look up the model's limit. Do not cut articles silently. Report rows that fail as unscored |

### 3.3 Checks

Replace the schema in `flu_extractor/checks.py`:

- `REQUIRED_TOP_LEVEL` becomes `summary, reasoning, useful, reason, items`. Remove `borderline` and `findings` everywhere: `checks.py`, `evaluation.py`, `report.py`, `inspect_row.py`, `run_extraction.py` printouts.
- `REQUIRED_ITEM_FIELDS` becomes the 12 v5 fields. `total_or_new` becomes `count_type`, with values `new`, `cumulative_region`, `cumulative_subset`.
- **Remove rule (f).** It flags two items of the same kind and place with overlapping dates. G5 requires exactly that ("50 and 17", "856 and 591"), so correct replies would be marked wrong. Replace it with G3: items identical in every field except evidence.
- Change rule (g) to both directions: `useful` must equal `bool(items)`.
- Add new checks: country is present (G1); end date is present (G2); end date is on or before the scan date and within 30 days (4.7); counts have `number`, `count_type`, `status` and null `words`; trends have one of the seven `words` and null `number`, `count_type`, `status`; `reasoning` is a list beginning with Step 0.
- Add a check that evidence after the first part is in article order, as a warning only.
- Keep rule (a), the exact quote check.

### 3.4 Scoring

- `metrics.py`: replace `total_or_new` with `count_type` in `EXACT_KEY_FIELDS`. `_SIDE_BY_SIDE_COLUMNS` in `report.py` needs the same change.
- `evaluation.py`: `default_rows_to_run` must select by `split` and leave out example articles by `article_id`. Remove the `needs_relook` and missing-label logic, as gold records cover every row.
- `report.py`: add the tables in 5.3.
- `tests/`: `test_checks.py` and `test_metrics.py` use the old schema. Update them first, then the code. They need no API.
- `README.md`: rewrite sections 6, 7, 8, 9 and 13 after the code works.

## 4. Selecting the few-shot examples

No examples have been chosen. `prompts/examples_v2.0.json` is for the old schema, so do not reuse it.

### 4.1 Why selection comes after a zero-shot run

The rules already take roughly 18,000 tokens, and each example adds about 1,500 tokens to every call (median article 3,000-3,700 characters, median useful reply 2,300-2,900 characters). So examples should cover what this model actually gets wrong. A Nemotron run with no examples shows that. The earlier blind test used a different model, so its errors are only a guide, though its 27 `unsure` notes in `/home/chandaluri/blind_test/blind_output.jsonl` are useful for finding hard rules.

### 4.2 Steps

1. **Fix the development sample.** Take 200 dev articles at random, stratified by labeler and by `useful`, keeping the sample's mix of about 28 percent useful, with a fixed seed. Save the ids. Call this D. It is used to compare example sets.
2. **Build the candidate pool from the other dev articles.** Never use a Thanya row or an article in D. Remove:
   - articles failing the gate, which never reach the model;
   - articles over 6,000 characters or replies over 5,000 characters, to keep the prefix small;
   - articles with garbled text, forum text or heavy political content;
   - inactive-only records, except for the one food-link slot.

   Prefer records where the human `useful` label agrees, or where Jahnavi ruled on the row.
3. **Run zero-shot on D.** Count errors by field and by rule: `useful`, kind, `count_type`, dates, place, strain, status, word, and missed or extra items.
4. **Rank the slots.** Fill the slots in 4.3 by zero-shot error count, highest first.
5. **Pick articles.** For each slot, use the record's `rules_used` and items to list up to 3 candidates. Prefer short articles that exercise more than one slot, and spread them across countries and across cases, deaths, hospitalized and trend.
6. **Get Jahnavi's approval.** Show each candidate with article, full record and the slot it fills. These records teach the model, so she checks every field. If an example's record changes, it changes in the `v2.jsonl` file too.
7. **Compare sizes.** Run k = 4, 8 and 12 on D. Nest the sets, so the 4 are inside the 8 and the 8 inside the 12. D stays identical across runs. Pick the smallest k within 1 percentage point of the best item F1 on exact match, and check `useful` F1 did not fall.
8. **Freeze** `prompts/examples_v5.0.json`, then go to Section 5. Do not touch the set after that.

### 4.3 Slots to cover

About one third of examples should be not useful, so the model does not learn that everything has items. About 72 percent of this sample is not useful.

| # | Slot | Rules | Kind of example |
|---|---|---|---|
| 1 | Flu named, but no current activity | 1.2, 9.5 | routine vaccine advice or company news, no item |
| 2 | Flu in animals only | 1.3 | poultry outbreak, no item |
| 3 | Past or forecast | 4.1, 4.7, 9.3.8 | old total or a coming season, no item |
| 4 | Food link fallback | 1.3, 9.7 | price rise gives inactive |
| 5 | Stages for one person | 2.4, 4.3 | case, admission, death on stated days |
| 6 | Overlapping counts | G4, G5 | a total plus a weekly count, the same event told twice |
| 7 | Count and trend together | 2.3, 9.3 | "rising" plus a number |
| 8 | Fallback present, per place | 9.3.5, 9.7 | several places, no level word |
| 9 | Trend with a strain | 9.6 | general plus dominant strain gives two items |
| 10 | Place from context | 5.3.6, 5.4, 5.5 | no place in the sentence, home area vs hospital |
| 11 | Relative dates | 4.3-4.6 | weekday, "past week", "since X" |
| 12 | Subset vs region, suspected | 6.3, 7.2 | a school outbreak, pending samples |

### 4.4 How examples are stored and sent

`prompts/examples_v5.0.json` is a list. Each entry has:

```json
{"article_id": "...", "slot": 6, "scan_date": "...", "link": "...", "article": "...",
 "answer": {"summary": "...", "reasoning": ["Step 0 ...", "..."], "useful": true, "reason": "...", "items": []}}
```

Rules for building them:

- `answer` comes straight from the record: `summary`, `reasoning`, then `output.useful`, `output.reason`, `output.items`. That is the key order v5 asks for. Leave out `rules_used`, `hard_case` and `source_rows`.
- Keep the full `reasoning`. The model copies the layout, and the reasoning is what shows it how to apply the rules.
- Send them as they are sent now: system prompt, then user and assistant pairs, then the real article. `build_prefix_messages` already does this. Change `json.dumps` only if needed, and keep `ensure_ascii=False`.
- Order the examples with not-useful and useful mixed, ending on a not-useful one, so the last turn does not push the model toward items.
- Keep the prefix identical across all calls in a run.
- Replace `source_row` with `article_id`, so example articles leave scoring.

### 4.5 Changes to prompt v5

The rule text does not need to change for the few-shot step. Make only these changes:

1. Update the rules version in Section 1, then rename the file to `llm_extraction_prompt_v5.0.md`.
2. Do not paste examples into the rules. They go in chat turns. Example numbers and rule IDs in the rules stay as they are.
3. Do not add a line telling the model to copy the examples. The rules stay the authority.
4. If the zero-shot run shows a repeated misreading of a rule, change the rule through the normal protocol on dev data only, before the freeze.

## 5. Measuring accuracy

### 5.1 The locked test set

Thanya rows 41-320 are the only articles with no chain-of-thought record yet, and no rule ruling has come from them, so they are the test set: 280 articles. Going by the other sets, expect about 70 to 85 useful. Keep this split:

| Split | Articles | Used for |
|---|---|---|
| dev | 920 (Jahnavi, Aditya, Manoj; includes the 40 Thanya overlaps) | rules, examples, choosing k |
| test | 280 (Thanya 41-320) | one final score |

Nothing about the test run may feed back into the prompt. If the prompt changes after that, the old score stands as reported, and a new score needs new articles.

### 5.2 Run order

```text
1. Update tests, then code (Section 3). python -m unittest discover tests
2. One-article smoke run, read the reply
3. Zero-shot run on D
4. Examples: Section 4, k = 4, 8, 12 on D
5. Freeze prompt, examples, model and settings. Save the hashes in run_config.json
6. Three runs on test, then evaluate
```

Three runs, because the README notes the hosted model varies at temperature 0. Report the mean and the range.

### 5.3 What to report

Gold is the chain-of-thought records. Report all of these on the test set:

| Measure | Detail |
|---|---|
| `useful` | precision, recall, F1, confusion table |
| Items, exact | every field but evidence. The headline |
| Items, strict | kind, place, strain, dates |
| Items, relaxed | kind, place, strain |
| Items, by kind | cases, deaths, hospitalized, trend |
| By field | on paired items: number, dates, `count_type`, status, strain, word |
| Evidence | share of quotes found exactly in the article |
| Failures | API errors, invalid JSON, cut-off replies, reported as unscored |
| By country | the six study countries, if numbers allow |
| Against human labels | `useful` only, as a second truth |

Add these three as well:

- **With and without gated rows.** Gated rows are decided by code, not the model, so they inflate `useful` accuracy. Show the score on rows that reached the model.
- **With and without inactive-only articles.** Jahnavi wants these filtered from the weekly signal. So far: Jahnavi 71, 241, 248, 310; Aditya 17, 239, 241, 307, 310, 320; Manoj 9, 13, 37, 255. Score both ways, and ask her which is the headline before the test run. Decide it before seeing the score.
- **Confidence intervals.** Bootstrap by article, 1,000 resamples. Items in one article are not independent.

A weekly tier is worth adding to `metrics.py`: kind, country, strain and the ISO week of `end_date`. The output feeds a weekly signal, so this is closer to what matters than an exact-date match.

### 5.4 Limits to state in the write-up

- **Gold is LLM-written.** The records were written by Claude from v5 and reviewed by Jahnavi on flips and big clashes, not line by line. A model scored against them partly measures agreement with Claude. That is why the human comparison stays in the report.
- **Records vs human labels on `useful`** (records yes and human yes / records yes and human no / records no and human yes / both no): Jahnavi 82 / 9 / 0 / 229, Aditya 70 / 9 / 4 / 237, Manoj 82 / 15 / 4 / 219. These differences have not been broken down by cause yet; do that before the write-up.
- **Read depth.** Aditya and Manoj rows were read once. Jahnavi's rows 1-226 had a second full read.
- **Sample mix.** The 1,200 were drawn half from likely useful and half from likely not useful, so the useful rate here is higher than in the full pool. Scores do not carry over directly to raw news.
- **Rule edits during Aditya and Manoj.** Dev-set scores are optimistic. Only the test score is a fair estimate.
