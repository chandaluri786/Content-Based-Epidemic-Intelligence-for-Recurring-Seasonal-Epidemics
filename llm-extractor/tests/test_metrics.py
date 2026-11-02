"""Tests for item matching and the per-article item-set outcomes.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import unittest

from flu_extractor.metrics import (
    EXACT_KEY_FIELDS,
    RELAXED_KEY_FIELDS,
    WEEKLY_KEY_FIELDS,
    SET_BOTH_EMPTY,
    SET_EXACT,
    SET_EXTRAS_ONLY,
    SET_MISSING_ONLY,
    SET_MIXED,
    SET_NO_MATCH,
    Counts,
    ItemTally,
    align_items,
    bootstrap_f1_interval,
    item_similarity,
    macro_average,
    score_article,
    classify_item_set,
    differing_fields,
    drop_inactive_only,
    match_items,
    score_usefulness,
)


def item(kind="cases", number=658, state="New York", country="USA", start=None, end="2016-12-30",
         status="confirmed", count_type="cumulative_region", words=None, evidence=("a quote",)):
    return {"kind": kind, "strain": None, "number": number, "status": status, "count_type": count_type,
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
        for change in ({"number": 600}, {"status": "suspected"}, {"count_type": "new"},
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


class WeeklyMatchTest(unittest.TestCase):
    def test_same_iso_week_matches_even_with_other_dates_and_place_below_country(self):
        # 2016-12-26 (Monday) and 2016-12-30 (Friday) are both in ISO week 2016-W52.
        result = match_items([item(end="2016-12-30", state="New York")],
                             [item(end="2016-12-26", state="Ohio", number=1)], WEEKLY_KEY_FIELDS)
        self.assertEqual(len(result.matched), 1)

    def test_another_week_does_not_match(self):
        result = match_items([item(end="2016-12-30")], [item(end="2016-12-25")], WEEKLY_KEY_FIELDS)
        self.assertEqual(len(result.matched), 0)


class FilterAndIntervalTest(unittest.TestCase):
    def test_inactive_only_articles_count_as_empty(self):
        inactive = item(kind="trend", number=None, status=None, count_type=None, words="inactive")
        self.assertEqual(drop_inactive_only([inactive, inactive]), [])
        self.assertEqual(len(drop_inactive_only([inactive, item()])), 2)
        self.assertEqual(drop_inactive_only([]), [])

    def test_bootstrap_interval_is_ordered_and_repeatable(self):
        counts = [(1, 0, 0), (0, 1, 0), (2, 0, 1), (0, 0, 1), (3, 1, 0)]
        low, high = bootstrap_f1_interval(counts, resamples=200)
        self.assertLessEqual(low, high)
        self.assertEqual(bootstrap_f1_interval(counts, resamples=200), (low, high))
        self.assertIsNone(bootstrap_f1_interval([]))


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


class PerArticleScoreTest(unittest.TestCase):
    def trend(self, words="rising", end="2016-12-30", country="USA"):
        return item(kind="trend", number=None, status=None, count_type=None, words=words, end=end,
                    country=country, start=end)

    def test_similarity_is_the_share_of_applicable_fields(self):
        self.assertEqual(item_similarity(item(), item()), 1.0)
        # a count compares 8 fields; one wrong end date costs 1/8
        self.assertEqual(item_similarity(item(), item(end="2016-12-29")), 7 / 8)
        # a trend compares 6 fields; the word and both dates wrong cost 3/6
        self.assertEqual(item_similarity(self.trend(), self.trend(words="high", end="2016-12-29")), 3 / 6)

    def test_other_kind_or_country_is_never_aligned(self):
        self.assertIsNone(item_similarity(item(), item(kind="deaths")))
        self.assertIsNone(item_similarity(item(), item(country="Canada")))

    def test_alignment_prefers_the_most_similar_pair(self):
        gold = [item(number=10), item(number=20)]
        model = [item(number=20, end="2016-12-29"), item(number=10)]
        pairs = align_items(gold, model)
        self.assertEqual([(g["number"], m["number"]) for g, m, _ in pairs], [(10, 10), (20, 20)])

    def test_exact_and_partial_credit_for_one_article(self):
        gold = [item(number=10), item(kind="deaths", number=2), self.trend()]
        model = [item(number=10), item(kind="deaths", number=2, end="2016-12-29"), item(kind="hospitalized")]
        score = score_article(gold, model)
        self.assertEqual((score.exact_matches, score.gold_items, score.model_items), (1, 3, 3))
        self.assertAlmostEqual(score.exact_f1, 2 * 1 / 6)
        # partial credit: 1 (exact) + 7/8 (one date wrong); the trend and the hospitalized item score 0
        self.assertAlmostEqual(score.soft_matches, 1 + 7 / 8)
        self.assertAlmostEqual(score.soft_f1, 2 * (1 + 7 / 8) / 6)

    def test_no_items_on_either_side_is_not_scored(self):
        score = score_article([], [])
        self.assertFalse(score.has_items)
        self.assertIsNone(score.exact_f1)
        self.assertIsNone(score.soft_f1)

    def test_items_on_one_side_only_score_zero(self):
        self.assertEqual(score_article([item()], []).exact_f1, 0.0)
        self.assertEqual(score_article([], [item()]).soft_f1, 0.0)
        self.assertIsNone(score_article([], [item()]).exact_recall)  # no gold items: recall undefined

    def test_macro_average_gives_every_article_one_vote(self):
        # one big article fully right, two small ones fully wrong: macro 1/3, whatever the item counts
        result = macro_average([1.0, 0.0, 0.0, None])
        self.assertAlmostEqual(result.mean, 1 / 3)
        self.assertEqual(result.articles, 3)
        low, high = result.interval
        self.assertLessEqual(low, result.mean)
        self.assertGreaterEqual(high, result.mean)
        self.assertIsNone(macro_average([None]).mean)


if __name__ == "__main__":
    unittest.main()
