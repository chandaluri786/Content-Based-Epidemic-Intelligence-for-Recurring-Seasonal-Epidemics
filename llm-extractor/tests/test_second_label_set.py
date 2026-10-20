"""Tests for running and scoring with a second label set and prompt (such as Jahnavi's track).

Covers the PROMPT_VERSION / HUMAN_LABELS_PATH overrides, the run-settings guard, the data build
that skips only the useful-vs-split check, and example answers taken from another labels file.
Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import importlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flu_extractor import config
from flu_extractor.evaluation import read_run_settings, settings_mismatch

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_data = _load_script("build_data_files")
build_prompt = _load_script("build_prompt_files")


class ConfigOverrideTest(unittest.TestCase):
    def tearDown(self):
        importlib.reload(config)  # back to the defaults for the other tests

    def test_defaults_are_the_team_prompt_and_labels(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROMPT_VERSION", None)
            os.environ.pop("HUMAN_LABELS_PATH", None)
            importlib.reload(config)
        self.assertEqual(config.SYSTEM_PROMPT_PATH.name, "system_prompt_v2.2.txt")
        self.assertEqual(config.EXAMPLES_PATH.name, "examples_v2.2.json")
        self.assertEqual(config.HUMAN_LABELS_PATH, config.PROJECT_DIR / "data" / "human_labels.json")

    def test_env_vars_choose_another_prompt_and_labels(self):
        env = {"PROMPT_VERSION": "v4.1", "HUMAN_LABELS_PATH": "data/human_labels_jahnavi.json"}
        with mock.patch.dict(os.environ, env):
            importlib.reload(config)
        self.assertEqual(config.SYSTEM_PROMPT_PATH.name, "system_prompt_v4.1.txt")
        self.assertEqual(config.EXAMPLES_PATH.name, "examples_v4.1.json")
        self.assertEqual(config.HUMAN_LABELS_PATH, config.PROJECT_DIR / "data" / "human_labels_jahnavi.json")


class RunSettingsTest(unittest.TestCase):
    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp())
        self.current = {"system_prompt": "system_prompt_v4.1.txt", "examples": "examples_v4.1.json",
                        "labels": "human_labels_jahnavi.json"}

    def save(self, **settings):
        (self.run_dir / "run_config.json").write_text(json.dumps({"model": "m", **settings}), encoding="utf-8")

    def test_a_new_run_has_no_settings_and_no_mismatch(self):
        self.assertIsNone(read_run_settings(self.run_dir))
        self.assertEqual(settings_mismatch(None, self.current), [])

    def test_a_run_without_a_labels_entry_used_the_team_labels(self):
        self.save(system_prompt="system_prompt_v2.2.txt", examples="examples_v2.2.json")
        self.assertEqual(read_run_settings(self.run_dir)["labels"], "human_labels.json")

    def test_matching_settings_pass(self):
        self.save(**self.current)
        self.assertEqual(settings_mismatch(read_run_settings(self.run_dir), self.current), [])

    def test_another_prompt_or_labels_file_is_reported(self):
        self.save(system_prompt="system_prompt_v2.2.txt", examples="examples_v2.2.json")
        mismatch = settings_mismatch(read_run_settings(self.run_dir), self.current)
        self.assertEqual(len(mismatch), 3, mismatch)
        only_labels = settings_mismatch(read_run_settings(self.run_dir), self.current, names=("labels",))
        self.assertEqual(only_labels, ["labels: the run used human_labels.json, now human_labels_jahnavi.json"])


class SecondLabelSetDataTest(unittest.TestCase):
    """The split's `useful` column holds the team's labels; a second set may disagree with it."""

    def setUp(self):
        self.sample = {i: {"record_id": i} for i in ("a", "b")}
        self.split = {"a": {"split": "dev", "useful": "yes"}, "b": {"split": "test", "useful": "no"}}
        item = build_data.convert_item({"article_id": "b", "strain": "", "kind": "cases", "number": "3",
                                        "status": "", "total_or_new": "new", "city": "", "state": "",
                                        "country": "India", "start_date": "", "end_date": "2020-01-10",
                                        "words": "", "evidence": "Three cases."})
        # Flipped against the split: a is now no, b is now yes.
        self.answers = {"a": {"labeler": "Jahnavi", "useful": "no", "items": []},
                        "b": {"labeler": "Manoj", "useful": "yes", "items": [item]}}

    def test_the_useful_flip_is_an_error_for_the_team_labels(self):
        errors = build_data.validate(self.answers, self.sample, self.split, expected_size=2)
        self.assertEqual(len(errors), 2, errors)

    def test_a_second_set_skips_only_that_check(self):
        errors = build_data.validate(self.answers, self.sample, self.split, expected_size=2,
                                     check_split_useful=False)
        self.assertEqual(errors, [])
        self.answers["b"]["items"] = []
        errors = build_data.validate(self.answers, self.sample, self.split, expected_size=2,
                                     check_split_useful=False)
        self.assertTrue(any("no items" in e for e in errors), errors)


class ExampleAnswersFromAnotherSetTest(unittest.TestCase):
    def test_answers_come_from_the_given_labels_file(self):
        root = Path(tempfile.mkdtemp())
        (root / "prompt_versions").mkdir()
        (root / "data").mkdir()
        text = "Three cases were reported."
        articles = [{"article_id": i, "split": "dev", "scan_date": "2020-01-10", "link": "https://x",
                     "article": text} for i in ("yes1", "no1")]
        item = {"kind": "cases", "number": 3, "evidence": [text]}
        team = [{"article_id": "yes1", "useful": True, "items": [item]},
                {"article_id": "no1", "useful": True, "items": [item]}]
        second = [{"article_id": "yes1", "useful": True, "items": [item]},
                  {"article_id": "no1", "useful": False, "items": []}]
        selection = [{"article_id": i, "teaches": "x", "reason": "y"} for i in ("yes1", "no1")]
        (root / "prompt_versions" / "examples_vX_selection.json").write_text(json.dumps(selection))
        (root / "data" / "articles.json").write_text(json.dumps(articles))
        (root / "data" / "human_labels.json").write_text(json.dumps(team))
        (root / "data" / "human_labels_second.json").write_text(json.dumps(second))
        with mock.patch.object(build_prompt, "PROJECT_DIR", root):
            examples = build_prompt.load_examples("vX", root / "data" / "human_labels_second.json")
        self.assertEqual([e["answer"]["useful"] for e in examples], [True, False])
        self.assertEqual(examples[1]["answer"]["items"], [])


if __name__ == "__main__":
    unittest.main()
