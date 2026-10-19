"""Tests for choosing which articles a run covers, and for the guard on test articles.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import unittest

from flu_extractor.data_loading import DEV, TEST, Article, HumanLabel
from flu_extractor.evaluation import default_ids_to_run
from run_extraction import check_test_guard, parse_id_spec

SPLIT_OF = {"d1": DEV, "d2": DEV, "d3": DEV, "t1": TEST, "t2": TEST}
LABELS = {i: HumanLabel(article_id=i, labeler="Aditya", split=s, useful=False) for i, s in SPLIT_OF.items()}
ARTICLES = {i: Article(article_id=i, labeler="Aditya", split=s, scan_date="2020-01-01", link="x", text="y")
            for i, s in SPLIT_OF.items()}


class DefaultIdsTest(unittest.TestCase):
    def test_keeps_only_the_chosen_split(self):
        self.assertEqual(default_ids_to_run(LABELS, DEV, frozenset()), ["d1", "d2", "d3"])
        self.assertEqual(default_ids_to_run(LABELS, TEST, frozenset()), ["t1", "t2"])

    def test_leaves_out_examples_and_extra_exclusions(self):
        ids = default_ids_to_run(LABELS, DEV, example_ids=frozenset({"d1"}), extra_excluded_ids=frozenset({"d3"}))
        self.assertEqual(ids, ["d2"])


class TestGuardTest(unittest.TestCase):
    def test_dev_articles_need_no_flag(self):
        check_test_guard(["d1", "d2"], ARTICLES, frozenset({"t1"}), is_final=False)

    def test_test_articles_need_final(self):
        with self.assertRaises(SystemExit):
            check_test_guard(["d1", "t1"], ARTICLES, frozenset(), is_final=False)
        check_test_guard(["t1"], ARTICLES, frozenset({"d1"}), is_final=True)

    def test_examples_from_test_block_the_final_run(self):
        with self.assertRaises(SystemExit):
            check_test_guard(["t2"], ARTICLES, frozenset({"t1"}), is_final=True)


class IdSpecTest(unittest.TestCase):
    def test_comma_list(self):
        self.assertEqual(parse_id_spec(" a, b ,,c"), ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
