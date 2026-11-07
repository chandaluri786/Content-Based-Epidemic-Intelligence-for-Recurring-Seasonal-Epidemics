"""Step 2: turn the article and item tables into 12 weekly counts per country-season.

Signals (all count articles, not items, so one article with many items counts once per week):
- freq_articles: pool articles that count for the season (date in window, country mentioned). The baseline.
- content_articles: articles with any item for the season.
- seasonal_articles: articles with a seasonal human flu item (no bird flu or variant strain).
- activity_articles: seasonal items that report flu going on: a count (cases, deaths, hospitalized) or a
  trend that is present, moderate, high or rising.
- rising_articles: seasonal trend items that are rising or high.
- avian_articles: articles with a bird flu or variant item. A check, not a candidate.

The candidates are chosen on calibration seasons only (step 4). Nothing here looks at FluNet beyond the
onset date that fixes the week index.
"""

from datetime import date

import signal_config as cfg
from tables import Window

CONTENT_SIGNALS = ("content_articles", "seasonal_articles", "activity_articles", "rising_articles", "avian_articles")
SIGNALS = ("freq_articles",) + CONTENT_SIGNALS


def week_index(scan_date: date, onset: date) -> int:
    """Whole weeks from the onset, with the last window day (onset + 14) folded into week +1."""
    days = (scan_date - onset).days
    week = cfg.LAST_WEEK if days == 7 * (cfg.LAST_WEEK + 1) else days // 7
    if not cfg.FIRST_WEEK <= week <= cfg.LAST_WEEK:
        raise ValueError(f"{scan_date} is week {week} from onset {onset}, outside the window")
    return week


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


def build_weekly(articles: list[dict], items: list[dict], windows: dict[str, list[Window]]) -> list[dict]:
    """One row per season and week, in season and week order."""
    by_season = {window.season_id: window for country_windows in windows.values() for window in country_windows}
    counts = empty_series(windows)

    scan_dates = {}
    for article in articles:
        scan_dates[article["record_id"]] = date.fromisoformat(article["scan_date"])
        for season_id in filter(None, article["frequency_seasons"].split(";")):
            week = week_index(scan_dates[article["record_id"]], by_season[season_id].onset_date)
            counts[(season_id, week)]["freq_articles"] += 1

    # An article counts once per (season, signal), however many items it has.
    article_signals: dict[tuple[str, str], set[str]] = {}
    for item in items:
        key = (item["record_id"], item["season_id"])
        article_signals[key] = article_signals.get(key, set()) | item_signals(item)
    for (record_id, season_id), signals in article_signals.items():
        week = week_index(scan_dates[record_id], by_season[season_id].onset_date)
        for signal in signals:
            counts[(season_id, week)][signal] += 1

    rows = []
    for (season_id, week), values in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        window = by_season[season_id]
        season_year = int(season_id.split("-")[1])
        rows.append({"season_id": season_id, "country": window.country, "season_year": season_year,
                     "split": split_of(season_year), "headline": window.country in cfg.HEADLINE_COUNTRIES,
                     "onset_date": window.onset_date.isoformat(), "week": week, **values})
    return rows
