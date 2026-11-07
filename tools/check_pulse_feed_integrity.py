#!/usr/bin/env python3
"""Check PULSE published route consistency without changing any production data."""
import json
import sys
import urllib.request
from datetime import datetime, timezone

BASE = "https://raw.githubusercontent.com/AppInRome/ISTAT-PULSE-DATA/main/"
FILES = {
    "routes": "data/live_data_index.json",
    "news": "data/news/index.json",
    "territori": "data/news/territori_index.json",
    "green": "data/news/green_index.json",
    "refresh": "data/refresh_status.json",
    "observer": "data/observer_refresh_status.json",
    "articles": "data/news/articles.json",
}
def read(path):
    request = urllib.request.Request(BASE + path + "?pulse_check=1", headers={"User-Agent": "PULSE-feed-integrity/1.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)

def article_ids(archive):
    rows = archive.get("articles", [])
    if isinstance(rows, dict):
        rows = list(rows.values())
    return {str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")}

def check(index, known, label):
    missing = []
    for period in ("oggi", "ieri", "archivio"):
        values = index.get(period, [])
        if not isinstance(values, list):
            raise ValueError(f"{label}.{period} is not a list")
        missing.extend(v for v in values if str(v) not in known)
    counts = {p: len(index.get(p, [])) for p in ("oggi", "ieri", "archivio")}
    print(f"{label}: {counts} generated_at={index.get('generated_at')} missing_ids={len(missing)}")
    if missing:
        print("Missing article IDs:", missing[:10], file=sys.stderr)
    return not missing

def main():
    data = {name: read(path) for name, path in FILES.items()}
    routes = data["routes"]
    expected = routes.get("notizie", {})
    for key in ("articles", "index", "green_index", "territori_index"):
        if not expected.get(key):
            raise ValueError(f"missing route notizie.{key}")
    if expected["articles"] != FILES["articles"]:
        raise ValueError("article path differs from published route manifest")
    if expected["index"] != FILES["news"]:
        raise ValueError("main news path differs from published route manifest")
    known = article_ids(data["articles"])
    if not known:
        raise ValueError("articles.json has no readable IDs")
    ok = all(check(data[label], known, label) for label in ("news", "territori", "green"))
    for label in ("refresh", "observer"):
        print(label, json.dumps(data[label], ensure_ascii=False)[:400])
    now = datetime.now(timezone.utc)
    print("UTC check:", now.isoformat())
    return 0 if ok else 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("PULSE FEED CHECK FAILED:", exc, file=sys.stderr)
        sys.exit(1)
