from datetime import date

import pytest

from pipeline.join.epiweek_join import CountryWeekJoined
from pipeline.mapping.intensity_map import compute_country_relative_intensity


def week(country: str, season_year: int, relevant: int) -> CountryWeekJoined:
    return CountryWeekJoined(
        country_iso3=country,
        season_year=season_year,
        iso_year=season_year,
        iso_week=1,
        week_start_date=date(season_year, 1, 2),
        content_relevant_count=relevant,
        frequency_raw_count=0,
        is_baseline_week=False,
        days_from_onset=0,
    )


@pytest.mark.unit
class TestComputeCountryRelativeIntensity:
    def test_totals_and_averages_are_computed_per_country(self):
        weeks = [
            week("USA", 2022, 10),
            week("USA", 2023, 20),
            week("KEN", 2022, 5),
        ]
        results = {
            r.country_iso3: r for r in compute_country_relative_intensity(weeks, ["USA", "KEN"])
        }
        assert results["USA"].total_relevant_articles == 30
        assert results["USA"].articles_per_season_avg == pytest.approx(15.0)
        assert results["KEN"].total_relevant_articles == 5
        assert results["KEN"].articles_per_season_avg == pytest.approx(5.0)

    def test_min_max_normalization_across_measured_countries(self):
        weeks = [week("USA", 2022, 100), week("KEN", 2022, 0), week("IND", 2022, 50)]
        results = {
            r.country_iso3: r
            for r in compute_country_relative_intensity(weeks, ["USA", "KEN", "IND"])
        }
        assert results["USA"].relative_intensity_score == pytest.approx(1.0)
        assert results["KEN"].relative_intensity_score == pytest.approx(0.0)
        assert results["IND"].relative_intensity_score == pytest.approx(0.5)

    def test_country_absent_from_weeks_is_flagged_not_measured(self):
        weeks = [week("USA", 2022, 10)]
        results = {
            r.country_iso3: r for r in compute_country_relative_intensity(weeks, ["USA", "BRA"])
        }
        assert results["BRA"].not_measured is True
        assert results["BRA"].relative_intensity_score is None
        assert results["USA"].not_measured is False

    def test_zero_variance_across_all_measured_countries_yields_zero_score(self):
        weeks = [week("USA", 2022, 10), week("KEN", 2022, 10)]
        results = {
            r.country_iso3: r for r in compute_country_relative_intensity(weeks, ["USA", "KEN"])
        }
        assert results["USA"].relative_intensity_score == pytest.approx(0.0)
        assert results["KEN"].relative_intensity_score == pytest.approx(0.0)

    def test_empty_weeks_flags_all_countries_not_measured(self):
        results = {
            r.country_iso3: r for r in compute_country_relative_intensity([], ["USA", "KEN"])
        }
        assert all(r.not_measured for r in results.values())
