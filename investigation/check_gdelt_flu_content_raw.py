"""
Flu Checkpoint 3 completion: content depth + retrievability for the 6 countries not yet
cleanly tested (USA, GBR, JPN, AUS, BRA, IDN), using the raw GDELT GKG 2.0 15-minute file
mirror instead of the rate-limited DOC 2.0 API (same method used for the dengue resolution
check, extended here to also fetch full article text).

Disk-safety: each 15-minute .zip is read into memory (zipfile + io.BytesIO) and discarded
immediately after parsing -- nothing is extracted to disk. The dengue check filled /private/tmp
to 100% by extracting multiple full days at once; this script processes one country-day at a
time and never accumulates a multi-GB footprint.
"""
import io
import json
import re
import shutil
import time
import urllib.request
import urllib.error
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser

GDELT_BASE = "https://data.gdeltproject.org/gdeltv2"
MIN_FREE_GB = 5  # abort rather than risk a repeat of the full-disk incident

# (country_display_name, representative_date YYYYMMDD, note)
TARGETS = [
    ("United States", "20231211", None),
    ("United Kingdom", "20230116", "No WHO FluNet data exists for GBR in any year checked (2018-2023) -- date is a generic NH winter week, not a verified onset."),
    ("Japan", "20231127", "Peak INF_ALL week (FluNet reports no SPEC_PROCESSED_NB for Japan, so no percent-positive onset could be computed)."),
    ("Australia", "20230605", None),
    ("Brazil", "20230313", None),
    ("Indonesia", "20230116", None),
]

# Word-boundary match on "flu" or "influenza" -- a naive substring match on "flu" was
# found to false-positive on "fluid", "hydrofluoric", "fluorspar", "influencer",
# "influence", "flutter", etc. This regex requires "flu"/"influenza" as its own token
# (hyphen/slash/underscore/start/end delimited), which excludes all of those.
FLU_TERM_RE = re.compile(r"(?:^|[-_/])(flu|influenza)(?:[-_/]|$)", re.IGNORECASE)


def url_matches_flu_term(url: str) -> bool:
    return bool(FLU_TERM_RE.search(url))

CONTENT_MARKERS = [
    "case", "cases", "hospitaliz", "death", "outbreak", "epidemic", "strain",
    "h1n1", "h3n2", "influenza b", "surge", "vaccine", "severe",
    # "who" (bare) dropped: it's a common English word (matches "who said", "index of who"...)
    # and false-positived constantly in the pilot run; "world health organization" is the
    # specific, non-generic form of the same signal.
    "world health organization",
]


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chunks = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self.chunks.append(data)

    def text(self):
        return " ".join(self.chunks)


def free_gb(path="/private/tmp"):
    total, used, free = shutil.disk_usage(path)
    return free / (1024 ** 3)


def fifteen_min_stamps(date_str: str):
    for h in range(24):
        for m in (0, 15, 30, 45):
            yield f"{date_str}{h:02d}{m:02d}00"


def download_zip_bytes(stamp: str) -> bytes | None:
    url = f"{GDELT_BASE}/{stamp}.gkg.csv.zip"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fse570-feasibility-spike"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception:
        return None


def iter_records_from_zip_bytes(raw_zip: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as f:
                for line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
                    yield line
    except Exception:
        return


def fetch_text(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 fse570-feasibility-spike"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    p = TextExtractor()
    try:
        p.feed(raw)
    except Exception:
        return None
    return p.text()


def score(text: str) -> int:
    low = text.lower()
    return sum(1 for m in CONTENT_MARKERS if m in low)


def process_country_day(country_name: str, date_str: str) -> dict:
    matched_urls = []
    files_ok, files_failed = 0, 0
    stamps = list(fifteen_min_stamps(date_str))
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(download_zip_bytes, s): s for s in stamps}
        for fut in as_completed(futures):
            raw = fut.result()
            if raw is None:
                files_failed += 1
                continue
            files_ok += 1
            for line in iter_records_from_zip_bytes(raw):
                parts = line.split("\t")
                if len(parts) < 11:
                    continue
                url = parts[4]
                if not url_matches_flu_term(url):
                    continue
                locations = parts[10]
                if country_name.lower() not in locations.lower():
                    continue
                matched_urls.append(url)
            del raw  # explicit: nothing from this file persists past this iteration
    return {"files_ok": files_ok, "files_failed": files_failed, "matched_urls": matched_urls}


def main():
    free = free_gb()
    print(f"Free disk space before starting: {free:.1f} GB")
    if free < MIN_FREE_GB:
        print(f"ABORTING: free space below {MIN_FREE_GB}GB safety threshold. No downloads started.")
        return

    all_results = {}
    for country_name, date_str, note in TARGETS:
        print(f"\n=== {country_name} :: {date_str} ===")
        if note:
            print(f"  NOTE: {note}")
        day_result = process_country_day(country_name, date_str)
        print(f"  15-min files read: {day_result['files_ok']} ok, {day_result['files_failed']} failed")
        print(f"  matched URLs (flu-term + {country_name} location tag): {len(day_result['matched_urls'])}")

        articles = []
        for url in day_result["matched_urls"][:10]:
            text = fetch_text(url)
            retrievable = bool(text and len(text.strip()) > 200)
            depth = score(text) if text else 0
            articles.append({"url": url, "retrievable": retrievable, "content_marker_hits": depth})
            print(f"    {url[:90]} | retrievable={retrievable} | markers={depth}")

        all_results[country_name] = {
            "date": date_str, "note": note,
            "files_ok": day_result["files_ok"], "files_failed": day_result["files_failed"],
            "n_matched_urls": len(day_result["matched_urls"]),
            "articles_sampled": articles,
        }
        print(f"  free disk space now: {free_gb():.1f} GB")

    out_path = "/Users/aditya.rallapalli/Code/projects/capstone-project/investigation/gdelt_flu_content_raw_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    total_sampled = sum(len(r["articles_sampled"]) for r in all_results.values())
    total_retrievable = sum(1 for r in all_results.values() for a in r["articles_sampled"] if a["retrievable"])
    total_rich = sum(1 for r in all_results.values() for a in r["articles_sampled"] if a["content_marker_hits"] >= 1)
    print("\n=== RAW-FILE CHECKPOINT 3 SUMMARY (6 new countries) ===")
    print(f"Total articles sampled: {total_sampled}")
    if total_sampled:
        print(f"Retrievable: {total_retrievable}/{total_sampled} ({100*total_retrievable/total_sampled:.0f}%) -- threshold >=60%")
        print(f"Content-rich: {total_rich}/{total_sampled} ({100*total_rich/total_sampled:.0f}%) -- threshold >=50%")
    else:
        print("No articles matched at all -- see per-country n_matched_urls above.")
    print(f"Results written to {out_path}")


if __name__ == "__main__":
    main()
