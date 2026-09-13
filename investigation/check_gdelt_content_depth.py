"""
Checkpoint 3: GDELT content depth + full-text retrievability for Brazil dengue coverage.

Uses GDELT's free DOC 2.0 API (no GCP/billing needed) to find candidate articles,
then attempts to fetch and inspect each article's full text for extractable content
beyond the bare word "dengue".

Sampling frame (fixed before inspecting results): a stratified set of (state/city, season)
cells drawn from the InfoDengue onset results (large-metro vs mid/small-metro tier,
severe year 2019 vs a more typical year 2023).
"""
import json
import time
import urllib.request
import urllib.error
from html.parser import HTMLParser

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
MIN_SECONDS_BETWEEN_CALLS = 8

SAMPLE_CELLS = [
    # (query terms, start, end, label)
    ("dengue Sao Paulo", "20190201000000", "20190531000000", "SaoPaulo_2019_severe"),
    ("dengue Sao Paulo", "20230201000000", "20230531000000", "SaoPaulo_2023_typical"),
    ("dengue Rio de Janeiro", "20190201000000", "20190531000000", "RioDeJaneiro_2019_severe"),
    ("dengue Belem", "20190201000000", "20190531000000", "Belem_2019_severe"),
    ("dengue Manaus", "20190201000000", "20190531000000", "Manaus_2019_severe"),
    ("dengue Goiania", "20190201000000", "20190531000000", "Goiania_2019_severe"),
]

CONTENT_MARKERS = [
    "caso", "cases", "óbito", "morte", "death", "sorotipo", "serotype",
    "hospital", "internação", "sintoma", "symptom", "epidemia", "surto",
    "outbreak", "alerta", "gravé", "grave", "severe",
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


def gdelt_query(query: str, start: str, end: str, maxrecords: int = 20) -> list[dict]:
    url = (
        f"{DOC_API}?query={urllib.parse.quote(query)}&mode=artlist"
        f"&maxrecords={maxrecords}&startdatetime={start}&enddatetime={end}&format=json"
    )
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": "fse570-feasibility-spike"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                return data.get("articles", [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = MIN_SECONDS_BETWEEN_CALLS * (attempt + 2)
                print(f"    rate limited, backing off {wait}s...")
                time.sleep(wait)
                continue
            print(f"    HTTP error: {e}")
            return []
        except Exception as e:
            print(f"    query failed: {e}")
            return []
    return []


def fetch_article_text(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 fse570-feasibility-spike"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None
    parser = TextExtractor()
    try:
        parser.feed(raw)
    except Exception:
        return None
    return parser.text()


def score_content_depth(text: str) -> int:
    lowered = text.lower()
    return sum(1 for marker in CONTENT_MARKERS if marker in lowered)


def main():
    import urllib.parse as _up
    global urllib
    urllib.parse = _up

    all_results = {}
    for query, start, end, label in SAMPLE_CELLS:
        print(f"\n=== {label} :: query='{query}' {start[:8]}-{end[:8]} ===")
        articles = gdelt_query(query, start, end, maxrecords=10)
        time.sleep(MIN_SECONDS_BETWEEN_CALLS)
        print(f"  articles found: {len(articles)}")
        cell_result = {"query": query, "window": f"{start[:8]}-{end[:8]}", "n_found": len(articles), "articles": []}
        for art in articles[:5]:
            url = art.get("url")
            text = fetch_article_text(url) if url else None
            retrievable = bool(text and len(text.strip()) > 200)
            depth_score = score_content_depth(text) if text else 0
            cell_result["articles"].append({
                "url": url,
                "domain": art.get("domain"),
                "language": art.get("language"),
                "sourcecountry": art.get("sourcecountry"),
                "retrievable": retrievable,
                "text_len": len(text) if text else 0,
                "content_marker_hits": depth_score,
            })
            print(f"    {url[:80]} | retrievable={retrievable} | markers={depth_score}")
        all_results[label] = cell_result

    out_path = "/Users/aditya.rallapalli/Code/projects/capstone-project/investigation/gdelt_content_depth_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    total_found = sum(r["n_found"] for r in all_results.values())
    total_sampled = sum(len(r["articles"]) for r in all_results.values())
    total_retrievable = sum(1 for r in all_results.values() for a in r["articles"] if a["retrievable"])
    total_content_rich = sum(1 for r in all_results.values() for a in r["articles"] if a["content_marker_hits"] >= 1)

    print("\n=== CHECKPOINT 3 SUMMARY (pilot sample, not yet the full N=50) ===")
    print(f"Cells queried: {len(SAMPLE_CELLS)}")
    print(f"Total articles found by GDELT DOC search: {total_found}")
    print(f"Articles actually sampled/fetched: {total_sampled}")
    if total_sampled:
        print(f"Retrievable (full text obtained): {total_retrievable}/{total_sampled} "
              f"({100*total_retrievable/total_sampled:.0f}%)")
        print(f"Content-marker-rich (>=1 marker beyond 'dengue'): {total_content_rich}/{total_sampled} "
              f"({100*total_content_rich/total_sampled:.0f}%)")
    print(f"Results written to {out_path}")


if __name__ == "__main__":
    main()
