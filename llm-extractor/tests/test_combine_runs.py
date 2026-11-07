"""Offline tests of scripts/combine_runs.py: several run folders into one reply per article.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from flu_extractor import config
from flu_extractor.checks import record_is_invalid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import combine_runs  # noqa: E402

GOOD = {"summary": "s", "reasoning": ["Step 0 (summary): s"], "useful": False, "reason": "r", "items": []}


def record(article_id: str, api_error=None, parse_error=None, invalid=None, parsed=GOOD) -> dict:
    return {"article_id": article_id, "api_error": api_error, "parse_error": parse_error, "invalid": invalid,
            "parsed": None if (api_error or parse_error) else parsed}


class CombineTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def run_dir(self, name: str, records: list[dict]) -> Path:
        path = self.root / name
        path.mkdir()
        (path / "raw_results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return path

    def test_api_failures_are_never_used(self):
        first = self.run_dir("fw", [record("a", api_error="412 suspended")])
        second = self.run_dir("ds", [record("a")])
        combined = combine_runs.combine([first, second])
        self.assertEqual(combined["a"]["source_run"], "ds")

    def test_a_later_valid_reply_replaces_an_earlier_one(self):
        first = self.run_dir("main", [record("a", invalid="malformed: x")])
        second = self.run_dir("rerun", [record("a")])
        combined = combine_runs.combine([first, second])
        self.assertEqual((combined["a"]["source_run"], combined["a"]["status"]), ("rerun", combine_runs.VALID))

    def test_a_later_invalid_reply_does_not_replace_an_earlier_one(self):
        first = self.run_dir("main", [record("a", invalid="malformed: x")])
        second = self.run_dir("rerun", [record("a", parse_error="reply truncated at max_tokens")])
        combined = combine_runs.combine([first, second])
        self.assertEqual((combined["a"]["source_run"], combined["a"]["status"]),
                         ("main", combine_runs.INVALID_KEPT))

    def test_within_one_run_the_last_line_counts(self):
        run = self.run_dir("main", [record("a", api_error="timeout"), record("a")])
        self.assertEqual(combine_runs.combine([run])["a"]["status"], combine_runs.VALID)

    def test_status_of_a_reply_without_an_answer(self):
        run = self.run_dir("main", [record("a", parse_error="reply truncated at max_tokens")])
        self.assertEqual(combine_runs.combine([run])["a"]["status"], combine_runs.NO_ANSWER)

    def test_the_input_records_are_not_changed(self):
        original = record("a")
        run = self.run_dir("main", [original])
        combine_runs.combine([run])
        self.assertNotIn("source_run", original)
        self.assertNotIn("source_run", (run / "raw_results.jsonl").read_text(encoding="utf-8"))

    def test_coverage_must_match_the_articles_file(self):
        combined = combine_runs.combine([self.run_dir("main", [record("a"), record("b")])])
        self.assertEqual(combine_runs.coverage_problems(combined, ["a", "b"]), [])
        problems = combine_runs.coverage_problems(combined, ["a", "c"])
        self.assertTrue(any("1 articles have no reply" in p for p in problems))
        self.assertTrue(any("1 replies are for articles not in" in p for p in problems))

    def test_a_missing_run_folder_stops(self):
        with self.assertRaises(FileNotFoundError):
            combine_runs.combine([self.root / "nope"])

    def test_summary_counts_by_source_and_status(self):
        first = self.run_dir("fw", [record("a"), record("b", invalid="malformed: x")])
        second = self.run_dir("ds", [record("c", parse_error="truncated")])
        summary = combine_runs.summarise(combine_runs.combine([first, second]))
        self.assertEqual(summary["articles"], 3)
        self.assertEqual(summary["by_source_run"], {"fw": 2, "ds": 1})
        self.assertEqual(summary["by_status"], {combine_runs.VALID: 1, combine_runs.INVALID_KEPT: 1,
                                                combine_runs.NO_ANSWER: 1})


class RecordValidityTest(unittest.TestCase):
    def test_parse_errors_and_invalid_replies_are_invalid(self):
        self.assertFalse(record_is_invalid(record("a")))
        self.assertTrue(record_is_invalid(record("a", parse_error="x")))
        self.assertTrue(record_is_invalid(record("a", invalid="malformed: x")))


class MaxTokensTest(unittest.TestCase):
    def test_the_reply_limit_can_be_set(self):
        self.assertEqual(config.parse_max_tokens(None), config.DEFAULT_MAX_TOKENS)
        self.assertEqual(config.parse_max_tokens("16000"), 16000)
        for bad in ("0", "-1", "many", "1.5"):
            with self.assertRaises(RuntimeError):
                config.parse_max_tokens(bad)


if __name__ == "__main__":
    unittest.main()
