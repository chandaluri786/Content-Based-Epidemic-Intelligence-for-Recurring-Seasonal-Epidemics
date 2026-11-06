"""Tests for the extraction evaluation: normalization, matching, field scoring, duplicates,
article and dataset aggregation, evidence checks. No API and no internet.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flu_extractor.duplicates import (
    DUPLICATE, EXACT, NEAR, POSSIBLE, REPEAT, adjudicated_gold, classify_model_extras, find_groups, load_adjudication,
)
from flu_extractor.evaluation import score_items, summarize, RowResult
from flu_extractor.evidence import check_item
from flu_extractor.field_scoring import EXTRA_VALUE, MATCH, MISSING_VALUE, WRONG, score_pair
from flu_extractor.matching import MATCH_THRESHOLD, best_first_pairs, match_article
from flu_extractor.metrics import Counts, describe, drop_inactive_only, interval, score_usefulness
from flu_extractor.normalization import MISSING, normalize_item, normalize_value


def count(kind="cases", number=12, count_type="new", status="confirmed", strain=None, city=None,
          state="Illinois", country="USA", start="2016-12-30", end="2016-12-30", evidence=None):
    return {"kind": kind, "number": number, "count_type": count_type, "status": status, "strain": strain,
            "city": city, "state": state, "country": country, "start_date": start, "end_date": end,
            "words": None, "evidence": evidence or ["Officials confirmed 12 new flu cases on Friday."]}


def trend(words="rising", state="Illinois", country="USA", strain=None, evidence=None):
    return {"kind": "trend", "number": None, "count_type": None, "status": None, "strain": strain,
            "city": None, "state": state, "country": country, "start_date": "2016-12-30",
            "end_date": "2016-12-30", "words": words, "evidence": evidence or ["Flu is rising in Illinois."]}


class NormalizationTest(unittest.TestCase):
    def test_case_spaces_and_punctuation_are_harmless(self):
        self.assertEqual(normalize_value("  New   York "), "new york")
        self.assertEqual(normalize_value("O’Hare"), normalize_value("O'Hare"))

    def test_meaningful_values_are_kept(self):
        self.assertNotEqual(normalize_value("new"), normalize_value("cumulative_region"))
        self.assertEqual(normalize_value(12), 12)

    def test_absent_field_is_not_null(self):
        item = count()
        del item["strain"]
        self.assertIs(normalize_item(item)["strain"], MISSING)
        self.assertIsNone(normalize_item(count())["strain"])


class MatchingTest(unittest.TestCase):
    # Jahnavi's three drawings. Rows G1-G3 are gold items 0-2, columns I1-I3 model items 0-2;
    # only similarities of at least 0.8 are allowed pairs.
    def test_drawing_1_best_partners_first_not_the_most_pairs(self):
        allowed = {(0, 0): 0.8, (0, 1): 0.9, (1, 2): 1.0, (2, 1): 0.8, (2, 2): 0.9}
        self.assertEqual(best_first_pairs(allowed), [(1, 2), (0, 1)])   # G2-I3, G1-I2; G3 miss, I1 extra

    def test_drawing_2_a_tie_resolves_itself_when_one_item_is_taken(self):
        # G1: I1 0.8, I3 0.9, I2 0.9; G2: I2 1.0; G3: I3 0.8, I2 0.9 (I2 is model item 1, I3 model item 2)
        allowed = {(0, 0): 0.8, (0, 2): 0.9, (0, 1): 0.9, (1, 1): 1.0, (2, 2): 0.8, (2, 1): 0.9}
        self.assertEqual(best_first_pairs(allowed), [(1, 1), (0, 2)])   # G2-I2, G1-I3; G3 miss, I1 extra

    def test_drawing_3_ties_go_to_the_pair_with_fewest_other_options(self):
        # G1: I1 0.8, I3 0.9, I2 0.9; G2: I2 0.8; G3: I3 0.8, I2 0.9. Three pairs tie at 0.9;
        # G1-I2 has 4 other options, G1-I3 and G3-I2 have 3; article order then picks G1-I3.
        allowed = {(0, 0): 0.8, (0, 2): 0.9, (0, 1): 0.9, (1, 1): 0.8, (2, 2): 0.8, (2, 1): 0.9}
        self.assertEqual(best_first_pairs(allowed), [(0, 2), (2, 1)])   # G1-I3, G3-I2; G2 miss, I1 extra

    def test_full_ties_fall_back_to_article_order(self):
        self.assertEqual(best_first_pairs({(1, 1): 0.9, (0, 1): 0.9, (1, 0): 0.9, (0, 0): 0.9}), [(0, 0), (1, 1)])

    def test_identical_items_pair_and_one_gold_item_matches_once(self):
        result = match_article([count()], [count(), count()])
        self.assertEqual(len(result.pairs), 1)
        self.assertEqual(result.unmatched_model, [1])

    def test_other_country_or_trend_versus_count_never_pairs(self):
        self.assertEqual(match_article([count()], [count(country="Canada")]).pairs, [])
        self.assertEqual(match_article([trend()], [count()]).pairs, [])

    def test_a_weak_resemblance_is_rejected_by_the_threshold(self):
        weak = count(number=99, count_type="cumulative_region", status="suspected", strain="H1N1",
                     city="Chicago", state="Ohio", start="2016-01-01", end="2016-01-31")
        result = match_article([count()], [weak])
        self.assertEqual(result.pairs, [])
        self.assertEqual(len(result.rejected), 1)
        self.assertLess(result.rejected[0][2], MATCH_THRESHOLD)

    def test_threshold_is_0_8_two_wrong_count_fields_or_one_wrong_trend_field(self):
        self.assertEqual(MATCH_THRESHOLD, 0.8)
        two_wrong = count(number=13, status="suspected")                      # 8 of 10 agree: a hit
        three_wrong = count(number=13, status="suspected", strain="H1N1")    # 7 of 10: not a hit
        self.assertEqual(len(match_article([count()], [two_wrong]).pairs), 1)
        self.assertEqual(len(match_article([count()], [three_wrong]).pairs), 0)
        self.assertEqual(len(match_article([trend()], [trend(words="falling")]).pairs), 1)            # 7 of 8
        self.assertEqual(len(match_article([trend()], [trend(words="falling", strain="H1N1")]).pairs), 0)  # 6 of 8

    def test_a_strong_pair_is_never_given_up_for_more_pairs(self):
        # Through match_article: gold g0 is closest to model m1 (0.9) though that leaves g1 unpaired.
        scores = {(0, 0): 0.8, (0, 1): 0.9, (1, 1): 0.8}
        items = [count(number=i) for i in range(2)]
        with mock.patch("flu_extractor.matching.is_candidate", lambda g, m: (g["number"], m["number"]) in scores), \
             mock.patch("flu_extractor.matching.compatibility", lambda g, m: scores[(g["number"], m["number"])]):
            result = match_article(items, items)
        self.assertEqual([(g, m) for g, m, _ in result.pairs], [(0, 1)])
        self.assertEqual((result.unmatched_gold, result.unmatched_model), ([1], [0]))
        self.assertEqual(result.rejected, [(1, 1, 0.8)])   # the miss's closest item was taken by g0

    def test_cross_kind_pairs_only_take_what_same_kind_pairs_leave(self):
        gold = [count(kind="cases", number=1, start="2017-11-27", end="2017-11-27"),
                count(kind="hospitalized", number=1, start="2017-11-28", end="2017-11-28")]
        model = [count(kind="hospitalized", number=1, start="2017-11-27", end="2017-11-27")]
        result = match_article(gold, model)
        self.assertEqual([(g, m) for g, m, _ in result.pairs], [(1, 0)])  # hospitalized with hospitalized
        alone = match_article([gold[0]], model)
        self.assertEqual([(g, m) for g, m, _ in alone.pairs], [(0, 0)])   # a kind confusion, when nothing else fits


class FieldScoringTest(unittest.TestCase):
    def test_null_handling(self):
        pair = score_pair(count(strain="H1N1", city=None, number=12),
                          count(strain=None, city="Chicago", number=13))
        results = {f.name: f.result for f in pair.fields}
        self.assertEqual(results["strain"], MISSING_VALUE)
        self.assertEqual(results["city"], EXTRA_VALUE)
        self.assertEqual(results["number"], WRONG)
        self.assertEqual(results["state"], MATCH)
        self.assertFalse(pair.exact)

    def test_only_fields_of_the_kind_are_scored_and_evidence_never(self):
        self.assertEqual(score_pair(count(), count(evidence=["Other words."])).applicable, 10)
        self.assertTrue(score_pair(count(), count(evidence=["Other words."])).exact)
        self.assertEqual(score_pair(trend(), trend()).applicable, 8)


class DuplicatesTest(unittest.TestCase):
    def test_exact_and_near_groups(self):
        items = [count(), count(evidence=["Another sentence."]), count(start="2016-12-29")]
        self.assertEqual([(g.indexes, g.category) for g in find_groups(items[:2])], [((0, 1), EXACT)])
        self.assertEqual(find_groups([items[0], items[2]])[0].category, NEAR)

    def test_other_places_or_a_total_and_its_part_are_never_candidates(self):
        self.assertEqual(find_groups([count(state="Illinois"), count(state="Ohio")]), [])
        self.assertEqual(find_groups([count(number=50), count(number=17)]), [])
        self.assertEqual(find_groups([count(status="confirmed"), count(status="suspected")]), [])

    def test_model_repeat_versus_possible_duplicate(self):
        model = [count(), count(), count(evidence=["Some other sentence."])]
        labels = classify_model_extras(model, matched={0}, unmatched=[1, 2])
        self.assertEqual(labels, {1: REPEAT, 2: POSSIBLE})

    def test_adjudication_reduces_only_confirmed_gold_duplicates(self):
        gold = [count(), count(evidence=["Another sentence."])]
        kept, reviews = adjudicated_gold("a1", gold, {})
        self.assertEqual((len(kept), reviews[0]["decision"]), (2, "not reviewed"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "adjudication.json"
            path.write_text(json.dumps([{"article_id": "a1", "item_indexes": [0, 1], "decision": DUPLICATE,
                                         "reason": "the same patient"}]), encoding="utf-8")
            kept, reviews = adjudicated_gold("a1", gold, load_adjudication(path))
        self.assertEqual((len(kept), reviews[0]["decision"]), (1, DUPLICATE))


class ArticleOutcomeTest(unittest.TestCase):
    def test_conventions_for_empty_sides(self):
        both_empty = score_items([], [])
        self.assertTrue(both_empty.empty_both)
        self.assertIsNone(both_empty.f1)
        only_model = score_items([], [count()])
        self.assertEqual((only_model.f1, only_model.precision, only_model.recall), (0.0, 0.0, None))
        only_gold = score_items([count()], [])
        self.assertEqual((only_gold.f1, only_gold.recall, only_gold.precision), (0.0, 0.0, None))
        self.assertIsNone(only_gold.attribute_accuracy)

    def test_event_and_attribute_scores_are_separate(self):
        # Found the event, one field wrong: event F1 1, attribute accuracy 0.9, not exact.
        outcome = score_items([count()], [count(number=13)])
        self.assertEqual((outcome.f1, outcome.attribute_accuracy, outcome.exact_rate), (1.0, 0.9, 0.0))


class SummaryTest(unittest.TestCase):
    def rows(self, n):
        return [RowResult(article_id=f"a{i}", sources=(), status="scored", gold_useful=True,
                          model_useful=True) for i in range(n)]

    def test_metrics_are_per_article_then_summarised_with_each_article_weighing_the_same(self):
        outcomes = [score_items([count()], [count()]),                         # recall 1, precision 1, F1 1
                    score_items([count(), count(state="Ohio")], [count()]),    # recall 0.5, precision 1, F1 2/3
                    score_items([count()], [trend()]),                         # recall 0, precision 0, F1 0
                    score_items([], []),                                       # no metric defined
                    score_items([], [count()])]                                # precision 0, F1 0, no recall
        s = summarize(self.rows(5), outcomes)
        recall, precision, f1 = (s.metrics[n] for n in ("recall", "precision", "f1"))
        self.assertEqual((recall.articles, recall.not_applicable), (3, 2))   # gold has items in 3
        self.assertAlmostEqual(recall.mean, (1 + 0.5 + 0) / 3)
        self.assertEqual(precision.articles, 4)                               # the model wrote items in 4
        self.assertAlmostEqual(precision.mean, (1 + 1 + 0 + 0) / 4)
        self.assertEqual(f1.articles, 4)                                      # both empty: not applicable
        self.assertAlmostEqual(f1.mean, (1 + 2 / 3 + 0 + 0) / 4)
        self.assertEqual((f1.share_one, f1.share_zero), (0.25, 0.5))
        self.assertEqual((s.counts.tp, s.counts.fn, s.counts.fp), (2, 2, 2))  # context only
        self.assertIsNotNone(s.intervals["f1"])

    def test_buckets_put_each_article_in_one_place(self):
        outcomes = [score_items([count()], [count()]),                         # all found, exact
                    score_items([count(), count(state="Ohio")], [count()]),    # some found
                    score_items([count()], [trend()]),                         # nothing found
                    score_items([], []),                                       # empty, correct
                    score_items([], [count()])]                                # empty, false items
        s = summarize(self.rows(5), outcomes)
        self.assertEqual((s.all_found, s.all_found_and_exact, s.some_found, s.none_found), (1, 1, 1, 1))
        self.assertEqual((s.gold_nonempty, s.gold_empty, s.both_empty, s.false_items_on_empty), (3, 2, 1, 1))

    def test_details_cover_only_articles_with_a_hit(self):
        # Article 1: one hit, 1 of 10 fields wrong (0.9). Article 2: a trend hit, 1 of 8 wrong (0.875).
        # Article 3: no hit, so it has no accuracy and is left out (not counted as 0).
        outcomes = [score_items([count()], [count(number=13)]),
                    score_items([trend()], [trend(words="falling")]),
                    score_items([count()], [])]
        s = summarize(self.rows(3), outcomes)
        accuracy = s.metrics["accuracy"]
        self.assertEqual((accuracy.articles, accuracy.not_applicable), (2, 1))
        self.assertAlmostEqual(accuracy.mean, (0.9 + 0.875) / 2)
        self.assertEqual(s.metrics["exact_rate"].mean, 0.0)
        self.assertEqual((s.fields["number"].articles, s.fields["number"].mean), (1, 0.0))   # counts only
        self.assertEqual((s.fields["words"].articles, s.fields["words"].mean), (1, 0.0))     # trends only
        self.assertEqual(s.fields["country"].mean, 1.0)

    def test_a_repeated_model_item_is_an_extra_and_is_counted_as_a_repeat(self):
        outcomes = [score_items([count()], [count(), count()])]
        s = summarize(self.rows(1), outcomes)
        self.assertEqual((s.counts.tp, s.counts.fp, s.duplicate_extras), (1, 1, 1))

    def test_the_plots_are_written(self):
        from flu_extractor.plots import write_plots
        outcomes = [score_items([count()], [count(number=13)]), score_items([], [count()]), score_items([], [])]
        s = summarize(self.rows(3), outcomes)
        with tempfile.TemporaryDirectory() as folder:
            write_plots(s, outcomes, Path(folder))
            names = sorted(p.name for p in Path(folder).iterdir())
        self.assertEqual(names, ["plot_article_buckets.png", "plot_article_counts.png",
                                 "plot_article_metrics.png", "plot_field_accuracy.png"])

    def test_two_identical_gold_items_need_two_model_items(self):
        # Two people with identical fields: each gold item can be matched once only.
        outcome = score_items([count(), count()], [count()])
        self.assertEqual((outcome.tp, outcome.fn, outcome.fp), (1, 1, 0))


class MetricsTest(unittest.TestCase):
    def test_counts_and_usefulness(self):
        self.assertEqual(Counts(0, 0, 3).f1, 0.0)
        result = score_usefulness([(True, True), (True, False), (False, True), (False, False)])
        self.assertEqual((result.counts.tp, result.counts.fn, result.counts.fp, result.true_negatives), (1, 1, 1, 1))

    def test_distribution_and_not_applicable(self):
        d = describe([0.0, 0.5, 1.0, None])
        self.assertEqual((d.articles, d.not_applicable, d.median, d.share_zero, d.share_one), (3, 1, 0.5, 1 / 3, 1 / 3))

    def test_bootstrap_is_repeatable(self):
        values = [0.0, 1.0, 0.5, 0.5]
        mean = lambda s: sum(values[i] for i in s) / len(s)  # noqa: E731
        self.assertEqual(interval(mean, 4), interval(mean, 4))

    def test_inactive_only_articles_count_as_empty(self):
        self.assertEqual(drop_inactive_only([trend(words="inactive")]), [])
        self.assertEqual(len(drop_inactive_only([trend(words="inactive"), count()])), 2)


class EvidenceTest(unittest.TestCase):
    ARTICLE = "Officials confirmed 12 new flu cases on Friday. Five people in Chicago have H1N1."

    def test_quotes_and_values(self):
        ev = check_item(count(city="Chicago", strain="H1N1"), self.ARTICLE)
        self.assertEqual((ev.verbatim, ev.not_found, ev.number_found, ev.city_found, ev.strain_found),
                         (1, 0, True, True, True))
        words = check_item(count(number=5, evidence=["Invented."]), self.ARTICLE)
        self.assertEqual((words.number_found, words.not_found, words.verifiable), (True, 1, False))


if __name__ == "__main__":
    unittest.main()
