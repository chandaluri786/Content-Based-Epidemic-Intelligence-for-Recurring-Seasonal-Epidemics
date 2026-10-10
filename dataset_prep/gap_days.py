"""
Step 2 of pool preparation: which days the corrected season windows need
that no teammate's run has downloaded yet.

A day counts as covered if the pool holds at least one article from it --
a covered day averages hundreds of matches, so an empty day almost always
means it was never processed. (A day processed but yielding nothing would
be redone; that's cheap and harmless.)

The gap list is turned into a seeded checkpoint file: every needed day
that is NOT a gap is pre-marked complete for every cohort country, so a
normal run_pipeline.py invocation pointed at it (PIPELINE_COMPLETED_DAYS_PATH)
processes only the gaps. Same mechanism as output/redownload_2015_2020/.

A gap-fill run is bound by waiting, not CPU: each day waits for its slowest
article fetches (dead sites time out) before the next day starts. So the
gaps can be split into disjoint shards, one seeded checkpoint each, and run
as independent processes side by side -- each shard's checkpoint leaves
only its own days to process.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from models import CountrySeasonWindow
from pipeline.windows import unique_days_across_cohort


def covered_days(pool_path: Path) -> set[date]:
    days: set[date] = set()
    with pool_path.open(encoding="utf-8") as f:
        for line in f:
            days.add(date.fromisoformat(json.loads(line)["datetime"][:10]))
    return days


def find_gap_days(cohort: list[CountrySeasonWindow], covered: set[date]) -> list[date]:
    return sorted(unique_days_across_cohort(cohort) - covered)


def seeded_checkpoint(cohort: list[CountrySeasonWindow], gaps: list[date],
                      countries: set[str]) -> dict[date, set[str]]:
    """completed_days content that leaves exactly the gap days to process."""
    gap_set = set(gaps)
    return {day: set(countries) for day in unique_days_across_cohort(cohort) if day not in gap_set}


def shard_days(gaps: list[date], shard_count: int) -> list[list[date]]:
    """Round-robin split, so every shard gets a mix of years (older years
    are slower: more dead links)."""
    return [gaps[i::shard_count] for i in range(min(shard_count, len(gaps)))]
