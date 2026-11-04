import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

SCHOLAR_ID = "b-MGt8gAAAAJ"
PROFILE_URL = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=zh-CN"
PAGE_SIZE = 100
METRICS = ("citations", "h_index", "i10_index")


def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    profile = soup.select_one("#gsc_prf_in")
    cells = soup.select("#gsc_rsb_st .gsc_rsb_std")
    more = soup.select_one("#gsc_bpf_more")
    if profile is None or len(cells) != 6 or more is None:
        raise ValueError("Scholar profile is unavailable or its page structure has changed")

    metrics = {}
    for key, cell in zip(METRICS, cells[::2]):
        value = re.sub(r"[,\s\u00a0\u202f]", "", cell.get_text())
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError(f"Invalid Scholar metric: {key}")
        metrics[key] = int(value)

    publication_ids = []
    rows = soup.select("#gsc_a_b .gsc_a_tr")
    for row in rows:
        link = row.select_one(".gsc_a_at")
        if link is None:
            raise ValueError("Missing publication link")
        query = parse_qs(urlparse(link.get("href", "")).query)
        publication_id = query.get("citation_for_view", [""])[0]
        if not publication_id.startswith(f"{SCHOLAR_ID}:"):
            raise ValueError("Unexpected publication profile")
        publication_ids.append(publication_id)

    if not rows:
        raise ValueError("No publications found; refusing to replace the saved snapshot")
    return metrics, publication_ids, not more.has_attr("disabled")


def fetch_page(start):
    query = urlencode({"user": SCHOLAR_ID, "hl": "en", "cstart": start, "pagesize": PAGE_SIZE})
    request = Request(
        f"https://scholar.google.com/citations?{query}",
        headers={"User-Agent": "PersonalHomepageScholarSync/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8")


def collect_metrics(fetch=fetch_page):
    publication_ids = set()
    totals = None
    for start in range(0, 1000, PAGE_SIZE):
        metrics, page_ids, has_more = parse_page(fetch(start))
        if totals is None:
            totals = metrics
        if len(set(page_ids)) != len(page_ids) or publication_ids.intersection(page_ids):
            raise ValueError("Repeated publications in Scholar pagination")
        publication_ids.update(page_ids)
        if not has_more:
            return {
                "scholar_id": SCHOLAR_ID,
                "source_url": PROFILE_URL,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "metrics": {"publications": len(publication_ids), **totals},
            }
        if len(page_ids) != PAGE_SIZE:
            raise ValueError("Incomplete Scholar publication page")
    raise ValueError("Scholar pagination did not finish")


def update_snapshot(output, fetch=fetch_page):
    snapshot = collect_metrics(fetch)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    return snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/scholar.json"))
    args = parser.parse_args()
    try:
        snapshot = update_snapshot(args.output)
    except Exception as error:
        print(f"Scholar update failed; existing snapshot was not changed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(snapshot["metrics"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
