"""Country-level relative-intensity aggregation (Step 7, lightweight).

Choropleth/chart rendering is a presentation-layer concern handled outside
the pipeline (notebook/report step), not built here.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CountryIntensity:
    country_iso3: str
    total_relevant_articles: int
    articles_per_season_avg: float
    relative_intensity_score: float | None
    not_measured: bool


def compute_country_relative_intensity(
    weeks, all_cohort_countries: list[str]
) -> list[CountryIntensity]:
    """Min-max normalized (0-1) relative intensity across the countries that
    actually have ingested data. A country in all_cohort_countries but absent
    from `weeks` (e.g. Brazil/Indonesia, excluded from GDELT ingestion) is
    flagged not_measured=True with a None score, never a silent zero."""
    totals: dict[str, int] = {}
    season_years: dict[str, set[int]] = {}

    for w in weeks:
        totals[w.country_iso3] = totals.get(w.country_iso3, 0) + w.content_relevant_count
        season_years.setdefault(w.country_iso3, set()).add(w.season_year)

    measured_totals = list(totals.values())
    max_total = max(measured_totals, default=0)
    min_total = min(measured_totals, default=0)
    span = max_total - min_total

    results: list[CountryIntensity] = []
    for country in all_cohort_countries:
        if country not in totals:
            results.append(
                CountryIntensity(
                    country_iso3=country,
                    total_relevant_articles=0,
                    articles_per_season_avg=0.0,
                    relative_intensity_score=None,
                    not_measured=True,
                )
            )
            continue

        total = totals[country]
        n_seasons = len(season_years[country])
        avg = total / n_seasons if n_seasons else 0.0
        score = (total - min_total) / span if span > 0 else 0.0

        results.append(
            CountryIntensity(
                country_iso3=country,
                total_relevant_articles=total,
                articles_per_season_avg=avg,
                relative_intensity_score=score,
                not_measured=False,
            )
        )

    return results
