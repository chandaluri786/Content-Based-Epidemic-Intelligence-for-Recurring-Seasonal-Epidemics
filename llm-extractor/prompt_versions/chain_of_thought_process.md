# How to write the chain-of-thought records

This is the process for writing a labeler's chain-of-thought file from the v5 prompt. Any model can follow it, and it can pick up from the last finished row. The current run is Jahnavi's. Aditya's, Thanya's and Manoj's sets follow the same way.

## To continue in a new session

Paste this as the first message, in a session opened on `/home/chandaluri/MSDSAE/capstone`:

```text
Continue writing the chain-of-thought records for Jahnavi. Read Content-Based-Epidemic-Intelligence-for-Recurring-Seasonal-Epidemics/llm-extractor/prompt_versions/chain_of_thought_process.md first and follow it exactly. Then read all of llm_extraction_prompt_v5.0_draft.md in the same folder. Continue from the row after the last line of Jahnavi_chain_of_thought_v2.jsonl. Do not open any file on the forbidden list. If the prompt does not settle a decision, stop and ask me, then resume after I answer.
```

## Files

| What | Path, from `/home/chandaluri/MSDSAE/capstone/` |
|---|---|
| Rules, the only source of decisions | `Content-Based-Epidemic-Intelligence-for-Recurring-Seasonal-Epidemics/llm-extractor/prompt_versions/llm_extraction_prompt_v5.0_draft.md` |
| Articles | `labeling/labeling/Jahnavi_texts.txt` |
| Output, one JSON line per row | `Content-Based-Epidemic-Intelligence-for-Recurring-Seasonal-Epidemics/llm-extractor/data/chain_of_thought/Jahnavi_chain_of_thought_v2.jsonl` |
| Keyword check | `Content-Based-Epidemic-Intelligence-for-Recurring-Seasonal-Epidemics/flu_bucketing/flu_keywords.py` |

**Forbidden until every row is written.** Do not open, search or print these files:
- `labeling/labeling/Jahnavi_labels.csv` and `Jahnavi_items.csv`
- `llm-extractor/data/chain_of_thought/Jahnavi_chain_of_thought.jsonl`, the earlier version
- `/home/chandaluri/blind_test*/blind_output.jsonl`
- any comparison output

`prompt_rules.md` has the same rules as the v5 prompt, plus decision history tied to row numbers. Read the v5 file only.

## Ground rules

1. **Decide only from the v5 prompt and the article.** Anything remembered from earlier work is not a source. If a remembered outcome differs from what the prompt gives, follow the prompt, or stop and ask if the prompt does not settle it.
2. **Read the whole article, word for word.** Never decide from a keyword search, snippet or truncated view. Long output must be read in parts to the end.
3. **Context decides.** Read the whole article first. Whether statements are the same event, and what period, place, kind and strain they have, come from context, whether stated directly or not. The rules show the reasoning; they are not a list of exact wordings.
4. **Stop and ask when stuck.** If the prompt does not settle a decision or two rules point different ways, write nothing for that row. Show Jahnavi the article text involved, the options, the rules, your lean, and the exact rule text that would settle it. Resume after her answer.
5. **Do not change the rules yourself.** Propose exact text and wait for her yes. After a yes, change the v5 prompt and `prompt_rules.md` together, keep their rule text identical, and check for conflicts and affected records.
6. **State the general logic in any proposed rule.** Do not write a patch shaped around one row. Examples only show the reasoning.
7. **Do not guess at results in chat.** Report only what was done and any stuck rows.

## Steps

1. Read all of the v5 prompt. Reread it after any context reset.
2. Save `lib2.py` and `a.py` from the end of this file in a scratch folder, if they are not already there.
3. Find the next row: the number of lines in the output file plus 1.
4. Print the next batch with `python3 a.py N M`. Use batches of up to about 60,000 characters, and read all of the output.
5. Check the keyword gate. For a row where `is_flu_related(body)` is false, give the Rule 1 reply with `NF`. Do not look for keywords by eye.
6. For every other row, follow "How to work" in the v5 prompt and decide all its items.
7. Write the rows with a short Python script that uses the helpers. The helpers refuse a row out of order, an evidence quote that is not in the article, or evidence out of order.
8. Report briefly after each batch, then continue.
9. After the last row, check that the file has one valid line for each article, in order, with every evidence quote found in its article. Only then may the forbidden files be opened for comparison, and Jahnavi reviews every difference.

## What a record contains

`rec(i, summary, statements, steps, items, reason)` builds one record:
- `summary`: at most 25 words.
- `statements`: every flu statement in the article, numbered S1, S2 and so on, including headlines.
- `steps`: a list of `("rule IDs", "text")` pairs, in reading order. The last pair must be `("Section 11", "...")`.
- `items`: built with `it(i, kind=..., evidence=[...])`.
- `reason`: one short sentence.

