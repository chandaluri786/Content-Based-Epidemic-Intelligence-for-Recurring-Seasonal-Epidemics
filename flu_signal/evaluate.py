"""Step 5: score the frozen settings season by season and compare content with frequency.

Rules (agreed 2026-11-07, before the held-out run):
- outcome per season and signal, as in step 4: hit (alarm in weeks -4..+1), false alarm (earlier), miss (none);
- lead_days = 7 x (-alarm week): week -2 is 14 days early. lead_days_known = 7 x (-alarm week - 1): counted
  from the end of the alarm week, when all its articles are in (week -2 is 7 days early, week 0 is 7 days late);
- per season, utility hit = +1, miss = 0, false alarm = -1. Content wins a season if its utility is higher, or
  both hit and content alarms earlier. Same utility and same week (or both miss) is a tie;
- exact two-sided sign test on wins vs losses (with 9 seasons it has little power, so mostly descriptive);
- content is "better" when its score (hits - false alarms) is at least frequency's AND it wins more seasons
  than it loses;
- secondary: Ganser's "timely" detection, an alarm in weeks -2..+1.
"""

import math
from statistics import median

import signal_config as cfg
from scoring import FALSE_ALARM, HIT, MISS, classify

CONTENT, FREQUENCY, TIE = "content", "frequency", "tie"
UTILITY = {HIT: 1, MISS: 0, FALSE_ALARM: -1}
TIMELY_FIRST_WEEK = -2
DAYS_PER_WEEK = 7


def lead_days(alarm_week: int | None) -> int | None:
    return None if alarm_week is None else -DAYS_PER_WEEK * alarm_week


def lead_days_known(alarm_week: int | None) -> int | None:
    return None if alarm_week is None else -DAYS_PER_WEEK * (alarm_week + 1)


def is_timely(alarm_week: int | None) -> bool:
    return alarm_week is not None and TIMELY_FIRST_WEEK <= alarm_week <= cfg.LAST_WEEK


def compare_season(content_week: int | None, frequency_week: int | None,
                   early_limit: int = cfg.EARLY_LIMIT) -> str:
    """Which signal did better in one season: content, frequency or tie."""
    content_outcome, frequency_outcome = classify(content_week, early_limit), classify(frequency_week, early_limit)
    if UTILITY[content_outcome] != UTILITY[frequency_outcome]:
        return CONTENT if UTILITY[content_outcome] > UTILITY[frequency_outcome] else FREQUENCY
    if content_outcome == HIT and content_week != frequency_week:
        return CONTENT if content_week < frequency_week else FREQUENCY
    return TIE


def sign_test(wins: int, losses: int) -> float:
    """Exact two-sided sign test p-value; ties are left out. 1.0 when there is nothing to test."""
    n = wins + losses
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2 ** n
    return min(1.0, 2.0 * tail)


def season_row(season_id: str, country: str, content_week: int | None, frequency_week: int | None,
               early_limit: int = cfg.EARLY_LIMIT, **extra) -> dict:
    """One season of the results table. early_limit other than 4 is only for the post-hoc checks."""
    row = {"season_id": season_id, "country": country, **extra}
    for role, week in ((CONTENT, content_week), (FREQUENCY, frequency_week)):
        row[f"{role}_alarm_week"] = week
        row[f"{role}_outcome"] = classify(week, early_limit)
        row[f"{role}_lead_days"] = lead_days(week)
        row[f"{role}_lead_days_known"] = lead_days_known(week)
        row[f"{role}_timely"] = is_timely(week)
    row["winner"] = compare_season(content_week, frequency_week, early_limit)
    return row


def _signal_summary(rows: list[dict], role: str) -> dict:
    outcomes = [row[f"{role}_outcome"] for row in rows]
    leads = [row[f"{role}_lead_days"] for row in rows if row[f"{role}_outcome"] == HIT]
    known = [row[f"{role}_lead_days_known"] for row in rows if row[f"{role}_outcome"] == HIT]
    hits, false_alarms = outcomes.count(HIT), outcomes.count(FALSE_ALARM)
    return {"hits": hits, "false_alarms": false_alarms, "misses": outcomes.count(MISS),
            "score": hits - false_alarms, "timely": sum(1 for row in rows if row[f"{role}_timely"]),
            "median_lead_days": median(leads) if leads else None,
            "median_lead_days_known": median(known) if known else None}


def summarize(rows: list[dict]) -> dict:
    """Headline numbers for a set of season rows."""
    winners = [row["winner"] for row in rows]
    wins, losses, ties = winners.count(CONTENT), winners.count(FREQUENCY), winners.count(TIE)
    content, frequency = _signal_summary(rows, CONTENT), _signal_summary(rows, FREQUENCY)
    both_hit = [row["content_lead_days"] - row["frequency_lead_days"] for row in rows
                if row["content_outcome"] == HIT and row["frequency_outcome"] == HIT]
    return {
        "seasons": len(rows),
        CONTENT: content,
        FREQUENCY: frequency,
        "content_wins": wins, "frequency_wins": losses, "ties": ties,
        "sign_test_p": round(sign_test(wins, losses), 4),
        "both_hit_seasons": len(both_hit),
        "median_lead_difference_days_when_both_hit": median(both_hit) if both_hit else None,
        "content_better": content["score"] >= frequency["score"] and wins > losses,
    }
