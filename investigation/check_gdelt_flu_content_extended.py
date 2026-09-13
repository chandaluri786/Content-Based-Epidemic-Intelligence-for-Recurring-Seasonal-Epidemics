"""
Follow-up item 2: extend Brazil/Indonesia flu content-depth from 1 day each to 5
stratified days each, mirroring the dengue resolution check's 2-day-to-5-day escalation
(a 1-2 day sample previously gave a misleading result there before a 5-day check reversed it).

Sample is fixed before running: 5 years spread evenly across the 2015-2024 decade
(2015, 2017, 2019, 2021, 2023), using each country's own real FluNet onset week for that
year -- not cherry-picked after seeing which days have more news.

Reuses check_gdelt_flu_content_raw.py's architecture: raw GDELT GKG 15-minute files,
in-memory zip parsing (no disk extraction), and the already-fixed word-boundary regex
for "flu"/"influenza" (naive substring matching false-positived on "fluid", "influencer", etc.
in the original pilot).
"""
import io
import json
import re
import shutil
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser

GDELT_BASE = "https://data.gdeltproject.org/gdeltv2"
MIN_FREE_GB = 5

# (country_display_name, [(year, date YYYYMMDD), ...] -- resolved from real FluNet onset weeks)
TARGETS = [
    ("Brazil", [
        ("2015", "20150302"),
        ("2017", "20170123"),
        ("2019", "20181231"),
        ("2021", "20211213"),
        ("2023", "20230313"),
    ]),
    ("Indonesia", [
        ("2015", "20150105"),
        ("2017", "20170102"),
        ("2019", "20181231"),
        ("2021", "20210510"),
        ("2023", "20230116"),
    ]),
]

FLU_TERM_RE = re.compile(r"(?:^|[-_/])(flu|influenza)(?:[-_/]|$)", re.IGNORECASE)


def url_matches_flu_term(url: str) -> bool:
    return bool(FLU_TERM_RE.search(url))


CONTENT_MARKERS = [
    "case", "cases", "hospitaliz", "death", "outbreak", "epidemic", "strain",
    "h1n1", "h3n2", "influenza b", "surge", "vaccine", "severe",
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


def fifteen_min_stamps(date_str):
    for h in range(24):
        for m in (0, 15, 30, 45):
            yield f"{date_str}{h:02d}{m:02d}00"


def download_zip_bytes(stamp):
    url = f"{GDELT_BASE}/{stamp}.gkg.csv.zip"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fse570-feasibility-spike"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception:
        return None


def iter_records_from_zip_bytes(raw_zip):
    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as f:
                for line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
                    yield line
    except Exception:
        return


def fetch_text(url):
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


def score(text):
    low = text.lower()
    return sum(1 for m in CONTENT_MARKERS if m in low)


def process_country_day(country_name, date_str):
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
            del raw
    return {"files_ok": files_ok, "files_failed": files_failed, "matched_urls": matched_urls}


def main():
    free = free_gb()
    print(f"Free disk space before starting: {free:.1f} GB")
    if free < MIN_FREE_GB:
        print(f"ABORTING: free space below {MIN_FREE_GB}GB safety threshold.")
        return

    all_results = {}
    for country_name, year_dates in TARGETS:
        country_days = {}
        for year, date_str in year_dates:
            print(f"\n=== {country_name} :: {year} ({date_str}) ===")
            day_result = process_country_day(country_name, date_str)
            print(f"  15-min files read: {day_result['files_ok']} ok, {day_result['files_failed']} failed")
            print(f"  matched URLs: {len(day_result['matched_urls'])}")

            articles = []
            for url in day_result["matched_urls"][:10]:
                text = fetch_text(url)
                retrievable = bool(text and len(text.strip()) > 200)
                depth = score(text) if text else 0
                articles.append({"url": url, "retrievable": retrievable, "content_marker_hits": depth})
                print(f"    {url[:90]} | retrievable={retrievable} | markers={depth}")

            country_days[year] = {
                "date": date_str,
                "files_ok": day_result["files_ok"],
                "n_matched_urls": len(day_result["matched_urls"]),
                "articles_sampled": articles,
            }
            print(f"  free disk space now: {free_gb():.1f} GB")
        all_results[country_name] = country_days

    out_path = "/Users/aditya.rallapalli/Code/projects/capstone-project/investigation/gdelt_flu_content_extended_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print("\n=== ITEM 2 SUMMARY: Brazil/Indonesia, 5 days each ===")
    grand_sampled, grand_retrievable, grand_rich = 0, 0, 0
    for country_name, country_days in all_results.items():
        sampled = sum(len(d["articles_sampled"]) for d in country_days.values())
        retrievable = sum(1 for d in country_days.values() for a in d["articles_sampled"] if a["retrievable"])
        rich = sum(1 for d in country_days.values() for a in d["articles_sampled"] if a["content_marker_hits"] >= 1)
        grand_sampled += sampled
        grand_retrievable += retrievable
        grand_rich += rich
        if sampled:
            print(f"{country_name}: {sampled} sampled, {retrievable}/{sampled} retrievable "
                  f"({100*retrievable/sampled:.0f}%), {rich}/{sampled} content-rich ({100*rich/sampled:.0f}%)")
        else:
            print(f"{country_name}: 0 articles matched across all 5 days")

    print(f"\nCombined: {grand_sampled} sampled", end="")
    if grand_sampled:
        print(f", {grand_retrievable}/{grand_sampled} retrievable ({100*grand_retrievable/grand_sampled:.0f}%, threshold >=60%)"
              f", {grand_rich}/{grand_sampled} content-rich ({100*grand_rich/grand_sampled:.0f}%, threshold >=50%)")
    print(f"Results written to {out_path}")


if __name__ == "__main__":
    main()