`NO(i, summary, statements, steps, reason)` is for an article with flu statements and no items; it adds the 9.7 and Section 11 steps. `NF(i, summary)` is the Rule 1 reply. `Q(i, start, end)` copies an exact quote from the article, which avoids typing errors with unusual characters.

### Layout of the reasoning
- **A count step**, in this order: number, dates, place, status, count type, strain, evidence.
- **A trend step**, in this order: date, place, word, strain, evidence.
- **Statements with no item:** give the rule and end with "No item."
- **Near the end:** a G3 or G5 step, then "Section 11".
- Cite every rule used in the brackets of its step.

### Evidence
- The first quote is the sentence stating the event. Further quotes follow in article order.
- Reading only the evidence, a person must be able to rebuild every field, including the place, date and strain. If a field comes from another sentence, quote that sentence.
- Copy the text exactly. Keep typos, and never complete a cut-off sentence.

### Example

```python
exec(open('lib2.py').read())
c = Q(85, 'Four Oklahomans have died', 'officials confirmed.')
append(rec(85, "Oklahoma reports four flu deaths since the flu season began on Sept. 1.",
  "S1 'Four Oklahomans have died due to the flu since Sept. 1, the beginning of this flu season'.",
  [("2.3, 3.2, 4.5, 4.6, 5.3.1, 5.5, 6.2, 7.2, 8.1, 10.1",
    "S1 is a count: deaths 4. Dates: the article states when the season began, so 2018-09-01 to the scan date, 2018-11-29 (4.5, 4.6). Place: Oklahoma (5.3.1, 5.5). 'Due to the flu', confirmed (6.2). The state's total, cumulative_region (7.2). Strain null (8.1). Evidence: S1 (10.1)."),
   ("G3", "one item, so no duplicates."),
   ("Section 11", "one valid item, so useful.")],
  [it(85, kind='deaths', number=4, count_type='cumulative_region', status='confirmed', state='Oklahoma', country='USA',
      start_date='2018-09-01', end_date='2018-11-29', evidence=[c])],
  "Useful: four flu deaths in Oklahoma since Sept. 1."))
```

This example shows the format only, so do not append it.

## For another labeler

In `lib2.py`, change the texts path, the output path and `'labeler':'Jahnavi'`. Change the `assert` on the article count if the set is a different size. The forbidden list then covers that labeler's labels, items and earlier records. The stored order of a set can differ, so never reuse row numbers from another labeler.

## Helpers

Save this as `lib2.py`:

```python
# Clean helpers: reads only the articles. Never loads labels or earlier records.
import json,re
P='/home/chandaluri/MSDSAE/capstone/'
F2=P+'Content-Based-Epidemic-Intelligence-for-Recurring-Seasonal-Epidemics/llm-extractor/data/chain_of_thought/Jahnavi_chain_of_thought_v2.jsonl'
t=open(P+'labeling/labeling/Jahnavi_texts.txt').read(); arts={}; meta={}
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
    return dict(meta[i],source_rows=[{'labeler':'Jahnavi','row':i}],summary=summary,reasoning=R,output={'useful':bool(items),'reason':reason,'items':items},rules_used=order,hard_case=hard,rules_version='prompt_rules 2026-10-31')
NO_TAIL=[("9.7","the article has no item, and no statement shows current flu activity with a tied place, so no fallback."),("Section 11","no valid item, so not useful.")]
def NO(i,summary,stmts,steps,reason): return rec(i,summary,stmts,steps+NO_TAIL,[],reason)
def NF(i,summary):
    return dict(meta[i],source_rows=[{'labeler':'Jahnavi','row':i}],summary=summary,reasoning=['Step 0 (summary): '+summary,'Step 1 (Rule 1): the article never mentions flu, influenza, a flu strain, a flu drug or vaccine, or a flu-like illness, so it is not useful.'],output={'useful':False,'reason':'Not useful: the article never mentions flu, influenza, a flu strain, a flu drug or vaccine, or a flu-like illness.','items':[]},rules_used=['Rule 1'],hard_case=None,rules_version='prompt_rules 2026-10-31')
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

Save this as `a.py`:

```python
import sys
exec(open('lib2.py').read())
for i in range(int(sys.argv[1]),int(sys.argv[2])+1):
    print('='*60); print('#',i,meta[i]['scan_date'],meta[i]['link']); print(arts[i].strip())
```

Keyword gate, for use in a write script:

```python
import sys
sys.path.insert(0, P + 'Content-Based-Epidemic-Intelligence-for-Recurring-Seasonal-Epidemics/flu_bucketing')
from flu_keywords import is_flu_related
```
