"""Step 2: turn the article and item tables into 12 weekly counts per country-season.

Signals (all count articles, not items, so one article with many items counts once per week):
- freq_articles: pool articles that count for the season (date in window, country mentioned). The baseline.
- content_articles: articles with any item for the season.
- seasonal_articles: articles with a seasonal human flu item (no bird flu or variant strain).
- activity_articles: seasonal items that report flu going on: a count (cases, deaths, hospitalized) or a
  trend that is present, moderate, high or rising.
- rising_articles: seasonal trend items that are rising or high.
- avian_articles: articles with a bird flu or variant item. A check, not a candidate.

Weeks are ISO weeks (Monday to Sunday), taken from each article's scan date alone. A season's weeks are the
ISO weeks that lie wholly inside its window. Only afterwards is each week labelled -10 .. +1 by its position
against the ISO week that holds the FluNet onset. A day outside those weeks (the window's last day, a Monday)
is dropped, not added to week +1.

The candidates are chosen on calibration seasons only (step 4). Nothing here looks at FluNet beyond the
onset date that names the weeks.
"""

from datetime import date, timedelta

import signal_config as cfg
from tables import Window

CONTENT_SIGNALS = ("content_articles", "seasonal_articles", "activity_articles", "rising_articles", "avian_articles")
SIGNALS = ("freq_articles",) + CONTENT_SIGNALS


def iso_week(day: date) -> str:
    """The ISO week of a date, e.g. "2016-W05". Uses the date alone."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def season_weeks(window: Window) -> dict[str, int]:
    """{ISO week: label} for the ISO weeks wholly inside the window, labelled by position against the ISO week
    of the onset (0). A season must have exactly the weeks FIRST_WEEK .. LAST_WEEK."""
    monday = window.window_start + timedelta(days=(7 - window.window_start.weekday()) % 7)
    weeks = []
    while monday + timedelta(days=6) <= window.window_end:
        weeks.append(iso_week(monday))
        monday += timedelta(weeks=1)
    onset_week = iso_week(window.onset_date)
    if onset_week not in weeks:
        raise ValueError(f"{window.season_id}: onset week {onset_week} is not a whole week inside the window")
    labels = {week: position - weeks.index(onset_week) for position, week in enumerate(weeks)}
    if sorted(labels.values()) != list(range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1)):
        raise ValueError(f"{window.season_id}: whole weeks {weeks} do not run {cfg.FIRST_WEEK} .. {cfg.LAST_WEEK}")
    return labels


def week_label(scan_date: date, window: Window, labels: dict[str, int]) -> int | None:
    """The label of the date's ISO week, or None for a day of a week only partly inside the window."""
    if not window.window_start <= scan_date <= window.window_end:
        raise ValueError(f"{scan_date} is outside the window of {window.season_id}")
    return labels.get(iso_week(scan_date))


def is_seasonal(strain: str | None) -> bool:
    """False for bird flu and other animal-origin strains and for swine variant viruses."""
    name = (strain or "").strip().lower()
    if not name:
        return True
    return not (name.startswith(cfg.NON_SEASONAL_STRAIN_PREFIXES) or name.endswith(cfg.NON_SEASONAL_STRAIN_SUFFIX))


def item_signals(item: dict) -> set[str]:
    """The content signals one item counts toward."""
    if not is_seasonal(item.get("strain")):
        return {"content_articles", "avian_articles"}
    signals = {"content_articles", "seasonal_articles"}
    kind, words = item.get("kind"), item.get("words")
    if kind in cfg.COUNT_KINDS or (kind == "trend" and words in cfg.ACTIVITY_WORDS):
        signals.add("activity_articles")
    if kind == "trend" and words in cfg.RISING_WORDS:
        signals.add("rising_articles")
    return signals


def split_of(season_year: int) -> str:
    return cfg.SPLIT_HELD_OUT if season_year >= cfg.HELD_OUT_FROM_YEAR else cfg.SPLIT_CALIBRATION


def empty_series(windows: dict[str, list[Window]]) -> dict[tuple[str, int], dict[str, int]]:
    """{(season_id, week): {signal: 0}} for every season and every one of its 12 weeks."""
    return {(window.season_id, week): {signal: 0 for signal in SIGNALS}
            for country_windows in windows.values() for window in country_windows
            for week in range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1)}


def build_weekly(articles: list[dict], items: list[dict],
                 windows: dict[str, list[Window]]) -> tuple[list[dict], dict[str, int]]:
    """(one row per season and week, in season and week order; counts dropped per signal because their day
    lies in an ISO week only partly inside the window)."""
    by_season = {window.season_id: window for country_windows in windows.values() for window in country_windows}
    labels = {season_id: season_weeks(window) for season_id, window in by_season.items()}
    counts = empty_series(windows)
    dropped = {signal: 0 for signal in SIGNALS}

    def add(season_id: str, scan_date: date, signals) -> None:
        week = week_label(scan_date, by_season[season_id], labels[season_id])
        for signal in signals:
            if week is None:
                dropped[signal] += 1
            else:
                counts[(season_id, week)][signal] += 1

    scan_dates = {}
    for article in articles:
        scan_dates[article["record_id"]] = date.fromisoformat(article["scan_date"])
        for season_id in filter(None, article["frequency_seasons"].split(";")):
            add(season_id, scan_dates[article["record_id"]], ("freq_articles",))

    # An article counts once per (season, signal), however many items it has.
    article_signals: dict[tuple[str, str], set[str]] = {}
    for item in items:
        key = (item["record_id"], item["season_id"])
        article_signals[key] = article_signals.get(key, set()) | item_signals(item)
    for (record_id, season_id), signals in article_signals.items():
        add(season_id, scan_dates[record_id], sorted(signals))

    iso_by_label = {season_id: {label: week for week, label in season.items()} for season_id, season in labels.items()}
    rows = []
    for (season_id, week), values in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        window = by_season[season_id]
        season_year = int(season_id.split("-")[1])
        rows.append({"season_id": season_id, "country": window.country, "season_year": season_year,
                     "split": split_of(season_year), "headline": window.country in cfg.HEADLINE_COUNTRIES,
                     "onset_date": window.onset_date.isoformat(), "week": week,
                     "iso_week": iso_by_label[season_id][week], **values})
    return rows, dropped
