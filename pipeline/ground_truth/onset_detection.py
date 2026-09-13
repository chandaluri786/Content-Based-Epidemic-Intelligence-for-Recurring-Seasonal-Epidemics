"""Season-onset detection: flat positivity-rate rule (most countries) and
Japan's peak-count proxy (FluNet lacks a specimen-processed denominator there).

Both are asked to determine "when did this country-season's flu season begin,"
just from different signals (percent test-positivity vs raw case count).
"""

from dataclasses import dataclass
from datetime import date

from pipeline.common.epiweek import date_from_iso_week
from pipeline.common.sustained_crossing import find_sustained_crossing
from pipeline.config import ONSET_POSITIVITY_THRESHOLD_PCT, ONSET_SUSTAIN_WEEKS, OnsetMethod


@dataclass(frozen=True)
class WeeklyValue:
    iso_year: int
    iso_week: int
    value: float | None


@dataclass(frozen=True)
class OnsetResult:
    onset_iso_year: int
    onset_iso_week: int
    onset_date: date
    value_at_onset: float | None
    onset_method: OnsetMethod


def _sorted_by_week(series: list[WeeklyValue]) -> list[WeeklyValue]:
    return sorted(series, key=lambda w: (w.iso_year, w.iso_week))


def find_onset_flat_rule(
    series: list[WeeklyValue],
    threshold: float = ONSET_POSITIVITY_THRESHOLD_PCT,
    sustain_weeks: int = ONSET_SUSTAIN_WEEKS,
) -> OnsetResult | None:
    """First week where `value` (percent positivity) is >= threshold for
    `sustain_weeks` consecutive weeks."""
    if not series:
        return None

    rows = _sorted_by_week(series)
    values = [r.value for r in rows]
    index = find_sustained_crossing(values, threshold=threshold, sustain_periods=sustain_weeks)
    if index is None:
        return None

    onset_row = rows[index]
    return OnsetResult(
        onset_iso_year=onset_row.iso_year,
        onset_iso_week=onset_row.iso_week,
        onset_date=date_from_iso_week(onset_row.iso_year, onset_row.iso_week),
        value_at_onset=onset_row.value,
        onset_method="positivity_2wk",
    )


def find_onset_peak_proxy(series: list[WeeklyValue]) -> OnsetResult | None:
    """Japan-only proxy: treat the single week with the highest raw case count
    as the onset week, since FluNet's Japan records lack a specimen-processed
    denominator to compute a positivity rate. Ties broken by earliest week.
    Documented as a lower-rigor method (config.CountryDef.onset_method)."""
    candidates = [r for r in series if r.value is not None]
    if not candidates:
        return None

    peak_row = max(_sorted_by_week(candidates), key=lambda r: r.value)
    return OnsetResult(
        onset_iso_year=peak_row.iso_year,
        onset_iso_week=peak_row.iso_week,
        onset_date=date_from_iso_week(peak_row.iso_year, peak_row.iso_week),
        value_at_onset=peak_row.value,
        onset_method="peak_count_proxy",
    )
