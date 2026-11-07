"""Build the article table and the item table from the pool, the LLM replies and the gold labels.

Article table: one row per pool article (50,640). It says where the answer came from (gold, llm or
not_sent), whether it is useful, and every cohort country-season it counts in for the frequency signal.

Item table: one row per item about a cohort country. Each item counts toward its own country (not the
article's sampling country), in that country's season whose window holds the article's scan date.
Items about other countries, or dated outside that country's window, are left out and counted.
"""

from dataclasses import dataclass
from datetime import date

import signal_config as cfg


@dataclass(frozen=True)
class Window:
    season_id: str
    country: str
    onset_date: date
    window_start: date
    window_end: date


def parse_windows(raw_windows: list[dict]) -> dict[str, list[Window]]:
    """{country ISO3: [Window, ...]}. Windows of one country must never overlap."""
    by_country: dict[str, list[Window]] = {}
    for raw in raw_windows:
        window = Window(raw["season_id"], raw["country"], date.fromisoformat(raw["onset_date"]),
                        date.fromisoformat(raw["window_start"]), date.fromisoformat(raw["window_end"]))
        by_country.setdefault(window.country, []).append(window)
    for country, windows in by_country.items():
        ordered = sorted(windows, key=lambda w: w.window_start)
        for earlier, later in zip(ordered, ordered[1:]):
            if later.window_start <= earlier.window_end:
                raise ValueError(f"{country}: windows {earlier.season_id} and {later.season_id} overlap")
    return {country: sorted(windows, key=lambda w: w.window_start) for country, windows in by_country.items()}


def season_for(country: str, scan_date: date, windows: dict[str, list[Window]]) -> str | None:
    """The season of `country` whose window holds `scan_date` (both ends included), or None."""
    for window in windows.get(country, []):
        if window.window_start <= scan_date <= window.window_end:
            return window.season_id
    return None


def article_answer(record_id: str, gold: dict[str, dict], llm: dict[str, dict], layer: str | None) -> tuple[str, dict]:
    """(source, answer) of one pool article. Gold wins; an article without a reply must be one the filter dropped."""
    if record_id in gold:
        return cfg.SOURCE_GOLD, gold[record_id]
    if record_id in llm:
        return cfg.SOURCE_LLM, llm[record_id]
    if layer == cfg.DROPPED_LAYER:
        return cfg.SOURCE_NOT_SENT, {"useful": False, "items": [], "status": "not_sent"}
    raise ValueError(f"article {record_id} has no gold label, no LLM reply and was not dropped (layer {layer})")


def item_rows(record_id: str, scan_date: date, items: list[dict], windows: dict[str, list[Window]],
              skipped: dict[str, int]) -> list[dict]:
    """Rows of items about a cohort country inside that country's window. Adds skip reasons to `skipped`."""
    rows = []
    for index, item in enumerate(items):
        country = cfg.COHORT_COUNTRIES.get(item.get("country") or "")
        if country is None:
            skipped["not_cohort_country"] = skipped.get("not_cohort_country", 0) + 1
            continue
        season_id = season_for(country, scan_date, windows)
        if season_id is None:
            skipped["outside_country_window"] = skipped.get("outside_country_window", 0) + 1
            continue
        fields = {name: item.get(name) for name in cfg.ITEM_FIELDS}
        rows.append({"record_id": record_id, "item_index": index, "scan_date": scan_date.isoformat(),
                     "item_country": country, "season_id": season_id, **fields})
    return rows


def article_row(bucket_row: dict, source: str, answer: dict, country_seasons: list[str],
                content_seasons: list[str]) -> dict:
    """One article-table row. Lists are written ';'-joined."""
    return {
        "record_id": bucket_row["record_id"],
        "scan_date": bucket_row["scan_date"],
        "sampling_country": bucket_row["country"],
        "sampling_season": bucket_row["season"],
        "phase": bucket_row["phase"],
        "bucket": bucket_row["bucket"],
        "group_size": bucket_row["group_size"],
        "source": source,
        "status": answer["status"],
        "useful": answer["useful"],
        "n_items": len(answer["items"]),
        "frequency_seasons": ";".join(country_seasons),
        "content_seasons": ";".join(content_seasons),
    }


def build_tables(bucket_rows: list[dict], layers: dict[str, str], assignments: dict[str, list[str]],
                 gold: dict[str, dict], llm: dict[str, dict], windows: dict[str, list[Window]]) -> tuple[list, list, dict]:
    """(article rows, item rows, report). Every pool article must have an answer and a season list."""
    articles, items = [], []
    skipped: dict[str, int] = {}
    sources: dict[str, int] = {}
    for bucket_row in bucket_rows:
        record_id = bucket_row["record_id"]
        if record_id not in assignments:
            raise ValueError(f"article {record_id} is missing from season_assignments.jsonl")
        source, answer = article_answer(record_id, gold, llm, layers.get(record_id))
        sources[source] = sources.get(source, 0) + 1
        rows = item_rows(record_id, date.fromisoformat(bucket_row["scan_date"]), answer["items"], windows, skipped)
        content_seasons = sorted({row["season_id"] for row in rows})
        articles.append(article_row(bucket_row, source, answer, assignments[record_id], content_seasons))
        items.extend(rows)
    unused_llm = set(llm) - {row["record_id"] for row in articles}
    if unused_llm:
        raise ValueError(f"{len(unused_llm)} LLM replies are for articles not in the pool, e.g. {sorted(unused_llm)[:3]}")
    report = {
        "articles": len(articles),
        "by_source": sources,
        "useful_articles": sum(1 for row in articles if row["useful"]),
        "items_kept": len(items),
        "items_skipped": skipped,
    }
    return articles, items, report
