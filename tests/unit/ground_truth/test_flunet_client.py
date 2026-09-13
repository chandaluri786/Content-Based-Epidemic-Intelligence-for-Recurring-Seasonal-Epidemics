import pytest

from pipeline.ground_truth.flunet_client import fetch_country_year_records


@pytest.mark.unit
class TestFetchCountryYearRecords:
    def test_single_page_under_page_size_returns_all_rows(self, requests_mock):
        csv_body = (
            "COUNTRY_CODE,ISO_YEAR,ISO_WEEK,SPEC_PROCESSED_NB,INF_ALL\n"
            "USA,2023,1,100,5\n"
            "USA,2023,2,100,12\n"
        )
        requests_mock.get(
            "https://xmart-api-public.who.int/FLUMART/VIW_FNT",
            text=csv_body,
        )
        records = fetch_country_year_records("USA", 2023, page_size=100)
        assert len(records) == 2
        assert records[0]["ISO_WEEK"] == "1"

    def test_paginates_when_a_full_page_is_returned(self, requests_mock):
        page_1_rows = "\n".join(f"USA,2023,{w},100,5" for w in range(1, 4))
        page_2_rows = "\n".join(f"USA,2023,{w},100,5" for w in range(4, 6))
        header = "COUNTRY_CODE,ISO_YEAR,ISO_WEEK,SPEC_PROCESSED_NB,INF_ALL"
        requests_mock.get(
            "https://xmart-api-public.who.int/FLUMART/VIW_FNT",
            [
                {"text": f"{header}\n{page_1_rows}\n"},
                {"text": f"{header}\n{page_2_rows}\n"},
            ],
        )
        records = fetch_country_year_records("USA", 2023, page_size=3)
        assert len(records) == 5
        assert requests_mock.call_count == 2

    def test_empty_response_returns_empty_list(self, requests_mock):
        requests_mock.get(
            "https://xmart-api-public.who.int/FLUMART/VIW_FNT",
            text="COUNTRY_CODE,ISO_YEAR,ISO_WEEK,SPEC_PROCESSED_NB,INF_ALL\n",
        )
        assert fetch_country_year_records("USA", 2023, page_size=100) == []

    def test_request_uses_expected_filter_params(self, requests_mock):
        requests_mock.get(
            "https://xmart-api-public.who.int/FLUMART/VIW_FNT",
            text="COUNTRY_CODE,ISO_YEAR,ISO_WEEK,SPEC_PROCESSED_NB,INF_ALL\n",
        )
        fetch_country_year_records("KEN", 2019, page_size=100)
        last = requests_mock.last_request
        assert last.qs["$filter"] == ["country_code eq 'ken' and iso_year eq 2019"]
        assert last.qs["$top"] == ["100"]
        assert last.qs["$skip"] == ["0"]
