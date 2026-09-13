"""WHO FluNet (xMart VIW_FNT) client.

Ports the query pattern validated in investigation/check_flunet_access.py,
adding $skip pagination: a country-year can return more than one row per week
(strain-subtype breakdown), so >page_size rows is plausible at full scale even
though the original spike's $top=100 never needed a second page in practice.
"""

import csv
import io

from pipeline.common.http import get_with_retry
from pipeline.config import FLUNET_API_URL, FLUNET_PAGE_SIZE, FLUNET_USER_AGENT


def fetch_country_year_records(
    iso3: str, year: int, page_size: int = FLUNET_PAGE_SIZE
) -> list[dict[str, str]]:
    """Fetch every FluNet weekly record for a country-year, following $skip
    pagination until a page shorter than page_size is returned."""
    all_rows: list[dict[str, str]] = []
    skip = 0

    while True:
        params = {
            "$format": "csv",
            "$filter": f"COUNTRY_CODE eq '{iso3}' and ISO_YEAR eq {year}",
            "$top": page_size,
            "$skip": skip,
        }
        response = get_with_retry(
            FLUNET_API_URL,
            params=params,
            headers={"User-Agent": FLUNET_USER_AGENT},
        )
        page_rows = list(csv.DictReader(io.StringIO(response.text)))
        all_rows.extend(page_rows)

        if len(page_rows) < page_size:
            break
        skip += page_size

    return all_rows
