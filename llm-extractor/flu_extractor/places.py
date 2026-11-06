"""Place names: is a place real, and what is its agreed name? Asked of OpenStreetMap's free
geocoder, Nominatim (prompt 5.1 and the place check, rule d).

Prompt 5.1: every city, state and country has one agreed form, its English name in OpenStreetMap.
agreed_names() turns any city / state / country chain into that form (Bangalore -> Bengaluru,
USA -> United States, Dobrich Province -> not found as written), so values from gold and from the
model are the same for the same place and can be compared and combined.

There is no list of allowed names: any place on Earth can be checked. The question is asked for the
whole chain an item gives, so the levels are checked together:

    {"country": "Australia"}                                   is Australia a country?
    {"state": "Victoria", "country": "Australia"}               is Victoria a state of Australia?
    {"city": "Pune", "state": "Maharashtra", "country": "India"}  is Pune a city in Maharashtra, India?

"Victoria, Canada" or "Pune, Gujarat" are therefore not found. Each answer, with the geocoder's English
name for the place and its OpenStreetMap id, is kept in memory for the rest of the run, so each chain
is asked only once. Answers are saved in data/place_lookups.json (config.PLACE_CACHE_PATH), so later
runs repeat exactly and need no internet for places already seen. The file is not a list of allowed
places: a chain that is not in it is asked online and added. An answer saved by an older version
(without the kind of place) or in another language is asked again.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable

from flu_extractor import config

PLACE_FIELDS = ("city", "state", "country")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy: identify the application, and send at most 1 request per second.
USER_AGENT = "flu-extractor-capstone/0.2 (place validity check)"
MIN_SECONDS_BETWEEN_REQUESTS = 1.1
REQUEST_TIMEOUT_SECONDS = 20
LOOKUP_ATTEMPTS = 3
SECONDS_BEFORE_RETRY = 5

# What kind of OpenStreetMap object may answer each level. A city must be a settlement (never a
# building, an industrial site or a district inside a city: "Vienna" once matched "Vienna
# International Centre", "Kyiv" matched "Old Kyiv"); a state must be a region-level unit, not
# something inside a city; a country must be a country.
CITY_TYPES = {"city", "town", "village", "municipality", "hamlet"}
COUNTRY_TYPES = {"country"}
TOO_SMALL_FOR_A_STATE = {"quarter", "suburb", "neighbourhood", "city_block", "borough", "city_district",
                         "village", "hamlet", "isolated_dwelling", "farm", "road", "building", "house"}
# Some countries' OpenStreetMap convention records towns as administrative areas of the "suburb" kind
# (Australia: Mornington, Victoria is boundary=administrative, addresstype "suburb"). Such an area
# answers the city level only when no settlement does. A loose neighbourhood point (place=suburb,
# "Old Kyiv"-like) is never a city.
TOWN_AS_ADMINISTRATIVE_AREA = {"suburb"}
# Level words that may be written but are not part of OpenStreetMap's name ("Dobrich Province" is
# "Dobrich"). When a name is not found, it is asked again without such a word (agreed_names).
LEVEL_WORDS = ("Province", "District", "Oblast", "County", "Region", "Governorate", "Prefecture", "Division",
               "State", "Territory", "Municipality", "Emirate")


def _acceptable(level: str, hit: dict) -> bool:
    """Is this OpenStreetMap object the right kind of place for the level asked about?"""
    if hit.get("category") not in ("place", "boundary"):
        return False
    kind = hit.get("addresstype", "")
    if level == "city":
        return kind in CITY_TYPES
    if level == "country":
        return kind in COUNTRY_TYPES
    return kind not in TOO_SMALL_FOR_A_STATE


def _is_town_as_administrative_area(hit: dict) -> bool:
    """A town recorded as an administrative area of the suburb kind (the Australian convention)."""
    return (hit.get("category") == "boundary" and hit.get("type") == "administrative"
            and hit.get("addresstype", "") in TOWN_AS_ADMINISTRATIVE_AREA)


def _best_hit(level: str, hits: list[dict]) -> dict | None:
    """The first hit of the right kind for the level; for a city, a town recorded as an administrative
    area is taken only if no settlement is among the hits."""
    hit = next((h for h in hits if _acceptable(level, h)), None)
    if hit is None and level == "city":
        hit = next((h for h in hits if _is_town_as_administrative_area(h)), None)
    return hit


# A lookup answers {"found": bool, "top_match": text, "english_name": text, "osm_id": text,
# "addresstype": text}, or None
# when the service could not be reached. "english_name" is the place's name in PLACE_NAME_LANGUAGE
# (config.py), or its main name when OpenStreetMap has no name in that language.
LookupResult = dict | None
Lookup = Callable[[dict], LookupResult]


def chain_key(place: dict) -> str:
    """The saved key of a place chain, e.g. 'city: pune | state: maharashtra | country: india'."""
    return " | ".join(f"{level}: {' '.join(place[level].split()).casefold()}"
                      for level in PLACE_FIELDS if place.get(level))


class NominatimLookup:
    """Asks Nominatim whether the chain {city?, state?, country} names a real place."""

    def __init__(self) -> None:
        self._last_request_at = 0.0

    def __call__(self, place: dict) -> LookupResult:
        # A "structured" query matches only places of the given kinds inside each other, so
        # "India" is not found as a state and "Victoria" is not found as a state of Canada.
        query = {level: place[level] for level in PLACE_FIELDS if place.get(level)}
        language = config.PLACE_NAME_LANGUAGE
        level = "city" if place.get("city") else "state" if place.get("state") else "country"
        url = NOMINATIM_URL + "?" + urllib.parse.urlencode(
            {**query, "format": "jsonv2", "limit": 5, "namedetails": 1, "accept-language": language})
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(1, LOOKUP_ATTEMPTS + 1):
            self._wait_for_turn()
            try:
                with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                    hits = json.load(response)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                if attempt < LOOKUP_ATTEMPTS:
                    time.sleep(SECONDS_BEFORE_RETRY)
                continue
            hit = _best_hit(level, hits)  # the best match of the right kind
            if hit is None:
                return {"found": False, "top_match": hits[0].get("display_name", "") if hits else "",
                        "english_name": "", "osm_id": "", "addresstype": ""}
            names = hit.get("namedetails") or {}
            english = names.get(f"name:{language}") or hit.get("name") or ""
            return {"found": True, "top_match": hit.get("display_name", ""), "english_name": english,
                    "osm_id": f"{hit.get('osm_type', '')}/{hit.get('osm_id', '')}",
                    "addresstype": hit.get("addresstype", "")}
        return None  # unreachable or overloaded: the caller must not guess an answer

    def _wait_for_turn(self) -> None:
        """Sleep until at least MIN_SECONDS_BETWEEN_REQUESTS have passed since the last request."""
        wait = self._last_request_at + MIN_SECONDS_BETWEEN_REQUESTS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()


def _fold(name: str) -> str:
    return " ".join(name.split()).casefold()


def _without_level_word(name: str) -> str | None:
    """The name without a trailing level word ("Dobrich Province" -> "Dobrich"), or None if it has none."""
    words = name.split()
    if len(words) > 1 and words[-1].casefold() in {w.casefold() for w in LEVEL_WORDS}:
        return " ".join(words[:-1])
    return None


class PlaceChecker:
    """Answers 'is this place chain real?', remembering every answer.

    cache_path: JSON file of saved answers (config.PLACE_CACHE_PATH in the pipeline); None keeps them
                in memory only.
    lookup:     function that asks the geocoder; replaced by a fake in the tests.
    offline:    if True, never ask the geocoder; chains that are not saved stay unchecked.
    """

    def __init__(self, cache_path: Path | None = None, lookup: Lookup | None = None,
                 offline: bool = False) -> None:
        self._cache_path = cache_path
        self._lookup = lookup or NominatimLookup()
        self._offline = offline
        self._cache: dict[str, dict] = {}
        if cache_path is not None and cache_path.exists():
            self._cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def check(self, place: dict) -> dict | None:
        """The answer for a chain {city?, state?, country}: {"found", "top_match", "english_name"},
        or None if it could not be checked (offline and not saved, or the service is down)."""
        if not place.get("country") or any(not isinstance(place.get(level, ""), (str, type(None)))
                                           for level in PLACE_FIELDS):
            return {"found": False, "top_match": "", "english_name": "", "osm_id": ""}
        key = chain_key(place)
        # An answer saved by an older version (without the kind of place, so possibly a wrong kind) or in
        # another language is asked again; offline it is not trusted.
        saved = self._cache.get(key)
        stale = saved is not None and (
            "addresstype" not in saved or saved.get("language", "en") != config.PLACE_NAME_LANGUAGE)
        if saved is None or stale:
            if self._offline:
                return None
            result = self._lookup({level: place.get(level) for level in PLACE_FIELDS})
            if result is None:
                return None  # not saved, so the next run tries again
            self._cache[key] = {**result, "language": config.PLACE_NAME_LANGUAGE,
                                "checked_on": date.today().isoformat()}
            self._save()
        return self._cache[key]

    def agreed_names(self, place: dict) -> dict:
        """The agreed form (5.1) of a chain {city?, state?, country}, level by level.

        Returns {"city", "state", "country"} with each level found in OpenStreetMap replaced by its
        English name, and "resolved": {level: True (found), False (not found) or None (not checked)}.
        A level that is not found keeps its written value, and the levels below it are not looked up,
        so they keep theirs too.
        """
        agreed = {level: place.get(level) for level in PLACE_FIELDS}
        resolved = {level: None for level in PLACE_FIELDS}
        asked = dict(agreed)   # the names the lower levels are asked with (a level word may be dropped)
        for level, chain in (("country", ("country",)), ("state", ("state", "country")),
                             ("city", ("city", "state", "country"))):
            if not place.get(level):
                continue
            answer = self.check({name: asked.get(name) for name in chain})
            if answer is not None and not answer["found"] and level != "country":
                bare = _without_level_word(place[level])        # "Dobrich Province" -> "Dobrich"
                if bare:
                    retry = self.check({**{name: asked.get(name) for name in chain}, level: bare})
                    if retry is not None and retry["found"]:
                        answer, asked[level] = retry, bare
            if (answer is not None and not answer["found"] and level == "city" and resolved["state"]
                    and _fold(place["city"]) == _fold(place["state"])):
                # A city that is its own first-level unit (Vienna, Kyiv): the state's entry is the city.
                answer = {"found": True, "english_name": agreed["state"]}
            if answer is None:
                break
            resolved[level] = bool(answer["found"])
            if not answer["found"]:
                break
            if answer.get("english_name"):
                agreed[level] = answer["english_name"]
        return {**agreed, "resolved": resolved}

    def with_agreed_names(self, item: dict) -> dict:
        """A copy of an item with its city, state and country in their agreed form (5.1)."""
        if not isinstance(item, dict) or not item.get("country"):
            return item
        agreed = self.agreed_names(item)
        return {**item, **{level: agreed[level] for level in PLACE_FIELDS}}

    def _save(self) -> None:
        """Write the file after every new answer, so an interrupted run loses nothing."""
        if self._cache_path is None:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._cache, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                             encoding="utf-8")
        os.replace(temporary, self._cache_path)  # replace in one step: never a half-written file
