"""Tests for the reply format check, the evidence check (rule a) and the other rule checks.

The place check (rule d) is tested in test_places.py.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import unittest

from flu_extractor.checks import (
    QUOTE_EMPTY,
    QUOTE_NOT_FOUND,
    QUOTE_TYPOGRAPHY_ONLY,
    find_quote_problem,
    find_rule_violations,
    find_shape_errors,
)
from flu_extractor.places import PlaceChecker

ARTICLE = (
    "SPRINGFIELD - Officials confirmed 12 new flu cases on Friday.\n"
    "The county total is now 85.\n"
    "“We expect more,” said Dr. Lee."
)
SCAN_DATE = "2016-12-30"
GOOD_QUOTE = "Officials confirmed 12 new flu cases on Friday."

# Here every place counts as real, so the other tests are not affected by rule (d).
EVERY_PLACE_IS_REAL = PlaceChecker(lookup=lambda field, value: {"found": True, "top_match": value})


def count_item(**changes):
    """A valid v5 count item; keyword arguments replace fields."""
    item = {
        "kind": "cases", "number": 12, "count_type": "new", "status": "confirmed", "strain": None,
        "city": "Springfield", "state": "Illinois", "country": "USA",
        "start_date": "2016-12-30", "end_date": "2016-12-30", "words": None, "evidence": [GOOD_QUOTE],
    }
    item.update(changes)
    return item


def trend_item(**changes):
    """A valid v5 trend item; keyword arguments replace fields."""
    return count_item(**{"kind": "trend", "number": None, "count_type": None, "status": None,
                         "words": "rising", **changes})


def reply(items=None, useful=None, **changes):
    """A minimal valid v5 reply. `useful` defaults to whether there are items."""
    items = [count_item()] if items is None else items
    parsed = {"summary": "Flu cases in Springfield.", "reasoning": ["Step 0 (summary): x", "Step 1 (Rule 1): y"],
              "useful": bool(items) if useful is None else useful, "reason": "x", "items": items}
    parsed.update(changes)
    return parsed


def violations(parsed):
    return find_rule_violations(parsed, ARTICLE, SCAN_DATE, EVERY_PLACE_IS_REAL)


def rules(parsed):
    """Only the rule letters of the violations, e.g. ['(a)', '(i)']."""
    return sorted(v[:3] for v in violations(parsed))


class QuoteCheckTest(unittest.TestCase):
    def test_exact_quote_passes(self):
        self.assertIsNone(find_quote_problem(GOOD_QUOTE, ARTICLE))

    def test_line_breaks_and_spacing_are_ignored(self):
        self.assertIsNone(find_quote_problem("on Friday.  The county\ntotal is now 85.", ARTICLE))

    def test_invented_sentence_fails(self):
        self.assertEqual(find_quote_problem("Officials confirmed 40 new flu cases.", ARTICLE), QUOTE_NOT_FOUND)

    def test_two_separate_sentences_joined_fail(self):
        # Both sentences are in the article, but not next to each other.
        joined = "Officials confirmed 12 new flu cases on Friday. We expect more"
        self.assertEqual(find_quote_problem(joined, ARTICLE), QUOTE_NOT_FOUND)

    def test_shortened_with_ellipsis_fails(self):
        self.assertEqual(find_quote_problem("Officials confirmed ... on Friday.", ARTICLE), QUOTE_NOT_FOUND)

    def test_empty_quote_fails(self):
        self.assertEqual(find_quote_problem("", ARTICLE), QUOTE_EMPTY)
        self.assertEqual(find_quote_problem("  \n ", ARTICLE), QUOTE_EMPTY)

    def test_straight_quotes_for_curly_quotes_are_flagged_separately(self):
        self.assertEqual(find_quote_problem('"We expect more," said Dr. Lee.', ARTICLE), QUOTE_TYPOGRAPHY_ONLY)


class ShapeTest(unittest.TestCase):
    def test_valid_reply_has_no_shape_errors(self):
        self.assertEqual(find_shape_errors(reply()), [])
        self.assertEqual(find_shape_errors(reply(items=[trend_item()])), [])

    def test_every_top_level_key_is_required(self):
        for key in ("summary", "reasoning", "useful", "reason", "items"):
            with self.subTest(key=key):
                parsed = reply()
                del parsed[key]
                self.assertIn(f"missing top-level key '{key}'", find_shape_errors(parsed))

    def test_reasoning_must_be_a_list_of_text(self):
        self.assertTrue(find_shape_errors(reply(reasoning="Step 0 ...")))
        self.assertTrue(find_shape_errors(reply(reasoning=[])))

    def test_every_item_field_is_required(self):
        item = count_item()
        del item["count_type"]
        self.assertIn("item 1 missing field 'count_type'", find_shape_errors(reply(items=[item])))

    def test_unknown_kind_and_bad_dates_are_shape_errors(self):
        self.assertTrue(find_shape_errors(reply(items=[count_item(kind="outbreak")])))
        self.assertTrue(find_shape_errors(reply(items=[count_item(end_date="2016-13-01")])))

    def test_evidence_must_be_a_non_empty_list(self):
        self.assertTrue(find_shape_errors(reply(items=[count_item(evidence=[])])))
        self.assertTrue(find_shape_errors(reply(items=[count_item(evidence=GOOD_QUOTE)])))


class RuleViolationTest(unittest.TestCase):
    def test_clean_replies_have_no_violations(self):
        self.assertEqual(violations(reply()), [])
        self.assertEqual(violations(reply(items=[trend_item()])), [])
        self.assertEqual(violations(reply(items=[])), [])

    def test_invented_evidence_is_rule_a(self):
        found = violations(reply(items=[count_item(evidence=["Officials confirmed 99 cases."])]))
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].startswith("(a)") and QUOTE_NOT_FOUND in found[0])

    def test_one_bad_quote_among_good_ones_is_still_reported(self):
        self.assertEqual(rules(reply(items=[count_item(evidence=[GOOD_QUOTE, "Made up sentence."])])), ["(a)"])

    def test_trend_fields_are_rule_b(self):
        self.assertEqual(rules(reply(items=[trend_item(words="widespread")])), ["(b)"])
        self.assertEqual(rules(reply(items=[trend_item(number=5)])), ["(b)"])

    def test_count_fields_are_rule_c(self):
        self.assertEqual(rules(reply(items=[count_item(words="rising")])), ["(c)"])
        self.assertEqual(rules(reply(items=[count_item(number=None)])), ["(c)"])
        self.assertEqual(rules(reply(items=[count_item(count_type="total")])), ["(c)"])
        self.assertEqual(rules(reply(items=[count_item(status=None)])), ["(c)"])

    def test_start_after_end_is_rule_e(self):
        self.assertEqual(rules(reply(items=[count_item(start_date="2016-12-30", end_date="2016-12-29")])), ["(e)"])

    def test_duplicates_are_rule_f_but_overlapping_counts_are_allowed(self):
        # G3: identical except evidence.
        duplicate = count_item(evidence=["The county total is now 85."])
        self.assertEqual(rules(reply(items=[count_item(), duplicate])), ["(f)"])
        # G5: "50 and 17" in overlapping periods are two valid items.
        overlapping = count_item(number=85, count_type="cumulative_region", start_date=None,
                                 evidence=["The county total is now 85."])
        self.assertEqual(violations(reply(items=[count_item(), overlapping])), [])

    def test_useful_must_agree_with_items_both_ways(self):
        self.assertEqual(rules(reply(useful=False)), ["(g)"])
        self.assertEqual(rules(reply(items=[], useful=True)), ["(g)"])

    def test_missing_country_and_end_date_are_rule_h(self):
        self.assertEqual(rules(reply(items=[count_item(city=None, state=None, country=None)])), ["(h)"])
        self.assertEqual(rules(reply(items=[count_item(start_date=None, end_date=None)])), ["(h)"])

    def test_end_date_after_scan_date_or_older_than_30_days_is_rule_i(self):
        self.assertEqual(rules(reply(items=[count_item(start_date=None, end_date="2016-12-31")])), ["(i)"])
        self.assertEqual(rules(reply(items=[count_item(start_date=None, end_date="2016-11-29")])), ["(i)"])
        self.assertEqual(violations(reply(items=[count_item(start_date=None, end_date="2016-11-30")])), [])

    def test_evidence_out_of_article_order_is_rule_j(self):
        # The first part may come from anywhere; the parts after it must follow the article.
        in_order = count_item(evidence=["The county total is now 85.", GOOD_QUOTE, "said Dr. Lee."])
        self.assertEqual(violations(reply(items=[in_order])), [])
        out_of_order = count_item(evidence=[GOOD_QUOTE, "said Dr. Lee.", "The county total is now 85."])
        self.assertEqual(rules(reply(items=[out_of_order])), ["(j)"])

    def test_reasoning_must_begin_with_step_0_rule_k(self):
        self.assertEqual(rules(reply(reasoning=["Step 1 (Rule 1): y"])), ["(k)"])


if __name__ == "__main__":
    unittest.main()
