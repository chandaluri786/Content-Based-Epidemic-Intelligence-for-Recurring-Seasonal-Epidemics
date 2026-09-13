"""ISO-8601 week <-> date conversions.

Every module that aggregates by "epi-week" (ground_truth, gdelt, join, detection)
must go through here rather than doing manual date/week arithmetic, since ISO
week 52/53 rolling into the next calendar year is easy to get silently wrong.
"""

from datetime import date, timedelta


def iso_week_of(d: date) -> tuple[int, int]:
    """Return (iso_year, iso_week) for a date, per ISO-8601."""
    iso_year, iso_week, _ = d.isocalendar()
    return iso_year, iso_week


def date_from_iso_week(iso_year: int, iso_week: int, weekday: int = 1) -> date:
    """Return the date for a given ISO (year, week, weekday). weekday=1 is Monday."""
    if not 1 <= iso_week <= 53:
        raise ValueError(f"iso_week must be in 1..53, got {iso_week}")
    if not 1 <= weekday <= 7:
        raise ValueError(f"weekday must be in 1..7, got {weekday}")

    return date.fromisocalendar(iso_year, iso_week, weekday)


def shift_weeks(d: date, n_weeks: int) -> date:
    """Return the date n_weeks after d (negative n_weeks shifts backward)."""
    return d + timedelta(weeks=n_weeks)


def iter_weekly_dates(start: date, end: date) -> list[date]:
    """Return dates from start to end stepping 7 days, inclusive of start and
    of end only if it falls exactly on a step. Empty if end < start."""
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current = shift_weeks(current, 1)
    return dates
