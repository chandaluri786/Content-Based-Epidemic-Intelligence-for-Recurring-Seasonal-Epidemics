from datetime import date

import pytest

from pipeline.config import COUNTRIES
from pipeline.ground_truth.ground_truth_builder import build_ground_truth_table


def flunet_row(iso_year, iso_week, processed, inf_all):
    return {
        "ISO_YEAR": str(iso_year),
        "ISO_WEEK": str(iso_week),
        "SPEC_PROCESSED_NB": str(processed) if processed is not None else "",
        "INF_ALL": str(inf_all) if inf_all is not None else "",
    }


def ukhsa_row(year, epiweek, value):
    return {"year": year, "epiweek": epiweek, "metric_value": value}


@pytest.mark.unit
class TestBuildGroundTruthTable:
    def test_positivity_country_with_onset_is_flagged_ok(self):
        def fake_flunet(iso3, year, page_size=100):
            if iso3 == "USA" and year == 2023:
                return [
                    flunet_row(2023, 1, 100, 2),
                    flunet_row(2023, 2, 100, 12),
                    flunet_row(2023, 3, 100, 13),
                ]
            return []

        rows = build_ground_truth_table(
            countries={"USA": COUNTRIES["USA"]},
            years=[2023],
            flunet_fetch=fake_flunet,
            ukhsa_fetch=lambda **kw: [],
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.country_iso3 == "USA"
        assert row.source == "FluNet"
        assert row.onset_method == "positivity_2wk"
        assert row.data_quality_flag == "ok"
        assert row.onset_iso_week == 2
        assert row.onset_date == date.fromisocalendar(2023, 2, 1)
        assert row.included_in_gdelt_cohort is True

    def test_positivity_country_with_no_onset_is_flagged_no_onset_found(self):
        def fake_flunet(iso3, year, page_size=100):
            return [flunet_row(2023, w, 100, 1) for w in range(1, 5)]

        rows = build_ground_truth_table(
            countries={"USA": COUNTRIES["USA"]},
            years=[2023],
            flunet_fetch=fake_flunet,
            ukhsa_fetch=lambda **kw: [],
        )
        assert rows[0].data_quality_flag == "no_onset_found"
        assert rows[0].onset_date is None

    def test_malformed_positivity_fields_are_treated_as_missing_not_fatal(self):
        def fake_flunet(iso3, year, page_size=100):
            return [
                {
                    "ISO_YEAR": "2023",
                    "ISO_WEEK": "1",
                    "SPEC_PROCESSED_NB": "garbage",
                    "INF_ALL": "5",
                },
                flunet_row(2023, 2, 100, 12),
                flunet_row(2023, 3, 100, 13),
            ]

        rows = build_ground_truth_table(
            countries={"USA": COUNTRIES["USA"]},
            years=[2023],
            flunet_fetch=fake_flunet,
            ukhsa_fetch=lambda **kw: [],
        )
        assert rows[0].onset_iso_week == 2

    def test_malformed_raw_count_field_is_treated_as_missing_not_fatal(self):
        def fake_flunet(iso3, year, page_size=100):
            return [
                {
                    "ISO_YEAR": "2023",
                    "ISO_WEEK": "1",
                    "SPEC_PROCESSED_NB": "",
                    "INF_ALL": "garbage",
                },
                flunet_row(2023, 2, None, 40),
            ]

        rows = build_ground_truth_table(
            countries={"JPN": COUNTRIES["JPN"]},
            years=[2023],
            flunet_fetch=fake_flunet,
            ukhsa_fetch=lambda **kw: [],
        )
        assert rows[0].onset_iso_week == 2
        assert rows[0].value_at_onset == 40.0

    def test_country_with_no_records_is_flagged_no_data(self):
        rows = build_ground_truth_table(
            countries={"USA": COUNTRIES["USA"]},
            years=[2023],
            flunet_fetch=lambda iso3, year, page_size=100: [],
            ukhsa_fetch=lambda **kw: [],
        )
        assert rows[0].data_quality_flag == "no_data"

    def test_gbr_uses_ukhsa_source_not_flunet(self):
        flunet_calls = []

        def fake_flunet(iso3, year, page_size=100):
            flunet_calls.append((iso3, year))
            return [flunet_row(year, 1, 100, 50)]  # would produce a bogus onset if used

        def fake_ukhsa(**kw):
            return [
                ukhsa_row(2023, 1, 2.0),
                ukhsa_row(2023, 2, 12.0),
                ukhsa_row(2023, 3, 13.0),
            ]

        rows = build_ground_truth_table(
            countries={"GBR": COUNTRIES["GBR"]},
            years=[2023],
            flunet_fetch=fake_flunet,
            ukhsa_fetch=fake_ukhsa,
        )
        assert flunet_calls == []
        row = rows[0]
        assert row.source == "UKHSA"
        assert row.onset_iso_week == 2
        assert row.data_quality_flag == "ok"

    def test_jpn_uses_peak_proxy_method(self):
        def fake_flunet(iso3, year, page_size=100):
            return [
                flunet_row(2023, 1, None, 5),
                flunet_row(2023, 2, None, 40),
                flunet_row(2023, 3, None, 10),
            ]

        rows = build_ground_truth_table(
            countries={"JPN": COUNTRIES["JPN"]},
            years=[2023],
            flunet_fetch=fake_flunet,
            ukhsa_fetch=lambda **kw: [],
        )
        row = rows[0]
        assert row.onset_method == "peak_count_proxy"
        assert row.data_quality_flag == "proxy_lower_rigor"
        assert row.onset_iso_week == 2
        assert row.value_at_onset == 40.0

    def test_bra_idn_rows_are_excluded_from_gdelt_cohort(self):
        rows = build_ground_truth_table(
            countries={"BRA": COUNTRIES["BRA"], "IDN": COUNTRIES["IDN"]},
            years=[2023],
            flunet_fetch=lambda iso3, year, page_size=100: [],
            ukhsa_fetch=lambda **kw: [],
        )
        assert all(r.included_in_gdelt_cohort is False for r in rows)

    def test_multiple_years_produce_one_row_each(self):
        def fake_flunet(iso3, year, page_size=100):
            return [flunet_row(year, w, 100, 1) for w in range(1, 5)]

        rows = build_ground_truth_table(
            countries={"USA": COUNTRIES["USA"]},
            years=[2022, 2023],
            flunet_fetch=fake_flunet,
            ukhsa_fetch=lambda **kw: [],
        )
        assert [r.year for r in rows] == [2022, 2023]

    def test_ukhsa_is_only_fetched_once_across_all_years(self):
        ukhsa_calls = []

        def fake_ukhsa(**kw):
            ukhsa_calls.append(1)
            return [ukhsa_row(y, w, 1.0) for y in (2022, 2023) for w in range(1, 5)]

        build_ground_truth_table(
            countries={"GBR": COUNTRIES["GBR"]},
            years=[2022, 2023],
            flunet_fetch=lambda iso3, year, page_size=100: [],
            ukhsa_fetch=fake_ukhsa,
        )
        assert len(ukhsa_calls) == 1
