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

Item signals (post hoc, added 2026-11-19, at the end of this file): the five case, hospitalisation and death
series built by COUNT_SIGNAL_RULES.md, their "as known at week t" versions for the replay, and the flu-word
frequency baseline. They are written to their own files; the signals above are unchanged.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
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


# ---------------------------------------------------------------------------------------------------------------
# Item signals (post hoc, 2026-11-19). The rules are COUNT_SIGNAL_RULES.md; section numbers below refer to it.
# Unlike the article signals above, these count the item numbers, and an item sits in the ISO week its events
# happened in (not its scan week). The article signals above are not changed by anything below.
# ---------------------------------------------------------------------------------------------------------------

USED = "used"
# Drop reasons, as in the report (Section 7).
NULL_START = "null_start"                      # 1.3
SPANS_WEEKS = "spans_weeks"                    # 1.4
CLOSED_BY_HIGHER_REGION = "closed_by_higher_region"   # Rule 2: a day closed by a region item higher up
SAME_ARTICLE_GUARD = "same_article_guard"      # 3.0
REGION_NOT_USED = "region_not_used"            # 3.1: days already taken by a region item at the same place
COVERED_OR_PARTIAL = "covered_or_partial"      # 3.2 / 3.4: on or across days covered at the same place
NEW_INSIDE_SUBSET = "new_inside_subset"        # 3.3
INVALID = "invalid"                            # a value the prompt cannot produce: left out and listed in the report


def iso_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def iso_week_label(monday: date) -> str:
    year, week, _ = monday.isocalendar()
    return f"{year}-W{week:02d}"


@dataclass(frozen=True)
class CountItem:
    """One cases, hospitalized or deaths item that passed Stage 1."""
    item_id: str                 # record_id:item_index
    record_id: str               # the article
    scan_date: date
    country_code: str            # ISO3 (items.csv item_country)
    kind: str
    status: str
    count_type: str
    number: int
    place: tuple                 # (country, state, city), None for an empty field
    start: date
    end: date

    @property
    def level(self) -> int:      # 0 country, 1 state, 2 city
        return 2 if self.place[2] else (1 if self.place[1] else 0)

    @property
    def days(self) -> frozenset:
        return frozenset(self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1))


def _blank(value) -> str | None:
    text = (value or "").strip()
    return text or None


def _number(value, where: str) -> int:
    text = (value or "").strip()
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"{where}: number {value!r} is not a number") from None
    if number < 0 or number != int(number):
        raise ValueError(f"{where}: number {value!r} is not a whole number of 0 or more")
    return int(number)


def _day(value: str, where: str, name: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"{where}: {name} {value!r} is not a YYYY-MM-DD date") from None


def count_item(row: dict) -> tuple[CountItem | None, str | None]:
    """Stage 1 for one items.csv row: (item, None) if it is used, (None, reason) if it is dropped, (None, None)
    if it is not a count (a trend). A value the prompt cannot produce raises ValueError naming the row;
    screen_item turns that into an INVALID drop."""
    if row["kind"] not in cfg.COUNT_KINDS:
        return None, None
    where = f"item {row['record_id']}:{row['item_index']}"
    if row["status"] not in cfg.STATUSES:
        raise ValueError(f"{where}: unknown status {row['status']!r}")
    if row["count_type"] not in cfg.COUNT_TYPES:
        raise ValueError(f"{where}: unknown count_type {row['count_type']!r}")
    if not _blank(row.get("end_date")):
        raise ValueError(f"{where}: end_date is empty (prompt G2 makes it mandatory)")
    if not _blank(row.get("start_date")):
        return None, NULL_START
    start, end = _day(row["start_date"], where, "start_date"), _day(row["end_date"], where, "end_date")
    if start > end:
        raise ValueError(f"{where}: start_date {start} is after end_date {end}")
    if iso_monday(start) != iso_monday(end):
        return None, SPANS_WEEKS
    if row["count_type"] == "new" and start != end:
        raise ValueError(f"{where}: a new count must cover one day (prompt 4.2), got {start} to {end}")
    place = (_blank(row.get("country")), _blank(row.get("state")), _blank(row.get("city")))
    if place[0] is None:
        raise ValueError(f"{where}: country is empty (prompt G1 makes it mandatory)")
    item = CountItem(f"{row['record_id']}:{row['item_index']}", row["record_id"],
                     _day(row["scan_date"], where, "scan_date"), row["item_country"], row["kind"], row["status"],
                     row["count_type"], _number(row.get("number"), where), place, start, end)
    return item, None


