"""Tests for building a prompt version's example file (scripts/build_prompt_files.py).

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))  # build_prompt_files imports build_data_files from the same folder
_spec = importlib.util.spec_from_file_location("build_prompt_files", _SCRIPTS / "build_prompt_files.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

TEXT = "Headline about flu\nTwelve cases were reported today.\nA paragraph about vaccines.\nThe end."


def item(evidence: str) -> dict:
    return {"kind": "cases", "strain": None, "number": 12, "status": None, "total_or_new": "new", "city": None,
            "state": None, "country": "USA", "start_date": "2020-01-10", "end_date": "2020-01-10", "words": None,
            "evidence": [evidence]}


def make(article_id: str, useful: bool, keep_lines=None, evidence="Twelve cases were reported today."):
    entry = {"article_id": article_id, "teaches": "x", "reason": "y"}
    if keep_lines is not None:
        entry["keep_lines"] = keep_lines
    article = {"article_id": article_id, "scan_date": "2020-01-10", "link": "https://x", "article": TEXT}
    label = {"article_id": article_id, "useful": useful, "items": [item(evidence)] if useful else []}
    return entry, build.build_example(1, entry, article, label)


def problems(pairs, splits=None):
    selection, examples = [p[0] for p in pairs], [p[1] for p in pairs]
    splits = splits or {e["article_id"]: "dev" for e in selection}
    return build.example_problems(selection, examples, splits)


class TrimTest(unittest.TestCase):
    def test_keeps_chosen_lines_and_marks_the_trim(self):
        self.assertEqual(build.trim_article(TEXT, [0, 1]),
                         "Headline about flu\nTwelve cases were reported today.\n[article trimmed]")

    def test_no_keep_lines_means_the_whole_article(self):
        self.assertEqual(build.trim_article(TEXT, None), TEXT)


class ExampleTest(unittest.TestCase):
    def test_example_shape_and_answer_come_from_the_label(self):
        _, example = make("a", True)
        self.assertEqual(set(example), {"example", "article_id", "teaches", "scan_date", "link", "article", "answer"})
        self.assertEqual(example["answer"], {"useful": True, "borderline": False, "reason": "y",
                                             "items": [item("Twelve cases were reported today.")]})

    def test_clean_examples_pass(self):
        self.assertEqual(problems([make("a", True, [0, 1]), make("b", False)]), [])

    def test_a_test_article_is_refused(self):
        found = problems([make("a", True), make("b", False)], splits={"a": "test", "b": "dev"})
        self.assertTrue(any("must come from dev" in p for p in found))

    def test_evidence_cut_away_by_the_trim_is_refused(self):
        self.assertTrue(any("evidence not in" in p for p in problems([make("a", True, [0, 2]), make("b", False)])))

    def test_a_repeated_article_is_refused(self):
        self.assertTrue(any("more than once" in p for p in problems([make("a", True), make("a", True)])))

    def test_an_uneven_mix_is_refused(self):
        self.assertTrue(any("about even" in p for p in problems([make(str(n), True) for n in range(4)])))


if __name__ == "__main__":
    unittest.main()
