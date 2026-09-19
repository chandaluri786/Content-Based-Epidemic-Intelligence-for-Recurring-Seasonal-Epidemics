"""Cheap, targeted check: real full-day (96-stamp) pre-term-filter candidate
volume for IND, deduped by URL, to ground a title/body-fetch cost estimate
for IND specifically (not extrapolated from a single 15-min-stamp snapshot).
Throwaway investigation script.
"""

import io
import sys
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.gdelt.raw_downloader import download_zip_bytes, fifteen_min_stamps

DATE_STR = "20230115"  # within IND's 2023 season window (onset 2023-01-23)
IND_FIPS = "IN"


def fetch_and_count(stamp: str) -> tuple[str, set[str]]:
    try:
        raw = download_zip_bytes(stamp)
    except Exception as exc:  # noqa: BLE001
        print(f"  {stamp}: FAILED {exc}", file=sys.stderr)
        return stamp, set()
    urls = set()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = zf.namelist()[0]
        with zf.open(name) as f:
            for line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
                fields = line.rstrip("\n").split("\t")
                if len(fields) <= 10:
                    continue
                url = fields[4]
                loc = fields[10]
                codes = set()
                for part in loc.split(";"):
                    sub = part.split("#")
                    if len(sub) > 2 and sub[2].strip():
                        codes.add(sub[2].strip())
                if IND_FIPS in codes:
                    urls.add(url)
    del raw
    return stamp, urls


def main() -> None:
    stamps = fifteen_min_stamps(DATE_STR)
    print(f"Downloading {len(stamps)} stamps for {DATE_STR} at 8x concurrency...")
    all_urls: set[str] = set()
    per_stamp_counts = Counter()
    with ThreadPoolExecutor(max_workers=8) as executor:
        for stamp, urls in executor.map(fetch_and_count, stamps):
            all_urls.update(urls)
            per_stamp_counts[stamp] = len(urls)

    print(f"\nTotal raw (non-deduped) IN-tagged mentions across 96 stamps: {sum(per_stamp_counts.values())}")
    print(f"Unique IN-tagged URLs for the day (deduped): {len(all_urls)}")

    domains = Counter(urlparse(u).netloc.lower().replace("www.", "") for u in all_urls)
    print(f"Distinct domains: {len(domains)}")
    print("Top 10 domains:")
    for d, c in domains.most_common(10):
        print(f"  {c:4d}  {d}")

    out_path = Path(__file__).resolve().parent / "spike_ind_daily_volume_urls.txt"
    out_path.write_text("\n".join(sorted(all_urls)))
    print(f"\nWrote {len(all_urls)} URLs to {out_path}")


if __name__ == "__main__":
    main()
