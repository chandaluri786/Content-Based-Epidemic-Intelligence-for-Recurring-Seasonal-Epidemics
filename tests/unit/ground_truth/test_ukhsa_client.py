import pytest

from pipeline.ground_truth.ukhsa_client import UKHSA_ENDPOINT_URL, fetch_all_weekly_records


@pytest.mark.unit
class TestFetchAllWeeklyRecords:
    def test_single_page_returns_all_results(self, requests_mock):
        requests_mock.get(
            UKHSA_ENDPOINT_URL,
            json={
                "count": 2,
                "next": None,
                "previous": None,
                "results": [
                    {"year": 2017, "epiweek": 27, "metric_value": 1.71, "age": "all"},
                    {"year": 2017, "epiweek": 28, "metric_value": 1.22, "age": "all"},
                ],
            },
        )
        records = fetch_all_weekly_records()
        assert len(records) == 2
        assert records[0]["metric_value"] == 1.71

    def test_follows_next_link_across_pages(self, requests_mock):
        page_2_url = UKHSA_ENDPOINT_URL + "?page=2&page_size=2"
        requests_mock.get(
            UKHSA_ENDPOINT_URL,
            json={
                "count": 3,
                "next": page_2_url,
                "previous": None,
                "results": [
                    {"year": 2017, "epiweek": 27, "metric_value": 1.71, "age": "all"},
                    {"year": 2017, "epiweek": 28, "metric_value": 1.22, "age": "all"},
                ],
            },
        )
        requests_mock.get(
            page_2_url,
            json={
                "count": 3,
                "next": None,
                "previous": UKHSA_ENDPOINT_URL,
                "results": [
                    {"year": 2017, "epiweek": 29, "metric_value": 0.8, "age": "all"},
                ],
            },
        )
        records = fetch_all_weekly_records()
        assert len(records) == 3
        assert requests_mock.call_count == 2

    def test_empty_results_returns_empty_list(self, requests_mock):
        requests_mock.get(
            UKHSA_ENDPOINT_URL,
            json={"count": 0, "next": None, "previous": None, "results": []},
        )
        assert fetch_all_weekly_records() == []

    def test_first_request_filters_to_all_age_sex_default_stratum(self, requests_mock):
        requests_mock.get(
            UKHSA_ENDPOINT_URL,
            json={"count": 0, "next": None, "previous": None, "results": []},
        )
        fetch_all_weekly_records()
        last = requests_mock.last_request
        assert last.qs["age"] == ["all"]
        assert last.qs["sex"] == ["all"]
        assert last.qs["stratum"] == ["default"]
