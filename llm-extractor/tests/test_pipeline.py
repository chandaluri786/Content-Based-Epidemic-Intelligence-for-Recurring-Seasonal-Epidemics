"""Tests for the parts between the data files and the scores: building the data, the request,
choosing the articles and scoring a run. No API and no internet.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from unittest import mock

import openai

from flu_extractor import config
from flu_extractor.data_loading import Article, GoldLabel, resolve_article_id
from flu_extractor.llm_client import ModelReply
from flu_extractor.evaluation import SCORED, UNPARSEABLE, default_articles_to_run, evaluate_run
from flu_extractor.extractor import extract_article, parse_reply
from flu_extractor.places import PlaceChecker
from flu_extractor.prompt import build_messages, build_prefix_messages, format_article

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_gold_files  # noqa: E402
import select_examples  # noqa: E402

EVERY_PLACE_IS_REAL = PlaceChecker(lookup=lambda place: {"found": True, "top_match": "", "english_name": "", "addresstype": "city"})


def article(article_id="a1", text="Officials confirmed 12 new flu cases on Friday."):
    return Article(article_id=article_id, scan_date="2016-12-30", link="http://x", text=text,
                   sources=(f"Jahnavi:{article_id[1:]}",))


class PromptTest(unittest.TestCase):
    def test_article_uses_the_input_names_of_the_v5_prompt(self):
        self.assertEqual(format_article("2016-12-30", "http://x", "Text."),
                         "scan_date: 2016-12-30\nlink: http://x\narticle:\nText.")

    def test_examples_become_user_and_assistant_turns_before_the_article(self):
        example = {"article_id": "e1", "scan_date": "2016-01-01", "link": "l", "article": "Grippe ist da.",
                   "answer": {"summary": "s", "reasoning": ["Step 0"], "useful": False, "reason": "r", "items": []}}
        messages = build_messages(build_prefix_messages("RULES", [example]), article())
        self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant", "user"])
        self.assertEqual(list(json.loads(messages[2]["content"])), ["summary", "reasoning", "useful", "reason", "items"])
        self.assertIn("Grippe ist da.", messages[1]["content"])  # not escaped: ensure_ascii=False

    def test_fewshot_guide_follows_the_rules_only_when_examples_are_sent(self):
        example = {"scan_date": "d", "link": "l", "article": "a", "answer": {}}
        with_examples = build_prefix_messages("RULES", [example], "GUIDE")[0]["content"]
        self.assertTrue(with_examples.startswith("RULES") and with_examples.endswith("GUIDE"))
        self.assertEqual(build_prefix_messages("RULES", [], "GUIDE")[0]["content"], "RULES")  # zero-shot


class ExampleSelectionTest(unittest.TestCase):
    @staticmethod
    def record(useful, rules, items=()):
        return {"output": {"useful": useful, "items": list(items)}, "rules_used": rules}

    def test_slots_come_from_rules_and_items(self):
        count = {"kind": "cases", "count_type": "cumulative_subset", "status": "suspected", "words": None,
                 "strain": None, "city": None, "state": None, "country": "USA"}
        trend = dict(count, kind="trend", count_type=None, status=None, words="rising")
        self.assertEqual(select_examples.slots_of(self.record(False, ["Rule 1", "1.2", "4.7"])), {1, 3})
        self.assertEqual(select_examples.slots_of(self.record(False, ["Rule 1", "1.3"])), {2})
        self.assertEqual(select_examples.slots_of(self.record(True, ["4.5", "5.3.6"], [count, trend])),
                         {7, 10, 11, 12})

    def test_prompt_order_spreads_not_useful_and_ends_on_one(self):
        examples = [{"id": i, "useful": u} for i, u in enumerate([True, True, False, True, True, False])]
        ordered = select_examples.prompt_order(examples)
        self.assertFalse(ordered[-1]["useful"])
        self.assertEqual(sorted(e["id"] for e in ordered), list(range(6)))
        self.assertEqual([e["useful"] for e in ordered], [True, True, False, True, True, False])


class ExtractorTest(unittest.TestCase):
    def test_an_article_without_flu_is_still_sent_to_the_model(self):
        sent = []
        reply = ModelReply(text=VALID_REPLY, finish_reason="stop", prompt_tokens=1, completion_tokens=1, seconds=1.0)
        with mock.patch("flu_extractor.extractor.ask_model", lambda client, messages: sent.append(messages) or reply):
            record = extract_article(client=None, prefix_messages=[], article=article(text="Stock prices rose."))
        self.assertEqual(len(sent), 1)
        self.assertEqual(record["raw_reply"], VALID_REPLY)
        self.assertNotIn("gated", record)

    def test_parse_reply_accepts_fenced_json(self):
        parsed, error, repaired = parse_reply('```json\n{"useful": false}\n```')
        self.assertEqual((parsed, error, repaired), ({"useful": False}, None, False))

    def test_stray_quotes_from_the_article_are_repaired(self):
        # the failure seen in the runs: an article quotation copied with its double quotes unescaped
        text = '{"reasoning": ["S1 \'a "noticeable increase" in wastewater\'"], "useful": true}'
        parsed, error, repaired = parse_reply(text)
        self.assertIsNone(error)
        self.assertTrue(repaired)
        self.assertEqual(parsed["reasoning"][0], 'S1 \'a "noticeable increase" in wastewater\'')

    def test_raw_line_breaks_inside_strings_are_repaired(self):
        parsed, error, repaired = parse_reply('{"reason": "line one\nline two", "useful": false}')
        self.assertEqual((parsed["reason"], error, repaired), ("line one\nline two", None, True))

    def test_valid_escapes_are_kept_and_unrepairable_text_is_reported(self):
        parsed, _, repaired = parse_reply('{"q": "he said \\"hi\\""}')
        self.assertEqual((parsed["q"], repaired), ('he said "hi"', False))
        parsed, error, _ = parse_reply('{"useful": true, "items": [')
        self.assertIsNone(parsed)
        self.assertTrue(error.startswith("invalid JSON"))


VALID_REPLY = json.dumps({"summary": "s", "reasoning": ["Step 0 (summary): s"], "useful": False,
                          "reason": "r", "items": []})


class ValidationRetryTest(unittest.TestCase):
    """extract_article accepts only a complete, parseable, well-formed reply; otherwise it asks again
    with a note that names the problem."""

    def run_with_replies(self, *replies):
        sent = []

        def fake_ask(client, messages):
            sent.append(messages[-1]["content"])
            outcome = replies[len(sent) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            text, finish = outcome
            return ModelReply(text=text, finish_reason=finish, prompt_tokens=100, completion_tokens=10, seconds=1.0)

        with mock.patch("flu_extractor.extractor.ask_model", fake_ask):
            record = extract_article(client=None, prefix_messages=[], article=article())
        return record, sent

    def test_a_valid_first_reply_is_accepted_without_retry(self):
        record, sent = self.run_with_replies((VALID_REPLY, "stop"))
        self.assertEqual((len(sent), record["validation_retries"], record["parse_error"]), (1, 0, None))
        self.assertEqual(record["parsed"]["useful"], False)

    def test_cut_off_invalid_and_malformed_replies_are_asked_again_with_a_note(self):
        for bad, words in ((("{\"summary\": \"s\", \"reas", "length"), "cut off"),
                           (("{\"useful\": tru", "stop"), "not valid JSON"),
                           (('{"useful": false, "items": []}', "stop"), "broke the reply format")):
            with self.subTest(bad=bad):
                record, sent = self.run_with_replies(bad, (VALID_REPLY, "stop"))
                self.assertEqual(len(sent), 2)
                self.assertIn(words, sent[1])            # the second request names the problem
                self.assertNotIn("Note:", sent[0])       # the first request is the plain article
                self.assertEqual((record["validation_retries"], record["parse_error"]), (1, None))
                self.assertEqual(len(record["validation_problems"]), 1)
                self.assertEqual(record["prompt_tokens"], 200)  # both requests counted

    def test_evidence_not_copied_from_the_article_is_asked_again(self):
        item = {"kind": "cases", "number": 12, "count_type": "new", "status": "confirmed", "strain": None,
                "city": None, "state": "Illinois", "country": "USA", "start_date": "2016-12-30",
                "end_date": "2016-12-30", "words": None, "evidence": ["Officials reported a dozen flu cases."]}
        answer = {"summary": "s", "reasoning": ["Step 0 (summary): s"], "useful": True, "reason": "r", "items": [item]}
        good = dict(answer, items=[dict(item, evidence=["Officials confirmed 12 new flu cases on Friday."])])
        record, sent = self.run_with_replies((json.dumps(answer), "stop"), (json.dumps(good), "stop"))
        self.assertEqual(len(sent), 2)
        self.assertIn("not exact copies", sent[1])
        self.assertIsNone(record["invalid"])
        self.assertEqual(record["parsed"], good)

    def test_a_wrong_fixed_value_is_asked_again(self):
        item = {"kind": "trend", "number": None, "count_type": None, "status": None, "strain": None, "city": None,
                "state": "Illinois", "country": "USA", "start_date": None, "end_date": "2016-12-30",
                "words": "increasing", "evidence": ["Officials confirmed 12 new flu cases on Friday."]}
        answer = {"summary": "s", "reasoning": ["Step 0 (summary): s"], "useful": True, "reason": "r", "items": [item]}
        record, sent = self.run_with_replies((json.dumps(answer), "stop"), (VALID_REPLY, "stop"))
        self.assertEqual(len(sent), 2)
        self.assertIn("words must be one of", sent[1])

    def test_gives_up_after_the_retries_and_reports_the_last_problem(self):
        bad = ("{\"useful\": tru", "stop")
        record, sent = self.run_with_replies(*[bad] * (config.MAX_VALIDATION_RETRIES + 1))
        self.assertEqual(len(sent), config.MAX_VALIDATION_RETRIES + 1)
        self.assertIsNone(record["parsed"])
        self.assertTrue(record["parse_error"].startswith("invalid JSON"))
        # the decoding settings never change (ask_model takes none); the last request asks for a compact reply
        self.assertIn("compact", sent[-1])
        self.assertIn("do not copy any text from the article", sent[-1])

    def test_an_api_failure_is_recorded_not_raised(self):
        record, _ = self.run_with_replies(openai.APIConnectionError(request=None))
        self.assertIn("APIConnectionError", record["api_error"])


class SelectionTest(unittest.TestCase):
    def test_default_articles_are_every_labelled_article_except_examples(self):
        articles = {a.article_id: a for a in (article("a1"), article("a2"), article("a3"),
                                              article("a4"), article("a5"))}
        gold = {i: GoldLabel(i, False) for i in ("a1", "a2", "a3", "a4")}  # a5 has no gold
        self.assertEqual(default_articles_to_run(articles, gold, frozenset({"a2"})), ["a1", "a3", "a4"])
        self.assertEqual(default_articles_to_run(articles, gold, frozenset({"a2"}), frozenset({"a3"})),
                         ["a1", "a4"])

    def test_article_can_be_named_by_set_position(self):
        articles = {"a7": article("a7")}
        self.assertEqual(resolve_article_id("Jahnavi:7", articles), "a7")
        self.assertEqual(resolve_article_id("a7", articles), "a7")
        with self.assertRaises(ValueError):
            resolve_article_id("Manoj:7", articles)


class EvaluationTest(unittest.TestCase):
    ITEM = {"kind": "cases", "number": 12, "count_type": "new", "status": "confirmed", "strain": None,
            "city": None, "state": "Illinois", "country": "USA", "start_date": "2016-12-30",
            "end_date": "2016-12-30", "words": None,
            "evidence": ["Officials confirmed 12 new flu cases on Friday."]}

    def record(self, article_id, parsed, parse_error=None):
        return {"article_id": article_id, "api_error": None, "parsed": parsed, "parse_error": parse_error}

    def test_scored_rows_enter_the_headline_and_unparseable_rows_do_not(self):
        articles = {"a1": article("a1"), "a2": article("a2", text="No illness."), "a3": article("a3")}
        gold = {"a1": GoldLabel("a1", True, [self.ITEM]), "a2": GoldLabel("a2", False), "a3": GoldLabel("a3", True)}
        answer = {"summary": "s", "reasoning": ["Step 0 (summary): s", "Step 1 (Rule 1): t"], "useful": True,
                  "reason": "r", "items": [self.ITEM]}
        empty = {"summary": "s", "reasoning": ["Step 0 (summary): s"], "useful": False, "reason": "r", "items": []}
        records = {"a1": self.record("a1", answer), "a2": self.record("a2", empty),
                   "a3": self.record("a3", None, parse_error="invalid JSON")}
        evaluation = evaluate_run(records, articles, gold, EVERY_PLACE_IS_REAL)
        self.assertEqual([r.status for r in evaluation.rows], [SCORED, SCORED, UNPARSEABLE])
        self.assertEqual(evaluation.headline.articles, 2)
        self.assertEqual(evaluation.headline.metrics["f1"].mean, 1.0)  # a1 F1 1; a2 both empty, so not applicable
        self.assertEqual(evaluation.headline.metrics["exact_rate"].mean, 1.0)
        self.assertEqual(evaluation.rows[0].violations, [])


class BuildGoldFilesTest(unittest.TestCase):
    SEPARATOR = "=" * 80

    def texts(self, *articles):
        blocks = [f"{self.SEPARATOR}\n#{row}  [1-own]  {aid}\nscan date: 2016-12-30\ntagged country: USA\n"
                  f"link: http://x/{aid}\n{'-' * 80}\n{body}\n" for row, aid, body in articles]
        return "".join(blocks)

    def test_system_prompt_starts_at_the_task_section(self):
        text = build_gold_files.extract_system_prompt("# Title\n\nGenerated from x.\n\n## Task\nDo it.\n")
        self.assertEqual(text, "## Task\nDo it.\n")

    def test_only_unshared_articles_with_a_v2_record_are_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            sets = {
                "Jahnavi": [(1, "j1", "Flu in town."), (2, "j2", "Influenza rising.")],
                "Aditya": [(1, "a1", "Nothing here.")],
                "Manoj": [(1, "m1", "More flu.")],
                "Thanya": [(1, "j1", "Flu in town."), (41, "t41", "Flu again.")],
            }
            for name, articles in sets.items():
                (folder / f"{name}_texts.txt").write_text(self.texts(*articles), encoding="utf-8")
            record = lambda aid, row: {"article_id": aid, "source_rows": [{"labeler": "Jahnavi", "row": row}],  # noqa: E731
                                       "output": {"useful": False, "reason": "r", "items": []}}
            (folder / "Jahnavi_chain_of_thought_v2.jsonl").write_text(
                json.dumps(record("j1", 1)) + "\n" + json.dumps(record("j2", 2)) + "\n", encoding="utf-8")
            (folder / "Jahnavi_chain_of_thought.jsonl").write_text("not read\n", encoding="utf-8")

            articles, gold, counts = build_gold_files.build(folder, folder)
        # j1 is also Thanya row 1, so every copy goes; a1, m1, t41 have no v2 record
        self.assertEqual([a["article_id"] for a in articles], ["j2"])
        self.assertEqual([g["article_id"] for g in gold], ["j2"])
        self.assertEqual(articles[0]["sources"], ["Jahnavi:2"])
        self.assertEqual(set(articles[0]), {"article_id", "scan_date", "link", "sources", "article"})
        self.assertNotIn("tagged country", articles[0]["article"])  # header lines are never sent
        self.assertEqual((counts["removed_shared"], counts["kept"]), (1, 1))


class InputFilesTest(unittest.TestCase):
    """The real files in data/ and prompts/ are in the format the pipeline and v5.1 need."""

    def test_the_data_and_every_example_set_pass_the_v5_1_checks(self):
        from flu_extractor.data_checks import check_input_files
        for examples in sorted(config.PROMPTS_DIR.glob("examples_v5.1*.json")):
            with self.subTest(examples=examples.name):
                self.assertEqual(check_input_files(config.ARTICLES_PATH, config.GOLD_LABELS_PATH, examples), [])

    def test_bad_gold_and_examples_are_caught(self):
        from flu_extractor.data_checks import check_examples, check_gold
        articles = [{"article_id": "a1", "scan_date": "2016-12-30", "link": "l", "sources": [],
                     "article": "Officials confirmed 12 new flu cases on Friday."}]
        item = {"kind": "cases", "number": 12, "count_type": "total", "status": "confirmed", "strain": None,
                "city": None, "state": None, "country": "USA", "start_date": None, "end_date": "2016-12-30",
                "words": None, "evidence": ["Twelve cases."]}
        self.assertTrue(check_gold([{"article_id": "a1", "useful": True, "labelers": [], "items": [item]}], articles))
        answer = {"summary": "s", "reasoning": ["Step 0 (summary): s"], "useful": False, "reason": "r", "items": []}
        example = {"article_id": "a1", "scan_date": "2016-12-30", "link": "l", "article": "Other text.",
                   "answer": answer}
        problems = check_examples([example], articles)
        self.assertTrue(any("Step 1" in p for p in problems))
        self.assertTrue(any("differs" in p for p in problems))

if __name__ == "__main__":
    unittest.main()
