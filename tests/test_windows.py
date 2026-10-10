"""
Unit tests for Stage 2 window post-processing (pipeline/windows.py):
same-country overlap removal, pre-GDELT windows, and the persisted
windows file. Pure logic, no network. Run with: pytest
"""

import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import CountrySeasonWindow
from pipeline.windows import drop_before_gdelt, drop_overlapping, load_windows, save_windows, season_id


def _window(country: str, season: int, start: date, end: date) -> CountrySeasonWindow:
    return CountrySeasonWindow(country_iso3=country, season_year=season, onset_date=start,
                               window_start=start, window_end=end)


def test_drop_overlapping_drops_the_later_window_in_the_same_country():
    first = _window("USA", 2023, date(2023, 9, 25), date(2023, 12, 18))
    later = _window("USA", 2024, date(2023, 10, 23), date(2024, 1, 15))
    assert drop_overlapping([later, first]) == [first]


def test_drop_overlapping_treats_a_shared_day_as_overlap():
    first = _window("USA", 2023, date(2023, 1, 1), date(2023, 3, 1))
    touching = _window("USA", 2024, date(2023, 3, 1), date(2023, 5, 1))
    assert drop_overlapping([first, touching]) == [first]


def test_drop_overlapping_keeps_cross_country_overlap():
    usa = _window("USA", 2023, date(2023, 9, 25), date(2023, 12, 18))
    idn = _window("IDN", 2023, date(2023, 10, 1), date(2023, 12, 31))
    assert drop_overlapping([usa, idn]) == [usa, idn]


def test_drop_overlapping_compares_against_the_last_kept_window():
    """A third window that overlaps only a dropped window is kept."""
    a = _window("KEN", 2016, date(2016, 1, 1), date(2016, 3, 1))
    b = _window("KEN", 2017, date(2016, 2, 1), date(2016, 5, 1))   # overlaps a -> dropped
    c = _window("KEN", 2018, date(2016, 4, 1), date(2016, 6, 1))   # overlaps only b -> kept
    assert drop_overlapping([a, b, c]) == [a, c]


def test_drop_overlapping_does_not_mutate_its_input():
    windows = [_window("USA", 2024, date(2023, 10, 23), date(2024, 1, 15)),
               _window("USA", 2023, date(2023, 9, 25), date(2023, 12, 18))]
    snapshot = list(windows)
    drop_overlapping(windows)
    assert windows == snapshot


def test_drop_before_gdelt_removes_windows_starting_before_the_feed():
    early = _window("USA", 2014, date(2014, 10, 20), date(2015, 1, 12))
    ok = _window("AUS", 2015, date(2015, 3, 1), date(2015, 6, 1))
    assert drop_before_gdelt([early, ok], earliest=date(2015, 2, 19)) == [ok]


def test_season_id_format():
    assert season_id(_window("USA", 2023, date(2023, 9, 25), date(2023, 12, 18))) == "USA-2023"


def test_windows_round_trip_through_disk():
    windows = [_window("USA", 2023, date(2023, 9, 25), date(2023, 12, 18))]
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "nested" / "season_windows.json"
        save_windows(windows, path)
        assert load_windows(path) == windows
