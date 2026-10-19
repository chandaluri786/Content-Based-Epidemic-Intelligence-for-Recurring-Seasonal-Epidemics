"""Tests for item matching and the per-article item-set outcomes.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import unittest

from flu_extractor.metrics import (
    EXACT_KEY_FIELDS,
    RELAXED_KEY_FIELDS,
    SET_BOTH_EMPTY,
    SET_EXACT,
    SET_EXTRAS_ONLY,
    SET_MISSING_ONLY,
    SET_MIXED,
    SET_NO_MATCH,
    Counts,
    ItemTally,
    classify_item_set,
    differing_fields,
    match_items,
    score_usefulness,
)


def item(kind="cases", number=658, state="New York", country="USA", start=None, end="2016-12-30",
         status=None, total_or_new="total", words=None, evidence=("a quote",)):
    return {"kind": kind, "strain": None, "number": number, "status": status, "total_or_new": total_or_new,
            "city": None, "state": state, "country": country, "start_date": start, "end_date": end,
            "words": words, "evidence": list(evidence)}


class ExactMatchTest(unittest.TestCase):
    def exact(self, human, model):
        return match_items(human, model, EXACT_KEY_FIELDS)

    def test_identical_items_match(self):
        result = self.exact([item()], [item()])
        self.assertEqual((len(result.matched), len(result.missed), len(result.extra)), (1, 0, 0))

    def test_evidence_is_not_compared(self):
        result = self.exact([item(evidence=("the human quote",))], [item(evidence=("a different quote",))])
        self.assertEqual(len(result.matched), 1)

    def test_case_and_repeated_spaces_are_ignored(self):
        result = self.exact([item(state="New York")], [item(state="new  york")])
        self.assertEqual(len(result.matched), 1)

    def test_every_other_field_must_agree(self):
        for change in ({"number": 600}, {"status": "suspected"}, {"total_or_new": "new"},
                       {"start": "2016-12-01"}, {"end": "2016-12-29"}, {"state": "Ohio"},
                       {"country": "Canada"}, {"kind": "deaths"}, {"words": "widespread"}):
            with self.subTest(change=change):
                result = self.exact([item()], [item(**change)])
                self.assertEqual((len(result.matched), len(result.missed), len(result.extra)), (0, 1, 1))

    def test_extra_item_is_counted(self):
        result = self.exact([item()], [item(), item(kind="deaths", number=3)])
        self.assertEqual((len(result.matched), len(result.missed), len(result.extra)), (1, 0, 1))

    def test_missing_item_is_counted(self):
        result = self.exact([item(), item(kind="deaths", number=3)], [item()])
        self.assertEqual((len(result.matched), len(result.missed), len(result.extra)), (1, 1, 0))

    def test_a_human_item_is_matched_only_once(self):
        # The model repeats an item the human wrote once: one match, one extra.
        result = self.exact([item()], [item(), item()])
        self.assertEqual((len(result.matched), len(result.missed), len(result.extra)), (1, 0, 1))


class DifferingFieldsTest(unittest.TestCase):
    def test_lists_only_fields_that_differ_and_never_evidence(self):
        human, model = item(number=658, end="2016-12-30"), item(number=600, end="2016-12-29", evidence=("x",))
        self.assertEqual(differing_fields(human, model), ["number", "end_date"])

    def test_identical_items_differ_in_nothing(self):
        self.assertEqual(differing_fields(item(), item()), [])

    def test_leftovers_can_be_paired_by_kind_and_place(self):
        human, model = item(number=658), item(number=600, start="2016-12-01")
        exact = match_items([human], [model], EXACT_KEY_FIELDS)
        near = match_items(exact.missed, exact.extra, RELAXED_KEY_FIELDS)
        self.assertEqual(len(near.matched), 1)
        self.assertEqual(differing_fields(*near.matched[0]), ["number", "start_date"])


class ItemSetOutcomeTest(unittest.TestCase):
    def outcome(self, human, model):
        return classify_item_set(match_items(human, model, EXACT_KEY_FIELDS))

    def test_identical_sets(self):
        self.assertEqual(self.outcome([item()], [item()]), SET_EXACT)

    def test_identical_sets_in_another_order(self):
        a, b = item(), item(kind="deaths", number=3)
        self.assertEqual(self.outcome([a, b], [b, a]), SET_EXACT)

    def test_both_empty(self):
        self.assertEqual(self.outcome([], []), SET_BOTH_EMPTY)

    def test_extras_only_including_items_on_a_not_useful_article(self):
        self.assertEqual(self.outcome([item()], [item(), item(kind="deaths", number=3)]), SET_EXTRAS_ONLY)
        self.assertEqual(self.outcome([], [item()]), SET_EXTRAS_ONLY)

    def test_missing_only_including_model_returning_nothing(self):
        self.assertEqual(self.outcome([item(), item(kind="deaths", number=3)], [item()]), SET_MISSING_ONLY)
        self.assertEqual(self.outcome([item()], []), SET_MISSING_ONLY)

    def test_mixed(self):
        self.assertEqual(self.outcome([item(), item(kind="deaths", number=3)],
                                      [item(), item(kind="trend", number=None, words="up")]), SET_MIXED)

    def test_no_match_with_items_on_both_sides(self):
        self.assertEqual(self.outcome([item()], [item(number=1)]), SET_NO_MATCH)

    def test_equal_count_is_not_enough(self):
        # One item each, but they differ: the sets are not the same.
        self.assertNotIn(self.outcome([item()], [item(number=600)]), (SET_EXACT, SET_BOTH_EMPTY))


class ScoreTest(unittest.TestCase):
    def test_tally_counts_per_kind_and_pooled(self):
        tally = ItemTally()
        tally.add(match_items([item(), item(kind="deaths", number=3)],
                              [item(), item(kind="trend", number=None, words="up")], EXACT_KEY_FIELDS))
        self.assertEqual(vars(tally.by_kind["cases"]), {"tp": 1, "fp": 0, "fn": 0})
        self.assertEqual(vars(tally.by_kind["deaths"]), {"tp": 0, "fp": 0, "fn": 1})
        self.assertEqual(vars(tally.by_kind["trend"]), {"tp": 0, "fp": 1, "fn": 0})
        self.assertEqual(vars(tally.overall()), {"tp": 1, "fp": 1, "fn": 1})

    def test_precision_recall_f1(self):
        counts = Counts(tp=2, fp=1, fn=3)
        self.assertAlmostEqual(counts.precision, 2 / 3)
        self.assertAlmostEqual(counts.recall, 2 / 5)
        self.assertAlmostEqual(counts.f1, 0.5)  # 2*2 / (2*2 + 1 + 3)

    def test_zero_hits_gives_zero_f1_and_no_division_error(self):
        self.assertEqual(Counts(tp=0, fp=2, fn=1).f1, 0.0)
        self.assertIsNone(Counts().f1)

    def test_usefulness_confusion_table(self):
        result = score_usefulness([(True, True), (True, False), (False, True), (False, False), (False, False)])
        self.assertEqual((result.counts.tp, result.counts.fn, result.counts.fp, result.true_negatives), (1, 1, 1, 2))
        self.assertAlmostEqual(result.accuracy, 3 / 5)


if __name__ == "__main__":
    unittest.main()
