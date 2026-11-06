"""Tests for the three check layers of checks.py against the prompt (v5.2): the reply format with every
fixed value, the evidence copied from the article, and the rule checks (with v5.2's G4 and G5). No API and no internet.

The place lookup itself is tested in test_places.py.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import unittest

from flu_extractor.checks import (
    QUOTE_EMPTY,
    QUOTE_NOT_FOUND,
    QUOTE_TYPOGRAPHY_ONLY,
    find_evidence_errors,
    find_format_errors,
    find_quote_problem,
    find_rule_violations,
    is_valid_strain,
)
from flu_extractor.places import PlaceChecker

ARTICLE = (
    "SPRINGFIELD - Officials confirmed 12 new flu cases on Friday.\n"
    "The county total is now 85.\n"
    "“We expect more,” said Dr. Lee."
)
SCAN_DATE = "2016-12-30"
GOOD_QUOTE = "Officials confirmed 12 new flu cases on Friday."

# Here every place counts as real and is called what it is written, so rule (d) stays quiet.
EVERY_PLACE_IS_REAL = PlaceChecker(lookup=lambda place: {"found": True, "top_match": "", "english_name": "", "addresstype": "city"})


def count_item(**changes):
    """A valid count item; keyword arguments replace fields."""
    item = {
        "kind": "cases", "number": 12, "count_type": "new", "status": "confirmed", "strain": None,
        "city": "Springfield", "state": "Illinois", "country": "USA",
        "start_date": "2016-12-30", "end_date": "2016-12-30", "words": None, "evidence": [GOOD_QUOTE],
    }
    item.update(changes)
    return item


def trend_item(**changes):
    """A valid trend item; keyword arguments replace fields."""
    return count_item(**{"kind": "trend", "number": None, "count_type": None, "status": None,
                         "words": "rising", **changes})


def reply(items=None, useful=None, **changes):
    """A minimal valid reply. `useful` defaults to whether there are items."""
    items = [count_item()] if items is None else items
    parsed = {"summary": "Flu cases in Springfield.", "reasoning": ["Step 0 (summary): x", "Step 1 (Rule 1): y"],
              "useful": bool(items) if useful is None else useful, "reason": "x", "items": items}
    parsed.update(changes)
    return parsed


def format_errors(**item_changes):
    return find_format_errors(reply([count_item(**item_changes)]))


def violations(parsed):
    return find_rule_violations(parsed, ARTICLE, SCAN_DATE, EVERY_PLACE_IS_REAL)


class FormatTest(unittest.TestCase):
    """Layer 1: the reply format and every value the prompt fixes."""

    def test_valid_replies_have_no_format_errors(self):
        self.assertEqual(find_format_errors(reply()), [])
        self.assertEqual(find_format_errors(reply([trend_item()])), [])
        self.assertEqual(find_format_errors(reply([])), [])

    def test_every_top_level_key_is_required(self):
        broken = reply()
        del broken["reason"]
        self.assertIn("reason", find_format_errors(broken)[0])

    def test_text_fields_and_useful_have_their_types(self):
        self.assertTrue(find_format_errors(reply(reasoning="Step 0")))
        self.assertTrue(find_format_errors(reply(summary="")))
        self.assertTrue(find_format_errors(reply(useful="yes")))

    def test_every_item_field_is_required_and_no_others(self):
        item = count_item()
        del item["words"]
        self.assertIn("words", find_format_errors(reply([item]))[0])
        self.assertTrue(format_errors(confidence=0.9))

    def test_kinds_count_types_statuses_and_trend_words_are_fixed_sets(self):
        self.assertTrue(format_errors(kind="vaccinations"))
        self.assertTrue(format_errors(count_type="total"))
        self.assertTrue(format_errors(status="probable"))
        self.assertTrue(find_format_errors(reply([trend_item(words="increasing")])))

    def test_trend_and_count_fields_follow_the_kind(self):
        self.assertTrue(find_format_errors(reply([trend_item(number=5)])))
        self.assertTrue(find_format_errors(reply([trend_item(status="confirmed")])))
        self.assertTrue(format_errors(words="high"))
        self.assertTrue(format_errors(number=None))
        self.assertTrue(format_errors(number=0))      # zero is a trend (inactive), never a count
        self.assertTrue(format_errors(number=2.5))
        self.assertTrue(format_errors(number="12"))

    def test_strain_values_of_8_1(self):
        for good in (None, "H1N1", "H3N2v", "H5", "H7N9", "influenza A", "influenza B", "avian influenza"):
            self.assertTrue(is_valid_strain(good), good)
        for bad in ("h1n1", "swine flu", "Influenza A", "bird flu", "flu", "H1N1 and H3N2"):
            self.assertFalse(is_valid_strain(bad), bad)
        self.assertTrue(format_errors(strain="swine flu"))

    def test_country_end_date_and_the_place_chain_are_required(self):
        self.assertTrue(format_errors(country=None))                  # G1
        self.assertTrue(format_errors(end_date=None))                 # G2
        self.assertTrue(format_errors(state=None))                    # a city needs a state (5.1)
        self.assertEqual(format_errors(city=None, state=None), [])    # country alone is allowed
        self.assertTrue(format_errors(state=""))

    def test_dates_are_real_iso_dates_in_order(self):
        self.assertTrue(format_errors(end_date="2016-02-30"))
        self.assertTrue(format_errors(end_date="30/12/2016"))
        self.assertTrue(format_errors(start_date="2016-12-31"))       # after the end date
        self.assertEqual(format_errors(start_date=None), [])

    def test_evidence_is_a_non_empty_list_of_quotes(self):
        self.assertTrue(format_errors(evidence=[]))
        self.assertTrue(format_errors(evidence=GOOD_QUOTE))
        self.assertTrue(format_errors(evidence=[" "]))

    def test_useful_must_agree_with_items_both_ways(self):
        self.assertTrue(find_format_errors(reply(useful=False)))
        self.assertTrue(find_format_errors(reply([], useful=True)))


class EvidenceTest(unittest.TestCase):
    """Layer 2 (rule a): evidence is copied exactly from the article."""

    def test_exact_quote_passes_and_line_breaks_are_ignored(self):
        self.assertIsNone(find_quote_problem(GOOD_QUOTE, ARTICLE))
        self.assertIsNone(find_quote_problem("Friday. The county total", ARTICLE))

    def test_invented_joined_or_shortened_quotes_fail(self):
        for quote in ("Officials confirmed 20 new flu cases.",
                      "Officials confirmed 12 new flu cases. The county total is now 85.",
                      "Officials confirmed ... on Friday."):
            self.assertEqual(find_quote_problem(quote, ARTICLE), QUOTE_NOT_FOUND)
        self.assertEqual(find_quote_problem("  ", ARTICLE), QUOTE_EMPTY)

    def test_straight_quotes_for_curly_quotes_are_flagged_separately(self):
        self.assertEqual(find_quote_problem('"We expect more," said Dr. Lee.', ARTICLE), QUOTE_TYPOGRAPHY_ONLY)

    def test_every_bad_quote_of_every_item_is_named(self):
        parsed = reply([count_item(evidence=[GOOD_QUOTE, "Invented."]), trend_item(evidence=["Also invented."])])
        errors = find_evidence_errors(parsed, ARTICLE)
        self.assertEqual(len(errors), 2)
        self.assertTrue(errors[0].startswith("(a) item 1"))


class RuleTest(unittest.TestCase):
    """Layer 3: rules reported in the results."""

    def test_clean_replies_have_no_violations(self):
        self.assertEqual(violations(reply()), [])
        self.assertEqual(violations(reply([])), [])

    def test_bad_evidence_is_reported_as_rule_a(self):
        self.assertTrue(any(v.startswith("(a)") for v in violations(reply([count_item(evidence=["Invented."])]))))

    def test_end_date_after_scan_date_or_older_than_30_days_is_rule_i(self):
        self.assertTrue(any(v.startswith("(i)") for v in violations(reply([count_item(end_date="2016-12-31",
                                                                                     start_date=None)]))))
        self.assertTrue(any(v.startswith("(i)") for v in violations(reply([count_item(end_date="2016-11-01",
                                                                                     start_date=None)]))))

    def test_evidence_out_of_article_order_is_rule_j(self):
        late = "The county total is now 85."
        in_order = count_item(evidence=[GOOD_QUOTE, late, "said Dr. Lee."])
        self.assertEqual([v for v in violations(reply([in_order])) if v.startswith("(j)")], [])
        reordered = count_item(evidence=[GOOD_QUOTE, "said Dr. Lee.", late])
        self.assertTrue(any(v.startswith("(j)") for v in violations(reply([reordered]))))

    def test_reasoning_steps_rule_k(self):
        self.assertTrue(any(v.startswith("(k)") for v in violations(reply(reasoning=["The article says..."]))))
        self.assertTrue(any(v.startswith("(k)") for v in violations(reply(reasoning=["Step 0 (summary): x",
                                                                                     "Step 1: y"]))))

    def test_counts_that_differ_in_period_strain_or_status_are_not_violations(self):
        total = count_item(number=85, count_type="cumulative_region", start_date="2016-12-01")
        self.assertEqual(violations(reply([count_item(), total])), [])                        # G4 table rows
        self.assertEqual(violations(reply([count_item(strain="influenza A"),
                                           count_item(number=1, strain="influenza B")])), [])
        self.assertEqual(violations(reply([count_item(), count_item(number=30, status="suspected")])), [])

    def test_counts_of_the_same_people_are_rule_g4(self):
        # Same kind, place, period, strain and status: a count and its part, or one count twice.
        part = count_item(number=2, count_type="cumulative_subset")
        self.assertTrue(any(v.startswith("(G4)") for v in violations(reply([count_item(), part]))))
        self.assertTrue(any(v.startswith("(G4)") for v in violations(reply([count_item(), count_item()]))))

    def test_contradicting_trend_words_are_rule_g5(self):
        rising, falling = trend_item(), trend_item(words="falling")
        self.assertTrue(any(v.startswith("(G5)") for v in violations(reply([rising, falling]))))
        self.assertEqual(violations(reply([rising, trend_item(words="falling", strain="influenza B")])), [])
        self.assertEqual(violations(reply([rising, trend_item()])), [])   # the same word twice is not G5


if __name__ == "__main__":
    unittest.main()
