#!/usr/bin/env python3
"""Create original PULSE article DRAFTS only from explicitly reviewed evidence.

This cannot publish news, change date indices, or approve an automated match.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from scripts.pulse_original_editorial import compose_verified
from scripts.pulse_primary_research import allowed_url

ROOT = Path(__file__).resolve().parents[1]


def reviewed_draft(article, dossier, decision, domains):
    if decision.get("decision") != "approved":
        raise ValueError("explicit_approval_required")
    reviewer = str(decision.get("reviewer") or "").strip()
    if len(reviewer) < 3:
        raise ValueError("reviewer_required")
    reviewed_at = datetime.fromisoformat(str(decision["reviewed_at"]).replace("Z", "+00:00"))
    if reviewed_at.tzinfo is None:
        raise ValueError("timezone_required")
    date.fromisoformat(str(decision["primary_publication_date"]))
    territory = str(decision.get("territory") or "").strip()
    dataset = str(decision.get("dataset") or "").strip()
    method = str(decision.get("methodology") or "").strip()
    if not (territory and dataset and len(method) >= 15):
        raise ValueError("territory_dataset_methodology_required")
    if article.get("id") != dossier.get("article_id") or article.get("id") != decision.get("article_id"):
        raise ValueError("wrong_article")
    if dossier.get("status") != "manual_primary_review_required":
        raise ValueError("not_a_reviewable_dossier")
    source_url = decision.get("source_url")
    if not allowed_url(source_url, domains):
        raise ValueError("unapproved_source_domain")
    match = None
    for checked in dossier.get("source_checks", []):
        for row in checked.get("candidate_evidence", []):
            if (row.get("source_url") == source_url
                    and row.get("source_sha256") == decision.get("source_sha256")
                    and row.get("location") == decision.get("location")
                    and row.get("indicator") == decision.get("indicator")
                    and row.get("unit") == decision.get("unit")
                    and row.get("verified") is True):
                match = row
                break
    if match is None:
        raise ValueError("evidence_not_in_dossier")
    if len(match.get("observations", [])) < 2:
        raise ValueError("no_comparable_series")
    discovery_url = (article.get("public_source") or {}).get("url") or ""
    candidate = dict(article)
    candidate["public_source"] = {
        "role": "primary_statistical_source", "url": source_url,
        "domain": __import__("urllib.parse", fromlist=["urlparse"]).urlparse(source_url).hostname
    }
    candidate["discovery"] = {"role": "journalistic_radar", "original_url": discovery_url,
                              "outlet": (article.get("public_source") or {}).get("domain", "")}
    verified = compose_verified(candidate, {"verified_series": [match]})
    if verified.get("verification_tier") != "verified_comparable_series":
        raise ValueError("editorial_topic_or_source_not_validated")
    verified["publication_status"] = "draft"
    verified["editorial_review"] = {
        "reviewer": reviewer, "reviewed_at": reviewed_at.isoformat(),
        "primary_publication_date": decision["primary_publication_date"],
        "territory": territory, "dataset": dataset,
        "methodology": method, "source_sha256": match["source_sha256"],
        "source_location": match["location"], "ready_for_publication": False
    }
    return verified


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dossiers", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "data/news/reviewed_article_drafts.json")
    args = parser.parse_args()
    reports = json.loads(args.dossiers.read_text(encoding="utf-8"))
    decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
    articles = {a["id"]: a for a in json.loads((ROOT / "data/news/articles.json").read_text(encoding="utf-8"))["articles"]}
    cfg = json.loads((ROOT / "data/news_radar_sources.json").read_text(encoding="utf-8"))
    queue = {item["article_id"]: item for item in reports["items"]}
    output = []
    for decision in decisions.get("reviews", []):
        aid = decision["article_id"]
        if aid not in articles or aid not in queue:
            raise ValueError("reviewed_article_missing")
        output.append(reviewed_draft(articles[aid], queue[aid], decision, cfg["official_domains"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"drafts": output, "publication_allowed": False},
                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(output)} reviewed DRAFTS; no feed or date index modified.")


if __name__ == "__main__":
    main()
