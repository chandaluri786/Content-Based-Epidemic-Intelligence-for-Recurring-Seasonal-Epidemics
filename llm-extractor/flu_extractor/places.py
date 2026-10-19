"""Check that a city, state or country value is a real place (the place check, rule d).

We ask OpenStreetMap's free geocoder, Nominatim, whether a place of that kind exists. There
is no list of names to keep up to date. Every answer is saved in a cache file, so each name
is looked up only once and later runs give the same answers without internet.
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

PLACE_FIELDS = ("city", "state", "country")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy: identify the application, and send at most 1 request per second.
USER_AGENT = "flu-extractor-capstone/0.1 (place validity check)"
MIN_SECONDS_BETWEEN_REQUESTS = 1.1
REQUEST_TIMEOUT_SECONDS = 20
LOOKUP_ATTEMPTS = 3
SECONDS_BEFORE_RETRY = 5

# A lookup answers {"found": True/False, "top_match": "<best match, as text>"}, or None when
# the service could not be reached.
LookupResult = dict | None
Lookup = Callable[[str, str], LookupResult]


class NominatimLookup:
    """Asks Nominatim whether `value` is a place of the kind `field` ('city', 'state' or 'country')."""

    def __init__(self) -> None:
        self._last_request_at = 0.0

    def __call__(self, field: str, value: str) -> LookupResult:
        # A "structured" query (city=..., state=..., country=...) only matches places of that kind,
        # so "India" is not found as a state and "California" is not found as a country.
        url = NOMINATIM_URL + "?" + urllib.parse.urlencode(
            {field: value, "format": "jsonv2", "limit": 1}
        )
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
            top_match = hits[0].get("display_name", "") if hits else ""
            return {"found": bool(hits), "top_match": top_match}
        return None  # unreachable or overloaded: the caller must not guess an answer

    def _wait_for_turn(self) -> None:
        """Sleep until at least MIN_SECONDS_BETWEEN_REQUESTS have passed since the last request."""
        wait = self._last_request_at + MIN_SECONDS_BETWEEN_REQUESTS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()


class PlaceChecker:
    """Answers 'is this value a real city / state / country?', remembering every answer.

    cache_path: JSON file holding earlier answers; None keeps them in memory only.
    lookup:     function that asks the geocoder; replaced by a fake in the tests.
    offline:    if True, never ask the geocoder; names that are not in the cache stay unchecked.
    """

    def __init__(self, cache_path: Path | None = None, lookup: Lookup | None = None,
                 offline: bool = False) -> None:
        self._cache_path = cache_path
        self._lookup = lookup or NominatimLookup()
        self._offline = offline
        self._cache: dict[str, dict] = {}
        if cache_path is not None and cache_path.exists():
            self._cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def is_known(self, field: str, value: str) -> bool | None:
        """True if a place of that kind exists, False if not, None if it could not be checked."""
        if field not in PLACE_FIELDS:
            raise ValueError(f"field must be one of {PLACE_FIELDS}, not {field!r}")
        squashed = " ".join(value.split())
        if not squashed:
            return False  # a blank value is not a place

        key = f"{field}: {squashed.casefold()}"
        if key not in self._cache:
            if self._offline:
                return None
            result = self._lookup(field, squashed)
            if result is None:
                return None  # not cached, so the next run tries again
            self._cache[key] = {**result, "checked_on": date.today().isoformat()}
            self._save()
        return self._cache[key]["found"]

    def _save(self) -> None:
        """Write the cache after every new answer, so an interrupted run loses nothing."""
        if self._cache_path is None:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._cache, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                             encoding="utf-8")
        os.replace(temporary, self._cache_path)  # replace in one step: never a half-written file
