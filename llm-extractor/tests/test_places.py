"""Tests for place names (prompt 5.1) and the place check (rule d): whole-chain lookups, the agreed
form of every place, the saved answers and offline mode. No internet is used: a fake geocoder answers.

Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import json
import tempfile
import unittest
from pathlib import Path

from flu_extractor.checks import PLACE_NOT_FOUND, PLACE_UNCHECKED, find_place_problems
from flu_extractor.places import PlaceChecker, chain_key

# What the fake geocoder knows: chain key (as written) -> English name in OpenStreetMap.
REAL_PLACES = {
    "country: usa": "United States", "country: united states": "United States",
    "country: india": "India", "country: australia": "Australia",
    "state: illinois | country: usa": "Illinois", "state: illinois | country: united states": "Illinois",
    "city: springfield | state: illinois | country: usa": "Springfield",
    "city: springfield | state: illinois | country: united states": "Springfield",
    "state: victoria | country: australia": "Victoria",
    "state: nsw | country: australia": "New South Wales",
    "state: karnataka | country: india": "Karnataka",
    "city: bangalore | state: karnataka | country: india": "Bengaluru",
    "city: bengaluru | state: karnataka | country: india": "Bengaluru",
    "state: delhi | country: india": "Delhi",
    "city: delhi | state: delhi | country: india": "Delhi",
    "country: bulgaria": "Bulgaria", "state: dobrich | country: bulgaria": "Dobrich",
    "country: austria": "Austria", "state: vienna | country: austria": "Vienna",
}


class FakeGeocoder:
    """Stands in for Nominatim and counts how often it is asked."""

    def __init__(self, unreachable=False):
        self.calls = []
        self.unreachable = unreachable

    def __call__(self, place):
        self.calls.append(chain_key(place))
        if self.unreachable:
            return None
        name = REAL_PLACES.get(chain_key(place))
        return {"found": name is not None, "top_match": name or "", "english_name": name or "", "osm_id": name or "",
                "addresstype": "city" if name else ""}


def item(city=None, state=None, country="United States"):
    return {"kind": "cases", "number": 1, "count_type": "new", "status": "confirmed", "strain": None,
            "city": city, "state": state, "country": country, "start_date": None, "end_date": "2016-12-30",
            "words": None, "evidence": ["x"]}


class PlaceCheckerTest(unittest.TestCase):
    def test_the_whole_chain_is_asked_together(self):
        checker = PlaceChecker(lookup=FakeGeocoder())
        self.assertTrue(checker.check({"state": "Victoria", "country": "Australia"})["found"])
        self.assertFalse(checker.check({"state": "Victoria", "country": "India"})["found"])   # wrong country
        self.assertFalse(checker.check({"state": "India", "country": "USA"})["found"])       # a country, not a state

    def test_no_country_is_never_a_place_and_is_not_looked_up(self):
        geocoder = FakeGeocoder()
        self.assertFalse(PlaceChecker(lookup=geocoder).check({"state": "Illinois"})["found"])
        self.assertEqual(geocoder.calls, [])

    def test_each_chain_is_looked_up_once_ignoring_case_and_spacing(self):
        geocoder = FakeGeocoder()
        checker = PlaceChecker(lookup=geocoder)
        for spelling in ("Illinois", "illinois", " Illinois "):
            self.assertTrue(checker.check({"state": spelling, "country": "USA"})["found"])
        self.assertEqual(geocoder.calls, ["state: illinois | country: usa"])

    def test_unreachable_service_gives_no_answer_and_nothing_is_remembered(self):
        geocoder = FakeGeocoder(unreachable=True)
        checker = PlaceChecker(lookup=geocoder)
        self.assertIsNone(checker.check({"country": "USA"}))
        self.assertIsNone(checker.check({"country": "USA"}))
        self.assertEqual(len(geocoder.calls), 2)   # asked again, because nothing was saved

    def test_offline_nothing_is_asked_and_nothing_is_checked(self):
        geocoder = FakeGeocoder()
        self.assertIsNone(PlaceChecker(lookup=geocoder, offline=True).check({"country": "India"}))
        self.assertEqual(geocoder.calls, [])

    def test_answers_are_saved_and_reused_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "place_lookups.json"
            PlaceChecker(cache, lookup=FakeGeocoder()).check({"country": "India"})
            saved = json.loads(cache.read_text(encoding="utf-8"))
            self.assertTrue(saved["country: india"]["found"])
            self.assertEqual(saved["country: india"]["language"], "en")
            geocoder = FakeGeocoder()
            offline = PlaceChecker(cache, lookup=geocoder, offline=True)
            self.assertTrue(offline.check({"country": "India"})["found"])
            self.assertIsNone(offline.check({"country": "USA"}))   # never asked before: unchecked
            self.assertEqual(geocoder.calls, [])

    def test_a_saved_answer_is_not_asked_again(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "place_lookups.json"
            PlaceChecker(cache, lookup=FakeGeocoder()).check({"country": "India"})
            geocoder = FakeGeocoder()
            self.assertTrue(PlaceChecker(cache, lookup=geocoder).check({"country": "India"})["found"])
            self.assertEqual(geocoder.calls, [])

    def test_an_old_answer_is_asked_again_online_and_not_trusted_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "place_lookups.json"
            cache.write_text(json.dumps({"country: usa": {"found": True, "top_match": "United States",
                                                          "english_name": "United States"}}), encoding="utf-8")
            self.assertIsNone(PlaceChecker(cache, offline=True).check({"country": "USA"}))
            geocoder = FakeGeocoder()
            self.assertEqual(PlaceChecker(cache, lookup=geocoder).check({"country": "USA"})["english_name"],
                             "United States")
            self.assertEqual(geocoder.calls, ["country: usa"])
            self.assertIn("addresstype", json.loads(cache.read_text(encoding="utf-8"))["country: usa"])


class AgreedNameTest(unittest.TestCase):
    """5.1: every place in one agreed form, its English name in OpenStreetMap, for any place."""

    def test_different_spellings_of_one_place_get_one_agreed_form(self):
        checker = PlaceChecker(lookup=FakeGeocoder())
        one = checker.agreed_names({"city": "Bangalore", "state": "Karnataka", "country": "India"})
        two = checker.agreed_names({"city": "Bengaluru", "state": "Karnataka", "country": "India"})
        self.assertEqual((one["city"], one["state"], one["country"]), ("Bengaluru", "Karnataka", "India"))
        self.assertEqual((one["city"], one["state"], one["country"]), (two["city"], two["state"], two["country"]))
        self.assertEqual(checker.agreed_names({"country": "USA"})["country"], "United States")
        self.assertEqual(checker.agreed_names({"state": "NSW", "country": "Australia"})["state"], "New South Wales")

    def test_a_level_not_found_keeps_its_written_value_and_stops_the_levels_below(self):
        agreed = PlaceChecker(lookup=FakeGeocoder()).agreed_names(
            {"city": "Springfield", "state": "Victoria", "country": "USA"})
        self.assertEqual((agreed["country"], agreed["state"], agreed["city"]), ("United States", "Victoria", "Springfield"))
        self.assertEqual(agreed["resolved"], {"country": True, "state": False, "city": None})

    def test_offline_and_not_saved_keeps_the_written_values(self):
        agreed = PlaceChecker(lookup=FakeGeocoder(), offline=True).agreed_names({"country": "USA"})
        self.assertEqual((agreed["country"], agreed["resolved"]["country"]), ("USA", None))

    def test_items_are_copied_with_agreed_names_and_scored_as_the_same_place(self):
        from flu_extractor.evaluation import score_items
        checker = PlaceChecker(lookup=FakeGeocoder())
        gold = item(city="Springfield", state="Illinois", country="USA")
        model = item(city="Springfield", state="Illinois", country="United States")
        self.assertEqual(checker.with_agreed_names(gold)["country"], "United States")
        self.assertEqual(gold["country"], "USA")   # the original item is not changed
        outcome = score_items([checker.with_agreed_names(gold)], [checker.with_agreed_names(model)])
        self.assertEqual((outcome.tp, outcome.exact_items), (1, 1))

    def test_a_level_word_osm_does_not_use_is_dropped(self):
        agreed = PlaceChecker(lookup=FakeGeocoder()).agreed_names({"state": "Dobrich Province", "country": "Bulgaria"})
        self.assertEqual((agreed["state"], agreed["resolved"]["state"]), ("Dobrich", True))

    def test_a_city_that_is_its_own_state_takes_the_states_name(self):
        # Vienna the city is not found as a settlement inside Vienna the state: the state's entry is the city.
        agreed = PlaceChecker(lookup=FakeGeocoder()).agreed_names({"city": "Vienna", "state": "Vienna", "country": "Austria"})
        self.assertEqual((agreed["city"], agreed["resolved"]["city"]), ("Vienna", True))

    def test_only_the_right_kind_of_place_answers_a_level(self):
        from flu_extractor.places import _acceptable
        building = {"category": "landuse", "addresstype": "commercial"}
        quarter = {"category": "place", "addresstype": "quarter"}
        city = {"category": "place", "addresstype": "city"}
        self.assertFalse(_acceptable("city", building))
        self.assertFalse(_acceptable("city", quarter))
        self.assertTrue(_acceptable("city", city))
        self.assertTrue(_acceptable("state", {"category": "boundary", "addresstype": "state"}))
        self.assertFalse(_acceptable("state", quarter))
        self.assertFalse(_acceptable("country", city))

    def test_a_town_recorded_as_an_administrative_suburb_answers_the_city_level(self):
        from flu_extractor.places import _best_hit
        australian_town = {"category": "boundary", "type": "administrative", "addresstype": "suburb",
                           "name": "Mornington"}
        neighbourhood = {"category": "place", "type": "suburb", "addresstype": "suburb", "name": "Old Kyiv"}
        settlement = {"category": "place", "type": "city", "addresstype": "city", "name": "Kyiv"}
        self.assertEqual(_best_hit("city", [australian_town])["name"], "Mornington")
        self.assertIsNone(_best_hit("city", [neighbourhood]))                        # a loose point is never a city
        self.assertEqual(_best_hit("city", [australian_town, settlement])["name"], "Kyiv")  # a settlement first
        self.assertIsNone(_best_hit("country", [australian_town]))


class PlaceProblemTest(unittest.TestCase):
    def problems(self, **place):
        return find_place_problems(item(**place), PlaceChecker(lookup=FakeGeocoder()))

    def test_real_chains_in_their_agreed_form_pass(self):
        self.assertEqual(self.problems(city="Springfield", state="Illinois", country="United States"), [])
        self.assertEqual(self.problems(city="Delhi", state="Delhi", country="India"), [])

    def test_a_state_in_the_wrong_country_is_not_found(self):
        problems = self.problems(state="Victoria", country="India")
        self.assertEqual(len(problems), 1)
        self.assertIn(PLACE_NOT_FOUND, problems[0])

    def test_a_missing_level_stops_the_lower_levels(self):
        self.assertEqual(len(self.problems(city="Springfield", state="Victoria", country="India")), 1)

    def test_any_value_not_in_its_agreed_form_is_reported_with_the_agreed_form(self):
        self.assertIn("write 'United States'", self.problems(country="USA")[0])
        self.assertIn("write 'New South Wales'", self.problems(state="NSW", country="Australia")[0])
        self.assertIn("write 'Bengaluru'", self.problems(city="Bangalore", state="Karnataka", country="India")[0])

    def test_unreachable_service_is_reported_not_guessed(self):
        problems = find_place_problems(item(country="USA"), PlaceChecker(lookup=FakeGeocoder(unreachable=True)))
        self.assertEqual(len(problems), 1)
        self.assertIn(PLACE_UNCHECKED, problems[0])

if __name__ == "__main__":
    unittest.main()