def screen_item(row: dict) -> tuple[CountItem | None, str | None, str | None]:
    """count_item that never stops the run: a row with a value the prompt cannot produce is left out as INVALID,
    with the problem, so every such row shows in the report instead of only the first one."""
    try:
        item, reason = count_item(row)
    except ValueError as problem:
        return None, INVALID, str(problem)
    return item, reason, None


def parent_of(place: tuple) -> tuple | None:
    """A city's parent is its state, or its country when the state is empty; a state's parent is its country."""
    country, state, city = place
    if city:
        return (country, state, None) if state else (country, None, None)
    if state:
        return (country, None, None)
    return None


@dataclass
class WeekResult:
    """One country, kind, status and ISO week."""
    value: int = 0
    decisions: dict = field(default_factory=dict)        # item_id -> USED or a drop reason
    overlap_risk_place_days: int = 0                      # Section 7: lower items on higher new/subset days


def _place_value(place: tuple, open_days: frozenset, higher: list[CountItem], by_place: dict, children: dict,
                 result: WeekResult) -> int:
    """Stages 2-4 at one place: region first, then new and subset items, then the children on the days left."""
    own = []
    for item in by_place.get(place, []):
        if not item.days <= open_days:                            # a day closed by a region item higher up
            result.decisions[item.item_id] = CLOSED_BY_HIGHER_REGION
        elif any(g.record_id == item.record_id and g.days & item.days for g in higher):
            result.decisions[item.item_id] = SAME_ARTICLE_GUARD   # 3.0
        else:
            own.append(item)

    total, covered = 0, frozenset()
    regions = sorted((i for i in own if i.count_type == "cumulative_region"),
                     key=lambda i: (-len(i.days), -i.number, i.start, i.item_id))
    for region in regions:                                        # 3.1
        if region.days & covered:
            result.decisions[region.item_id] = REGION_NOT_USED
        else:
            covered |= region.days
            total += region.number
            result.decisions[region.item_id] = USED

    fill = open_days - covered                                    # 3.2
    subsets = []
    for subset in (i for i in own if i.count_type == "cumulative_subset"):
        if subset.days <= fill:
            subsets.append(subset)
            result.decisions[subset.item_id] = USED
        else:
            result.decisions[subset.item_id] = COVERED_OR_PARTIAL
    news = []
    for new in (i for i in own if i.count_type == "new"):
        if not new.days <= fill:
            result.decisions[new.item_id] = COVERED_OR_PARTIAL
        elif any(s.record_id == new.record_id and new.start in s.days for s in subsets):
            result.decisions[new.item_id] = NEW_INSIDE_SUBSET     # 3.3
        else:
            news.append(new)
            result.decisions[new.item_id] = USED
    total += sum(i.number for i in subsets) + sum(i.number for i in news)

    used_here = [i for i in own if result.decisions[i.item_id] == USED]
    higher_fill = [g for g in higher if g.count_type != "cumulative_region"]
    risky_days = {(place, day) for i in used_here for g in higher_fill if g.record_id != i.record_id
                  for day in i.days & g.days}
    result.overlap_risk_place_days += len(risky_days)

    passed = open_days - covered                                  # 3.5: only region days are closed
    for child in sorted(children.get(place, []), key=str):
        total += _place_value(child, passed, higher + subsets + news, by_place, children, result)
    return total


