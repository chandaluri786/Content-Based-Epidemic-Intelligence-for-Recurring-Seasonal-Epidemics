"""Tests for the place cache and for rule (d). No internet is used: a fake geocoder answers.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import json
import tempfile
import unittest
from pathlib import Path

from flu_extractor.checks import (
    PLACE_NOT_FOUND,
    PLACE_UNCHECKED,
    find_rule_violations,
    find_shape_errors,
)
from flu_extractor.places import PlaceChecker

ARTICLE = "SPRINGFIELD - Officials confirmed 12 new flu cases on Friday."
GOOD_QUOTE = "Officials confirmed 12 new flu cases on Friday."

# What the fake geocoder knows: {(field, lower-case name)}.
REAL_PLACES = {
    ("city", "springfield"), ("city", "westmead"), ("state", "california"),
    ("state", "delhi"), ("country", "usa"), ("country", "india"),
}


class FakeGeocoder:
    """Stands in for Nominatim and counts how often it is asked."""

    def __init__(self, unreachable=False):
        self.calls = []
        self.unreachable = unreachable

    def __call__(self, field, value):
        self.calls.append((field, value))
        if self.unreachable:
            return None
        found = (field, value.casefold()) in REAL_PLACES
        return {"found": found, "top_match": value if found else ""}


def reply(city=None, state=None, country=None):
    item = {
        "kind": "cases", "strain": None, "number": 12, "status": "confirmed", "total_or_new": "new",
        "city": city, "state": state, "country": country, "start_date": None, "end_date": None,
        "words": None, "evidence": [GOOD_QUOTE],
    }
    return {"useful": True, "borderline": False, "reason": "x", "items": [item], "findings": []}


class PlaceCheckerTest(unittest.TestCase):
    def test_real_and_unreal_places(self):
        checker = PlaceChecker(lookup=FakeGeocoder())
        self.assertTrue(checker.is_known("city", "Westmead"))
        self.assertFalse(checker.is_known("city", "Northern Hemisphere"))

    def test_a_value_is_asked_about_as_its_own_field(self):
        checker = PlaceChecker(lookup=FakeGeocoder())
        self.assertFalse(checker.is_known("state", "India"))      # a country, not a state
        self.assertFalse(checker.is_known("country", "California"))  # a state, not a country

    def test_blank_value_is_not_a_place_and_is_not_looked_up(self):
        geocoder = FakeGeocoder()
        self.assertFalse(PlaceChecker(lookup=geocoder).is_known("city", "   "))
        self.assertEqual(geocoder.calls, [])

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(ValueError):
            PlaceChecker(lookup=FakeGeocoder()).is_known("planet", "Mars")

    def test_each_name_is_looked_up_once_ignoring_case_and_spacing(self):
        geocoder = FakeGeocoder()
        checker = PlaceChecker(lookup=geocoder)
        for spelling in ("Springfield", "springfield", "  SPRINGFIELD "):
            self.assertTrue(checker.is_known("city", spelling))
        self.assertEqual(len(geocoder.calls), 1)

    def test_unreachable_service_gives_no_answer_and_nothing_is_remembered(self):
        geocoder = FakeGeocoder(unreachable=True)
        checker = PlaceChecker(lookup=geocoder)
        self.assertIsNone(checker.is_known("city", "Springfield"))
        self.assertIsNone(checker.is_known("city", "Springfield"))
        self.assertEqual(len(geocoder.calls), 2)  # asked again, because no answer was stored

    def test_answers_are_saved_and_reused_by_a_new_checker(self):
        with tempfile.TemporaryDirectory() as folder:
            cache_file = Path(folder) / "lookups.json"
            PlaceChecker(cache_file, lookup=FakeGeocoder()).is_known("city", "Westmead")
            saved = json.loads(cache_file.read_text(encoding="utf-8"))
            self.assertEqual(list(saved), ["city: westmead"])
            self.assertTrue(saved["city: westmead"]["found"])

            second_geocoder = FakeGeocoder()
            self.assertTrue(PlaceChecker(cache_file, lookup=second_geocoder).is_known("city", "Westmead"))
            self.assertEqual(second_geocoder.calls, [])  # answered from the file

    def test_offline_mode_uses_only_saved_answers(self):
        with tempfile.TemporaryDirectory() as folder:
            cache_file = Path(folder) / "lookups.json"
            PlaceChecker(cache_file, lookup=FakeGeocoder()).is_known("city", "Westmead")
            geocoder = FakeGeocoder()
            offline = PlaceChecker(cache_file, lookup=geocoder, offline=True)
            self.assertTrue(offline.is_known("city", "Westmead"))
            self.assertIsNone(offline.is_known("city", "Springfield"))  # never looked up before
            self.assertEqual(geocoder.calls, [])


class PlaceRuleTest(unittest.TestCase):
    """Rule (d): city, state and country are null or a real place of that kind."""

    def violations(self, parsed, checker=None):
        checker = checker or PlaceChecker(lookup=FakeGeocoder())
        return [v for v in find_rule_violations(parsed, ARTICLE, checker) if v.startswith("(d)")]

    def test_null_places_are_allowed_without_any_lookup(self):
        geocoder = FakeGeocoder()
        self.assertEqual(self.violations(reply(), PlaceChecker(lookup=geocoder)), [])
        self.assertEqual(geocoder.calls, [])

    def test_real_city_state_and_country_pass(self):
        self.assertEqual(self.violations(reply("Springfield", "California", "USA")), [])

    def test_region_in_country_field_fails(self):
        violations = self.violations(reply(country="Southern Hemisphere"))
        self.assertEqual(len(violations), 1)
        self.assertIn(PLACE_NOT_FOUND, violations[0])

    def test_a_value_in_the_wrong_field_fails(self):
        self.assertEqual(len(self.violations(reply(state="India"))), 1)
        self.assertEqual(len(self.violations(reply(country="California"))), 1)

    def test_unreachable_service_is_reported_not_guessed(self):
        checker = PlaceChecker(lookup=FakeGeocoder(unreachable=True))
        violations = self.violations(reply(city="Springfield"), checker)
        self.assertEqual(len(violations), 1)
        self.assertIn(PLACE_UNCHECKED, violations[0])

    def test_place_that_is_not_text_is_a_shape_error(self):
        self.assertTrue(any("city must be text or null" in e for e in find_shape_errors(reply(city=5))))


if __name__ == "__main__":
    unittest.main()
