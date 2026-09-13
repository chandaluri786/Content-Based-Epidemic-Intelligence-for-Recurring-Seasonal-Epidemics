"""
Flu fallback Checkpoint 3: GDELT content-depth pilot for influenza coverage,
across the same income/hemisphere-stratified countries checked in FluNet.
"""
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
BACKOFF_BASE = 15

QUERIES = [
    ("influenza sourcecountry:unitedstates", "20231201000000", "20240115000000", "USA_2023w50"),
    ("influenza sourcecountry:kenya", "20230301000000", "20230401000000", "Kenya_2023w10"),
    ("influenza sourcecountry:india", "20230115000000", "20230215000000", "India_2023w04"),
    ("influenza sourcecountry:indonesia", "20230101000000", "20230201000000", "Indonesia_2023w03"),
]

CONTENT_MARKERS = [
    "case", "cases", "hospitaliz", "death", "outbreak", "epidemic", "strain",
    "h1n1", "h3n2", "influenza b", "surge", "vaccine", "severe", "who",
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


def gdelt_query(query, start, end, maxrecords=10):
    params = {
        "query": query, "mode": "artlist", "maxrecords": maxrecords,
        "startdatetime": start, "enddatetime": end, "format": "json",
    }
    url = f"{DOC_API}?{urllib.parse.urlencode(params)}"
    for attempt in range(5):
        req = urllib.request.Request(url, headers={"User-Agent": "fse570-feasibility-spike"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read()).get("articles", [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = BACKOFF_BASE * (attempt + 1)
                print(f"    rate limited, backing off {wait}s...")
                time.sleep(wait)
                continue
            print(f"    HTTP error: {e}")
            return []
        except Exception as e:
            print(f"    query failed: {e}")
            return []
    return []


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


def main():
    all_results = {}
    for query, start, end, label in QUERIES:
        print(f"\n=== {label} :: '{query}' ===")
        articles = gdelt_query(query, start, end)
        time.sleep(BACKOFF_BASE)
        print(f"  articles found: {len(articles)}")
        cell = {"query": query, "n_found": len(articles), "articles": []}
        for art in articles[:5]:
            url = art.get("url")
            text = fetch_text(url) if url else None
            retrievable = bool(text and len(text.strip()) > 200)
            depth = score(text) if text else 0
            cell["articles"].append({
                "url": url, "domain": art.get("domain"), "language": art.get("language"),
                "retrievable": retrievable, "content_marker_hits": depth,
            })
            print(f"    {url[:80]} | retrievable={retrievable} | markers={depth}")
        all_results[label] = cell

    out_path = "/Users/aditya.rallapalli/Code/projects/capstone-project/investigation/gdelt_flu_content_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    total_sampled = sum(len(r["articles"]) for r in all_results.values())
    total_retrievable = sum(1 for r in all_results.values() for a in r["articles"] if a["retrievable"])
    total_rich = sum(1 for r in all_results.values() for a in r["articles"] if a["content_marker_hits"] >= 1)
    print("\n=== FLU CHECKPOINT 3 PILOT SUMMARY ===")
    print(f"Total found: {sum(r['n_found'] for r in all_results.values())}")
    print(f"Sampled: {total_sampled}")
    if total_sampled:
        print(f"Retrievable: {total_retrievable}/{total_sampled} ({100*total_retrievable/total_sampled:.0f}%)")
        print(f"Content-rich: {total_rich}/{total_sampled} ({100*total_rich/total_sampled:.0f}%)")
    print(f"Results written to {out_path}")


if __name__ == "__main__":
    main()
