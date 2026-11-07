"""Step 4 scoring: how good one detector setting is across a set of seasons.

Per season, with the alarm week a (onset = week 0):
- hit: a in [-EARLY_LIMIT, LAST_WEEK]. The lead is -a weeks (a = -2 is 2 weeks early).
- false alarm: a < -EARLY_LIMIT, too early to be this season's rise.
- miss: no alarm.
Score = hits - false alarms. Ties go to more hits, then fewer false alarms, then an earlier median
alarm week among hits, then the plainer setting (cut-off nearest 0.5, smaller sustain, margin 0).
"""

from dataclasses import dataclass
from statistics import median

import signal_config as cfg

HIT, FALSE_ALARM, MISS = "hit", "false_alarm", "miss"


@dataclass(frozen=True)
class Setting:
    signal: str
    method: str
    cutoff: float
    sustain_weeks: int
    margin: float


@dataclass(frozen=True)
class Score:
    hits: int
    false_alarms: int
    misses: int
    median_hit_week: float | None

    @property
    def value(self) -> int:
        return self.hits - self.false_alarms


def classify(alarm_week: int | None, early_limit: int = cfg.EARLY_LIMIT) -> str:
    if alarm_week is None:
        return MISS
    if not cfg.FIRST_WEEK <= alarm_week <= cfg.LAST_WEEK:
        raise ValueError(f"alarm week {alarm_week} is outside the window")
    return FALSE_ALARM if alarm_week < -early_limit else HIT


def score_setting(alarm_weeks: list[int | None], early_limit: int = cfg.EARLY_LIMIT) -> Score:
    outcomes = [classify(week, early_limit) for week in alarm_weeks]
    hit_weeks = [week for week, outcome in zip(alarm_weeks, outcomes) if outcome == HIT]
    return Score(hits=outcomes.count(HIT), false_alarms=outcomes.count(FALSE_ALARM), misses=outcomes.count(MISS),
                 median_hit_week=float(median(hit_weeks)) if hit_weeks else None)


def rank_key(setting: Setting, score: Score) -> tuple:
    """Smaller is better. The order is the tie-break order in the module doc."""
    median_week = score.median_hit_week if score.median_hit_week is not None else float("inf")
    return (-score.value, -score.hits, score.false_alarms, median_week, abs(setting.cutoff - 0.5),
            setting.sustain_weeks, setting.margin, setting.method)


def rank(scored: list[tuple[Setting, Score]]) -> list[tuple[Setting, Score]]:
    return sorted(scored, key=lambda pair: rank_key(*pair))
