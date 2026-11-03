#!/usr/bin/env python3
"""PULSE primary-source research desk: an auditable queue, NOT an auto-publisher.

A press headline is a lead, never statistical verification. This tool searches
candidate official pages, extracts bounded structured data, and records where
every potential number was found. Human confirmation remains mandatory.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from scripts.pulse_evidence import extract_url, fetch_bounded
from scripts.pulse_evidence_adapters import discover_attachments
from scripts.pulse_original_editorial import words
from scripts.update_news_radar import multi_search

ROOT = Path(__file__).resolve().parents[1]
NEWS = ROOT / "data/news/articles.json"
CONFIG = ROOT / "data/news_radar_sources.json"
OUTPUT = ROOT / "data/news/primary_research_queue.json"
MAX_SOURCES_PER_STORY = 3
MAX_STORIES = 12
ALLOWED_DOCUMENT_EXTENSIONS = (".csv", ".tsv", ".xlsx", ".xls", ".pdf", ".json", ".html", ".htm")


def allowed_url(url, domains):
    """Require HTTPS, public configured domain and an actual publication path."""
    try:
        p = urlparse(str(url))
        h = (p.hostname or "").lower()
        if p.scheme != "https" or p.username or p.password or not p.path.strip("/"):
            return False
        return any(h == d or h.endswith("." + d) for d in domains)
    except (TypeError, ValueError):
        return False


def article_leads(article):
    source = article.get("public_source") or {}
    leads = []
    if source.get("role") == "primary_statistical_source":
        leads.append(source.get("url"))
    for item in article.get("sources") or []:
        if isinstance(item, dict) and item.get("role") in ("statistical_primary", "primary_statistical_source"):
            leads.append(item.get("url"))
    return [x for x in dict.fromkeys(leads) if x]


def search_leads(article, domains, search_fn=multi_search):
    """Search official providers only. Search snippets are never evidence."""
    title = str(article.get("original_discovery_headline") or article.get("reported_headline") or article.get("headline") or "")
    tokens = sorted(words(title), key=len, reverse=True)[:5]
    if len(tokens) < 2:
        return []
    query = " ".join(tokens[:5]) + " statistica rapporto dati"
    results = search_fn(query, limit=8)
    return [r.get("url") for r in results if allowed_url(r.get("url"), domains)]


def relevant_evidence(item, article, source_host):
    """Conservatively rank matching indicators; do not treat matching as proof."""
    if not isinstance(item, dict) or item.get("verified") is not True:
        return False
    url = str(item.get("source_url") or "")
    if (urlparse(url).hostname or "").lower() != source_host:
        return False
    if not item.get("source_sha256") or not item.get("location") or not item.get("extraction_method"):
        return False
    indicator = str(item.get("indicator") or "")
    headline = str(article.get("original_discovery_headline") or article.get("headline") or "")
    common = words(indicator) & words(headline)
    if not common:
        return False
    observations = item.get("observations") or []
    return bool(item.get("unit")) and len(observations) >= 1


def examine(url, article, domains, fetch_fn=fetch_bounded, extract_fn=extract_url):
    """Explore the landing document and limited same-host attachments."""
    if not allowed_url(url, domains):
        return {"url": url, "status": "excluded_domain"}
    candidates = [url]
    try:
        raw, mime, final = fetch_fn(url)
        if not allowed_url(final, domains):
            return {"url": url, "status": "redirect_outside_official_domains"}
        if "html" in mime.lower():
            candidates += [
                u for u in discover_attachments(raw, final, max_links=3)
                if allowed_url(u, domains)
            ]
    except (OSError, ValueError, TimeoutError) as exc:
        return {"url": url, "status": "fetch_failed", "error": type(exc).__name__}
    evidence = []
    checked = []
    for doc in dict.fromkeys(candidates[:4]):
        try:
            result = extract_fn(doc)
            # Never accept a redirect's evidence without validating final origin.
            resolved = result.get("source_url", doc)
            if not allowed_url(resolved, domains):
                checked.append({"url": doc, "status": "redirect_outside_official_domains"})
                continue
            checked.append({"url": resolved, "status": result.get("status")})
            for row in result.get("evidence", [])[:20]:
                if relevant_evidence(row, article, (urlparse(resolved).hostname or "").lower()):
                    evidence.append(row)
        except (OSError, ValueError, TypeError, KeyError, TimeoutError) as exc:
            checked.append({"url": doc, "status": "extraction_failed", "error": type(exc).__name__})
    return {"url": url, "status": "potential_evidence_requires_review" if evidence else "no_matched_structured_data",
            "documents": checked, "candidate_evidence": evidence[:5]}


def research_article(article, domains, search_fn=multi_search, fetch_fn=fetch_bounded, extract_fn=extract_url):
    urls = [u for u in article_leads(article) if allowed_url(u, domains)]
    for u in search_leads(article, domains, search_fn):
        if u not in urls:
            urls.append(u)
    checked = [examine(u, article, domains, fetch_fn, extract_fn)
               for u in urls[:MAX_SOURCES_PER_STORY]]
    candidates = [c for x in checked for c in x.get("candidate_evidence", [])]
    return {
        "article_id": article.get("id"),
        "headline": article.get("headline"),
        "published_at": article.get("published_at"),
        "source_leads": urls[:MAX_SOURCES_PER_STORY],
        "source_checks": checked,
        "status": "manual_primary_review_required" if candidates else "primary_evidence_not_found",
        "editorial_action": ("Inspect provenance, indicator definition, territory, unit, year and publication date before any promotion."
                             if candidates else "Retain attributed press brief; do not invent a chart, table or original statistical interpretation."),
        "publication_allowed_automatically": False,
        "candidate_count": len(candidates)
    }


def build_queue(articles, domains, limit=MAX_STORIES, **kwargs):
    eligible = [a for a in articles if a.get("publication_status") == "published"
                and (a.get("public_source") or {}).get("role") == "journalistic_source"]
    eligible.sort(key=lambda a: a.get("published_at", ""), reverse=True)
    rows = [research_article(a, domains, **kwargs) for a in eligible[:limit]]
    return {"schema_version": 1, "checked_at": datetime.now(timezone.utc).isoformat(),
            "safety": "research_candidates_only_not_published_verified_articles",
            "total_press_briefs": len(eligible), "checked": len(rows),
            "requires_manual_review": sum(r["status"] == "manual_primary_review_required" for r in rows),
            "items": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=8, help="Maximum press briefs, 1 to 12")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--dry-run", action="store_true", help="No output write; still performs bounded online research")
    args = parser.parse_args()
    if not 1 <= args.limit <= MAX_STORIES:
        parser.error("--limit must be between 1 and 12")
    bundle = json.loads(NEWS.read_text(encoding="utf-8"))
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    domains = [str(d).lower() for d in cfg.get("official_domains", [])]
    if not domains:
        raise SystemExit("No authoritative source domains configured")
    report = build_queue(bundle["articles"], domains, limit=args.limit)
    if not args.dry_run:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, ensure_ascii=False))
    print("Publication changed: NO; source report saved:", not args.dry_run)


if __name__ == "__main__":
    main()
