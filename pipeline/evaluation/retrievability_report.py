"""Full-scale retrievability/content-depth summary (Step 8), computed with the
exact same method as the feasibility spike (retrievable = text length > 200
chars, content_rich = >=1 content-marker hit) so the numbers are directly
comparable to the spike's 88%/88% aggregate figure.
"""

from dataclasses import dataclass

SPIKE_BASELINE_PCT = 88.0
DIVERGENCE_THRESHOLD_POINTS = 10.0


@dataclass(frozen=True)
class ArticleRetrievabilityRecord:
    country_iso3: str
    retrievable: bool
    content_rich: bool


@dataclass(frozen=True)
class CountryRetrievabilitySummary:
    country_iso3: str
    n_articles: int
    pct_retrievable: float
    pct_content_rich: float


def summarize_retrievability(
    records: list[ArticleRetrievabilityRecord],
) -> list[CountryRetrievabilitySummary]:
    by_country: dict[str, list[ArticleRetrievabilityRecord]] = {}
    for record in records:
        by_country.setdefault(record.country_iso3, []).append(record)

    summaries = []
    for country, country_records in by_country.items():
        n = len(country_records)
        pct_retrievable = 100.0 * sum(r.retrievable for r in country_records) / n
        pct_content_rich = 100.0 * sum(r.content_rich for r in country_records) / n
        summaries.append(
            CountryRetrievabilitySummary(country, n, pct_retrievable, pct_content_rich)
        )

    return summaries


def diverges_from_spike_baseline(
    pct_value: float,
    baseline: float = SPIKE_BASELINE_PCT,
    threshold_points: float = DIVERGENCE_THRESHOLD_POINTS,
) -> bool:
    """Flag when a full-scale percentage differs from the spike's baseline by
    more than threshold_points, in either direction."""
    return abs(pct_value - baseline) > threshold_points
