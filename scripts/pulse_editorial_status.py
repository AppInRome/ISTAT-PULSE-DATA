#!/usr/bin/env python3
"""Auditable daily PULSE check, independent from the last published article date.

Never modifies existing articles or their original publication timestamps.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path


SCHEMA = "pulse-editorial-refresh-status-v1"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def instant(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def latest_published_at(articles):
    """Use first publication of the PULSE article, not any feed check timestamp."""
    times = []
    for item in articles:
        if not isinstance(item, dict) or item.get("publication_status") != "published":
            continue
        published = instant(item.get("first_published_at_utc") or item.get("published_at"))
        if published is not None:
            times.append(published)
    return max(times).isoformat().replace("+00:00", "Z") if times else None


def make_status(feed, frontpage, report, pipeline, checked_at):
    articles = feed.get("articles")
    if not isinstance(articles, list):
        raise ValueError("published_feed_invalid")
    decisions = report.get("candidate_decisions", [])
    if not isinstance(decisions, list):
        raise ValueError("candidate_decisions_invalid")
    new_ids = report.get("published_article_ids", [])
    if not isinstance(new_ids, list) or len(new_ids) != report.get("published_new"):
        raise ValueError("publication_count_mismatch")
    published_ids = {a.get("id") for a in articles if isinstance(a, dict)}
    if any(i not in published_ids for i in new_ids):
        raise ValueError("published_article_not_in_feed")
    if instant(checked_at) is None:
        raise ValueError("invalid_check_timestamp")
    discovery = (pipeline.get("official_discovery") or {})
    considered = discovery.get("sources_considered") or []
    if not isinstance(considered, list):
        considered = []
    unavailable = [{
        "source": str(x.get("provider") or x.get("source") or "sconosciuta")[:80],
        "status": str(x.get("status") or "")[:80],
    } for x in considered if isinstance(x, dict) and
        x.get("status") not in ("source_series_found", "ok", "verified")]
    novelty = Counter(str(x.get("novelty") or "unknown") for x in decisions if isinstance(x, dict))
    outcomes = Counter(str(x.get("decision") or "unknown") for x in decisions if isinstance(x, dict))
    tiers = Counter(str(x.get("tier") or "unknown") for x in decisions if isinstance(x, dict))
    return {
        "schema": SCHEMA,
        "last_editorial_check_at": checked_at,
        "last_published_article_at": latest_published_at(articles),
        "published_articles_total": len(articles),
        "published_new_in_last_check": report["published_new"],
        "verified_candidate_dossiers": len(decisions),
        "research_checked": report.get("research_checked", 0),
        "research_rejected": report.get("rejected", 0),
        "rejection_reasons": report.get("rejected_reasons") or {},
        "novelty_counts": dict(sorted(novelty.items())),
        "selection_counts": dict(sorted(outcomes.items())),
        "editorial_tiers": dict(sorted(tiers.items())),
        "candidate_decisions": decisions[:100],
        "sources_unavailable": unavailable[:30],
        "official_sources_examined": len(considered),
        "editorial_frontpage_checked_at": frontpage.get("generated_at"),
        "note": ("An unchanged series is not a new official publication. "
                 "First discovery does not prove a fresh release. "
                 "An absent new article is not a failed editorial check."),
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--feed", default="data/news/automatic_features.json")
    p.add_argument("--frontpage", default="data/news/editorial_frontpage.json")
    p.add_argument("--publication-report", required=True)
    p.add_argument("--pipeline-report", required=True)
    p.add_argument("--output", default="data/news/editorial_refresh_status.json")
    a = p.parse_args(argv)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    status = make_status(read_json(a.feed), read_json(a.frontpage),
                         read_json(a.publication_report),
                         read_json(a.pipeline_report), now)
    out = Path(a.output)
    if out.is_file():
        previous = read_json(out)
        if previous.get("schema") == SCHEMA and (
            status["published_articles_total"] < previous.get("published_articles_total", 0)
        ):
            raise ValueError("published_archive_shrank")
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(out.suffix + ".tmp")
    temp.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(out)
    print(json.dumps({k:v for k,v in status.items()
                      if k != "candidate_decisions"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