def week_value(items: list[CountItem], monday: date) -> WeekResult:
    """The country value of one country, kind, status and ISO week (Section 6), from items all in that week."""
    by_place: dict[tuple, list[CountItem]] = defaultdict(list)
    for item in items:
        if iso_monday(item.start) != monday:
            raise ValueError(f"item {item.item_id} is not in the week of {monday}")
        by_place[item.place].append(item)
    children: dict[tuple, set] = defaultdict(set)
    roots = set()
    for place in list(by_place):
        node = place
        while (parent := parent_of(node)) is not None:
            children[parent].add(node)
            node = parent
        roots.add(node)
    result = WeekResult()
    week_days = frozenset(monday + timedelta(days=i) for i in range(7))
    for root in sorted(roots, key=str):          # one root per country name; normally just one
        result.value += _place_value(root, week_days, [], by_place, children, result)
    return result


def country_week_values(items: list[CountItem]) -> dict[tuple, WeekResult]:
    """{(country ISO3, kind, status, ISO Monday): WeekResult} over every group that has items."""
    groups: dict[tuple, list[CountItem]] = defaultdict(list)
    for item in items:
        groups[(item.country_code, item.kind, item.status, iso_monday(item.start))].append(item)
    return {key: week_value(group, key[3]) for key, group in groups.items()}


def count_signal_rows(values: dict[tuple, WeekResult], items: list[CountItem]) -> list[dict]:
    """output/count_signals.csv: one row per group with at least one item used (Section 7)."""
    article_of = {item.item_id: item.record_id for item in items}
    rows = []
    for (country, kind, status, monday), result in sorted(values.items()):
        used = [item_id for item_id, decision in result.decisions.items() if decision == USED]
        if used:
            rows.append({"country": country, "iso_week": iso_week_label(monday), "week_start": monday.isoformat(),
                         "kind": kind, "status": status, "value": result.value, "n_items_used": len(used),
                         "n_articles_used": len({article_of[item_id] for item_id in used})})
    return rows


def series_name(kind: str, status: str) -> str | None:
    return next((name for name, pair in cfg.ITEM_SERIES.items() if pair == (kind, status)), None)


def count_report(rows: list[dict], values: dict[tuple, WeekResult]) -> dict:
    """output/count_signals_report.json: drops per rule and overlap risk, per item series (Section 7)."""
    report: dict[str, dict] = {}
    for row in rows:
        item, reason, _ = screen_item(row)
        if item is None and reason is None:
            continue
        name = series_name(row["kind"], row["status"]) or f"{row['kind']}_{row['status']}"
        entry = report.setdefault(name, {"items": 0, "decisions": Counter(), "overlap_risk_place_days": 0})
        entry["items"] += 1
        if reason is not None:
            entry["decisions"][reason] += 1
    for (country, kind, status, monday), result in values.items():
        name = series_name(kind, status) or f"{kind}_{status}"
        entry = report.setdefault(name, {"items": 0, "decisions": Counter(), "overlap_risk_place_days": 0})
        entry["decisions"].update(result.decisions.values())
        entry["overlap_risk_place_days"] += result.overlap_risk_place_days
    return {name: {"items": entry["items"], "decisions": dict(sorted(entry["decisions"].items())),
                   "overlap_risk_place_days": entry["overlap_risk_place_days"]}
            for name, entry in sorted(report.items())}


def week_monday(window: Window, week: int) -> date:
    """The ISO Monday of season week `week` (onsets are Mondays, so season weeks are ISO weeks)."""
    if window.onset_date.weekday() != 0:
        raise ValueError(f"{window.season_id}: onset {window.onset_date} is not a Monday")
    return window.onset_date + timedelta(days=7 * week)


