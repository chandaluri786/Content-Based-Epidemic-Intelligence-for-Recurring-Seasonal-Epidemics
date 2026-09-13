"""UKHSA England dashboard client.

No prior spike script exists for this source (unlike FluNet) -- the saved
investigation/ukhsa_flu_results.json was already flattened to age=all/sex=all/
stratum=default, hiding that the live endpoint actually returns per-age-band
rows by default and must be explicitly filtered. Confirmed live: the
{age=all, sex=all, stratum=default} filter reproduces the exact 479-record
count in that saved JSON.
"""

from typing import Any

from pipeline.common.http import get_with_retry
from pipeline.config import (
    UKHSA_API_BASE,
    UKHSA_GEOGRAPHY,
    UKHSA_METRIC,
    UKHSA_PAGE_SIZE,
    UKHSA_TOPIC,
)

UKHSA_ENDPOINT_URL = (
    f"{UKHSA_API_BASE}/themes/infectious_disease/sub_themes/respiratory"
    f"/topics/{UKHSA_TOPIC}/geography_types/Nation/geographies/{UKHSA_GEOGRAPHY}"
    f"/metrics/{UKHSA_METRIC}"
)


def fetch_all_weekly_records(page_size: int = UKHSA_PAGE_SIZE) -> list[dict[str, Any]]:
    """Fetch every weekly England test-positivity record, following the `next`
    pagination link until it is null."""
    url: str | None = UKHSA_ENDPOINT_URL
    params: dict[str, Any] | None = {
        "page_size": page_size,
        "age": "all",
        "sex": "all",
        "stratum": "default",
    }

    all_results: list[dict[str, Any]] = []
    while url:
        response = get_with_retry(url, params=params)
        data = response.json()
        all_results.extend(data["results"])
        url = data.get("next")
        params = None  # `next` already carries the full query string

    return all_results
