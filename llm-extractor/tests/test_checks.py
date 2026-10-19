"""Tests for the evidence check (rule a) and the other rule checks.

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

# Here every place counts as real, so the evidence tests are not affected by rule (d).
EVERY_PLACE_IS_REAL = PlaceChecker(lookup=lambda field, value: {"found": True, "top_match": value})


def reply(evidence, useful=True):
    """A minimal valid model reply with one item carrying the given evidence."""
    item = {
        "kind": "cases", "strain": None, "number": 12, "status": "confirmed", "total_or_new": "new",
        "city": "Springfield", "state": None, "country": None, "start_date": None, "end_date": None,
        "words": None, "evidence": evidence,
    }
    return {"useful": useful, "borderline": False, "reason": "x", "items": [item]}


class QuoteCheckTest(unittest.TestCase):
    def test_exact_quote_passes(self):
        self.assertIsNone(find_quote_problem("Officials confirmed 12 new flu cases on Friday.", ARTICLE))

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


class RuleViolationTest(unittest.TestCase):
    GOOD_QUOTE = "Officials confirmed 12 new flu cases on Friday."

    def violations(self, parsed):
        return find_rule_violations(parsed, ARTICLE, EVERY_PLACE_IS_REAL)

    def test_clean_reply_has_no_violations(self):
        parsed = reply([self.GOOD_QUOTE])
        self.assertEqual(find_shape_errors(parsed), [])
        self.assertEqual(self.violations(parsed), [])

    def test_invented_evidence_is_reported_as_rule_a(self):
        violations = self.violations(reply(["Officials confirmed 99 cases."]))
        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].startswith("(a)") and QUOTE_NOT_FOUND in violations[0])

    def test_one_bad_quote_among_good_ones_is_still_reported(self):
        self.assertEqual(len(self.violations(reply([self.GOOD_QUOTE, "Made up sentence."]))), 1)

    def test_findings_are_not_required(self):
        parsed = reply([self.GOOD_QUOTE])
        self.assertNotIn("findings", parsed)
        self.assertEqual(find_shape_errors(parsed), [])

    def test_findings_left_over_from_prompt_v2_0_are_ignored(self):
        # Prompt v2.0 still asks for findings; an invented sentence there is neither an error nor a violation.
        parsed = {**reply([self.GOOD_QUOTE]), "findings": [{"country": "USA", "finding": "Made up."}]}
        self.assertEqual(find_shape_errors(parsed), [])
        self.assertEqual(self.violations(parsed), [])


if __name__ == "__main__":
    unittest.main()