def item_series(items: list[CountItem], window: Window, known_by: date | None = None) -> dict[str, list[int]]:
    """The five item series of one season, weeks FIRST_WEEK..LAST_WEEK, from the items of its country scanned
    on or before `known_by` (all of them when None). A week with no item used is 0 for the detectors."""
    mondays = {week_monday(window, week) for week in range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1)}
    known = [i for i in items if i.country_code == window.country and iso_monday(i.start) in mondays
             and (known_by is None or i.scan_date <= known_by)]
    values = country_week_values(known)
    series = {}
    for name, (kind, status) in cfg.ITEM_SERIES.items():
        series[name] = [values[key].value if (key := (window.country, kind, status, week_monday(window, week))) in values
                        else 0 for week in range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1)]
    return series


def item_vintages(items: list[CountItem], window: Window) -> dict[str, list[list[int]]]:
    """{series: [the 12-week series as known at the end of each season week]} for the replay
    (COMBINED_SIGNAL_RULES 3): at week t only articles scanned by the Sunday of week t are seen."""
    weeks = range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1)
    known = [item_series(items, window, week_monday(window, week) + timedelta(days=6)) for week in weeks]
    return {name: [vintage[name] for vintage in known] for name in cfg.ITEM_SERIES}


def flu_word_frequency(articles: list[dict], windows: dict[str, list[Window]]) -> dict[tuple[str, int], int]:
    """freq_articles counted only over articles the keyword filter sent on (source != not_sent)."""
    by_season = {window.season_id: window for country_windows in windows.values() for window in country_windows}
    labels = {season_id: season_weeks(window) for season_id, window in by_season.items()}
    counts: Counter = Counter()
    for article in articles:
        if article["source"] == cfg.SOURCE_NOT_SENT:
            continue
        for season_id in filter(None, article["frequency_seasons"].split(";")):
            week = week_label(date.fromisoformat(article["scan_date"]), by_season[season_id], labels[season_id])
            if week is not None:          # same strict ISO weeks as freq_articles: partial-week days dropped
                counts[(season_id, week)] += 1
    return counts


def build_item_weekly(articles: list[dict], item_rows: list[dict], windows: dict[str, list[Window]]) -> dict:
    """Everything step 2 writes for the item signals: count_signals rows, the report, item_weekly_signals rows
    and item_vintages rows."""
    items, invalid = [], []
    for row in item_rows:
        item, reason, problem = screen_item(row)
        if item is not None:
            items.append(item)
        elif reason == INVALID:
            invalid.append({"record_id": row.get("record_id"), "item_index": row.get("item_index"),
                            "kind": row.get("kind"), "status": row.get("status"), "problem": problem})
    values = country_week_values(items)
    flu_word = flu_word_frequency(articles, windows)
    weekly_rows, vintage_rows = [], []
    for window in sorted((w for ws in windows.values() for w in ws), key=lambda w: w.season_id):
        season_year = int(window.season_id.split("-")[1])
        final = item_series(items, window)
        for position, week in enumerate(range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1)):
            weekly_rows.append({"season_id": window.season_id, "country": window.country, "season_year": season_year,
                                "split": split_of(season_year), "headline": window.country in cfg.HEADLINE_COUNTRIES,
                                "onset_date": window.onset_date.isoformat(), "week": week,
                                cfg.FLU_WORD_FREQUENCY_SIGNAL: flu_word[(window.season_id, week)],
                                **{name: final[name][position] for name in cfg.ITEM_SERIES}})
        for name, vintages in item_vintages(items, window).items():
            for as_of, vintage in zip(range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1), vintages):
                for week, value in zip(range(cfg.FIRST_WEEK, cfg.LAST_WEEK + 1), vintage):
                    vintage_rows.append({"season_id": window.season_id, "signal": name, "as_of_week": as_of,
                                         "week": week, "value": value})
    return {"count_rows": count_signal_rows(values, items), "report": count_report(item_rows, values),
            "invalid_items": invalid, "weekly_rows": weekly_rows, "vintage_rows": vintage_rows}
