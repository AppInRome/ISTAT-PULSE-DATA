#!/usr/bin/env python3
"""Rebuild standalone PULSE historical longform reader with interactive source charts.

Never calls an LLM. Reads existing primary-source reviewed articles, checks
that all official chart/table observations agree, and preserves full prose.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


START = '<script type="application/json" id="feed">'
END = '</script>'


def build_payload(source):
    if source.get("schema") != "pulse-automatic-official-features-v1":
        raise ValueError("wrong_official_feed_schema")
    stories = []
    for a in source.get("articles", []):
        review = a.get("automatic_review") or {}
        series = a.get("verified_series_relevant") or []
        body = [x.get("text", "") for x in a.get("pulse_article_body") or []]
        lead = str(a.get("summary") or "")
        words = len((" ".join([lead, *body])).split())
        if not (review.get("passed") is True and review.get("model_used") is False
                and a.get("publication_status") == "published"
                and a.get("editorial_format") == "deterministic_source_locked_auto_audited"
                and a.get("chart_spec", {}).get("status") == "verified"
                and a.get("table_spec", {}).get("status") == "verified"
                and 250 <= words <= 500 and len(body) >= 4 and len(series) == 1):
            raise ValueError("unverified_or_incomplete_story:" + str(a.get("id")))
        points = series[0].get("observations") or []
        chart = (a.get("chart_spec") or {}).get("data") or []
        table = (a.get("table_spec") or {}).get("rows") or []
        if not 2 <= len(points) == len(chart) == len(table) <= 24:
            raise ValueError("not_one_to_one_source_chart_table:" + a["id"])
        for p, c, t in zip(points, chart, table):
            if not (str(p["period"]) == str(c["period"]) == str(t[0])
                    and float(p["value"]) == float(c["value"]) == float(t[1])):
                raise ValueError("numeric_mismatch:" + a["id"])
        stories.append({
            "id": a["id"], "topic": a["topic"], "title": a["headline"],
            "lead": lead, "paragraphs": body,
            "source": a["public_source"]["url"], "period": a["period_reference"],
            "indicator": series[0]["indicator"], "unit": series[0]["unit"],
            "data": [{"period": o["period"], "value": o["value"], "raw": o.get("raw", "")}
                     for o in points]
        })
    return {"generated_at": source.get("generated_at") or "", "articles": stories}


def regenerate(feed_path, html_path):
    feed = json.loads(Path(feed_path).read_text(encoding="utf-8"))
    payload = build_payload(feed)
    target = Path(html_path)
    content = target.read_text(encoding="utf-8")
    start = content.index(START) + len(START)
    end = content.index(END, start)
    document = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # JSON lives inside an HTML script element; protect against premature ending.
    document = document.replace("<", r"\u003c").replace("&", r"\u0026")
    updated = content[:start] + document + content[end:]
    if updated != content:
        target.write_text(updated, encoding="utf-8")
    return len(payload["articles"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default="data/news/automatic_features.json")
    ap.add_argument("--output", default="docs/PULSE_STORICO_INTERATTIVO.html")
    args = ap.parse_args()
    print("PULSE historical verified interactive articles:", regenerate(args.feed, args.output))


if __name__ == "__main__":
    main()
