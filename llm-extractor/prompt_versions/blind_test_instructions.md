# Blind test of the extraction prompt

This test checks how clear the v5 prompt is. A fresh LLM session applies the prompt to one labeler's articles with no labels, no earlier results and no rulings from anyone. Its output is then compared with that labeler's chain-of-thought records.

The set-up copies the prompt and articles into a separate folder outside the capstone project. A session started inside the project would load `CLAUDE.md` and the project memory, and could open the labels.

## 1. Set up the folder

Set `NAME` to the labeler: `Jahnavi`, `Aditya`, `Manoj` or `Thanya`. Then paste the whole block into a terminal. If the folder already exists from an earlier run, the block stops so that nothing is overwritten.

```bash
NAME=Jahnavi

R=/home/chandaluri/MSDSAE/capstone
P=$R/Content-Based-Epidemic-Intelligence-for-Recurring-Seasonal-Epidemics
T=/home/chandaluri/blind_test_$NAME

if [ -e "$T" ]; then echo "$T already exists. Move or delete it first."; else
mkdir "$T" && cd "$T"
cp "$P/llm-extractor/prompt_versions/llm_extraction_prompt_v5.2.md" .
cp "$R/labeling/labeling/${NAME}_texts.txt" .
cp "$P/flu_bucketing/flu_keywords.py" .

cat > make_gate.py <<'PY'
import re, sys
from flu_keywords import is_flu_related
t = open(sys.argv[1], encoding='utf-8').read()
fail = []
n = 0
for p in re.split(r'\n(?==+\n#\d+ )', t):
    m = re.search(r'^#(\d+)\s', p, re.M)
    if m and '-' * 80 in p:
        n += 1
        if not is_flu_related(p.split('-' * 80, 1)[1]):
            fail.append(int(m.group(1)))
open('keyword_gate.txt', 'w').write('Articles checked: %d\nFailed the keyword check: %s\n' % (n, ', '.join(map(str, fail))))
print(n)
PY

COUNT=$(python3 make_gate.py "${NAME}_texts.txt")
rm -rf make_gate.py flu_keywords.py __pycache__

cat > PROMPT.txt <<EOF
You are running a blind extraction test. Work only inside the folder $T. It contains:
- $T/llm_extraction_prompt_v5.2.md: the v5 prompt, with the full instructions and rules for extracting from one article
- $T/${NAME}_texts.txt: $COUNT articles, each starting with a header like "#12 [1-own] <article_id>", then "scan date:", "link:", a dashed line, and the article text
- $T/keyword_gate.txt: the result of the project's flu keyword check on all $COUNT articles

TASK
Apply the v5 prompt to every article in ${NAME}_texts.txt, #1 to #$COUNT, in file order. Write one result per article to $T/blind_output.jsonl.

KEYWORD GATE
The v5 prompt says flu keywords are checked in code before you see an article. That check has already been run, and its result is in keyword_gate.txt. Read that file before you start. Do not look for keywords yourself; the keyword list is not available to you.
- Rows listed in keyword_gate.txt failed the check. Read each one to write the summary, then give the Rule 1 reply from the v5 prompt. Do not apply any other rule to them.
- All other rows passed the check. For these, Rule 1 is passed; apply all the rules as usual.

BLINDNESS
- Do not open, search for, or list any file outside $T.
- Do not use the web.
- Do not use any labels, earlier results or outside knowledge about these articles. The v5 prompt and the article text are your only sources.

FORWARD ONLY
- Move forward one article at a time. Once a row is written to blind_output.jsonl, it is final.
- Never go back to a finished row. Do not reread it, change it, rewrite it or delete it, even if a later article makes you think it was wrong.
- Never compare a result with the results of earlier articles. Do not look at earlier rows to check consistency, and do not use an earlier decision as a precedent.
- Treat each article independently, as if it were the only one you had seen. Decide only from the v5 prompt and that article's text.

HOW TO WORK
1. Read all of the v5 prompt before you start, every line.
2. For each article, read the complete article text word for word. Never decide from a keyword search, a snippet or a truncated view. Long articles must be read in parts until the end.
3. Follow "How to work" and "Your reply" in the v5 prompt exactly, including all rule citations and all 12 item fields. Number every reasoning step in that layout: Step 0 (summary), Step 1 (Rule 1), then Step N with its rule IDs in brackets.
4. Before writing a row, check that each of its evidence quotes appears exactly in that article, and fix any quote that does not.
5. Use scripts only to extract an article's text, to check evidence quotes, and to append a result. Never use a script to make a decision.
6. Do the work yourself. Do not start subagents.

OUTPUT
Append one JSON object per line to $T/blind_output.jsonl, right after finishing each article, with these keys in this order:
{"row": <the number after #>, "article_id": "...", "scan_date": "...", "link": "...", "summary": "...", "reasoning": [...], "useful": true or false, "reason": "...", "items": [...], "unsure": null}

"unsure" is for this test only. If the v5 prompt did not settle a decision, or two rules pointed different ways, or you had to use your own judgement, make the best decision you can, then describe it in "unsure" in one or two sentences: the statement, the rule numbers, and the other outcome you considered. Otherwise leave it null. Do not invent doubts.

NO QUESTIONS
Do not ask me anything and do not stop for a ruling. Nobody will resolve ambiguities for you. Decide and record it in "unsure". Do not edit the v5 prompt, ${NAME}_texts.txt or keyword_gate.txt.

RESUMING
If your context is reset or summarised, or you are restarted, first reread all of $T/llm_extraction_prompt_v5.2.md and $T/keyword_gate.txt. Then get only the last row number from $T/blind_output.jsonl, without reading the content of any row, and continue from the next row. Never write a result from memory or notes; read the article.

FINISH
When row $COUNT is written, use a script to check only that $T/blind_output.jsonl has exactly $COUNT valid JSON lines with rows 1 to $COUNT in order. Do not reopen or change any row. Then report the number of useful articles, the number of items, how many rows have "unsure" filled in, and any rows you could not complete.
EOF

cat keyword_gate.txt
ls
fi
```

You should see four files: `PROMPT.txt`, `keyword_gate.txt`, the v5 prompt and the labeler's `_texts.txt` file. The output also prints the article count and the rows that failed the keyword check.

## 2. Start the session

Open the new folder as the workspace, for example `/home/chandaluri/blind_test_Jahnavi`, and start a new session there. Use the same model each time so runs can be compared. Allow it to run commands and write files in that folder, or it will keep stopping for permission.

## 3. Paste the prompt

Open `PROMPT.txt` in that folder and paste its whole text as the first message. The set-up has already filled in the folder, labeler and article count.

The run is long, so the session will probably be summarised several times. If it hits a usage limit, start it again with the same prompt. The resume rule continues from the last finished row.

## 4. Compare the results

When the session reports it has finished, `blind_output.jsonl` is in the same folder. Compare it row by row with the labeler's chain-of-thought file:

1. Leave out the rows in `keyword_gate.txt`. The gate fixes them, so they are not a test.
2. Compare `useful`, then each item, then each field.
3. Use the `unsure` notes to separate gaps in the rules from slips by the session.
4. For each difference, decide which side the rules support. A difference can also be a mistake in the existing record.

## What the result means

- It shows how clear the rules are on these articles. The rules were built from them, so it does not measure accuracy on new articles. That needs a set the rules have never seen.
- `prompt_rules.md` and the v5 prompt share the same rule text. Use the v5 file: `prompt_rules.md` adds decision history that a blind session must not see.
- Each run needs a fresh copy of the current v5 prompt, so make a new folder after any rule change.
