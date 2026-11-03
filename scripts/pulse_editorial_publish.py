#!/usr/bin/env python3
"""Gate editorially reviewed PULSE features; never manufacture verification.

The feature file is a stable data input to the existing news refresh.
Publication requires a signed-off human-authored body plus source-backed values.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def _words(text):
    return re.findall(r"\b[\wÀ-ÿ]+\b", text or "", flags=re.UNICODE)


def validate_feature(draft, edited):
    original_id = str(draft.get("id") or "")
    review = draft.get("editorial_review") or {}
    if draft.get("publication_status") != "draft" or not original_id.startswith("PULSE-"):
        raise ValueError("not_reviewed_draft")
    if not review.get("reviewer") or not review.get("source_sha256") or not review.get("source_location"):
        raise ValueError("review_provenance_missing")
    if draft.get("verification_tier") != "verified_comparable_series":
        raise ValueError("no_verified_comparable_series")
    primary = draft.get("public_source") or {}
    if primary.get("role") != "primary_statistical_source":
        raise ValueError("no_primary_source")
    url = str(primary.get("url") or "")
    if urlparse(url).scheme != "https" or not urlparse(url).hostname:
        raise ValueError("invalid_primary_source_url")
    chart, table = draft.get("chart_spec") or {}, draft.get("table_spec") or {}
    if chart.get("status") != "verified" or table.get("status") != "verified":
        raise ValueError("chart_table_not_verified")
    series = chart.get("data") or []
    rows = table.get("rows") or []
    if len(series) < 2 or len(rows) != len(series):
        raise ValueError("chart_table_length_mismatch")
    if chart.get("source_url") != url or table.get("source_url") != url:
        raise ValueError("chart_table_source_mismatch")
    for point, row in zip(series, rows):
        if str(point.get("period")) != str(row[0]):
            raise ValueError("period_mismatch")
    if edited.get("article_id") != original_id:
        raise ValueError("article_id_mismatch")
    if edited.get("decision") != "publish" or edited.get("reviewer") != review["reviewer"]:
        raise ValueError("publication_approval_required")
    if not edited.get("copy_editor") or len(str(edited["copy_editor"]).strip()) < 3:
        raise ValueError("copy_editor_required")
    approved_at = datetime.fromisoformat(str(edited["approved_at"]).replace("Z", "+00:00"))
    if approved_at.tzinfo is None:
        raise ValueError("timezone_required")
    title = str(edited.get("headline") or "").strip()
    lead = str(edited.get("lead") or "").strip()
    paragraphs = edited.get("paragraphs") or []
    if len(title) < 22 or len(lead) < 80 or not isinstance(paragraphs, list) or len(paragraphs) < 5:
        raise ValueError("insufficient_editorial_structure")
    if any(not isinstance(p, str) or len(_words(p)) < 40 for p in paragraphs):
        raise ValueError("paragraphs_too_short")
    if len(_words(" ".join([lead] + paragraphs))) < 360:
        raise ValueError("article_not_longform")
    if len({re.sub(r"\s+", " ", p.strip().casefold()) for p in paragraphs}) != len(paragraphs):
        raise ValueError("duplicate_paragraphs")
    if not edited.get("independent_verification_note") or len(str(edited["independent_verification_note"])) < 60:
        raise ValueError("missing_independent_verification_note")
    try:
        from scripts.pulse_editorial_quality import assess_story
    except ModuleNotFoundError:
        from pulse_editorial_quality import assess_story
    audit = assess_story(title, lead, paragraphs, chart.get("data", []))
    if not audit["passed"]:
        raise ValueError("editorial_quality_failed:" + ",".join(audit["issues"]))
    approved = dict(draft)
    approved["headline"] = title
    approved["pulse_title"] = title
    approved["summary"] = lead
    approved["pulse_summary"] = lead
    approved["pulse_article_body"] = [{"heading": "", "text": p.strip()} for p in paragraphs]
    approved["discovery"] = {**(approved.get("discovery") or {}), "evidence_gate": "strong_primary_match"}
    approved["publication_status"] = "published"
    approved["editorial_status"] = "verified"
    approved["editorial_format"] = "individually_edited_longform"
    approved["editorial_quality"] = audit
    approved["byline"] = "Redazione PULSE"
    approved["editorial_review"] = {**review, "ready_for_publication": True,
                                   "copy_editor": str(edited["copy_editor"]),
                                   "approved_at": approved_at.isoformat(),
                                   "independent_verification_note": edited["independent_verification_note"]}
    # Preserve original source-published date and stable ID: no rebirth in OGGI.
    if approved["id"] != draft["id"] or approved.get("published_at") != draft.get("published_at"):
        raise ValueError("identity_or_date_changed")
    return approved


def merge_features(articles, features):
    """Overlay only matching approved IDs; avoid creating a duplicate news item."""
    approved = {a["id"]: a for a in features}
    if len(approved) != len(features):
        raise ValueError("duplicate_feature_ids")
    output = []
    used = set()
    for article in articles:
        identity = article.get("id")
        if identity in approved:
            original = article
            replacement = approved[identity]
            if original.get("published_at") != replacement.get("published_at"):
                raise ValueError("date_changed")
            output.append(replacement)
            used.add(identity)
        else:
            output.append(article)
    if set(approved) != used:
        raise ValueError("missing_original_press_articles")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drafts", type=Path, required=True)
    parser.add_argument("--edits", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    drafts = json.loads(args.drafts.read_text(encoding="utf-8"))
    edits = json.loads(args.edits.read_text(encoding="utf-8"))
    by_id = {a["id"]: a for a in drafts.get("drafts", [])}
    if len(by_id) != len(drafts.get("drafts", [])):
        raise ValueError("duplicate_draft_ids")
    features = []
    for edited in edits.get("articles", []):
        if edited.get("article_id") not in by_id:
            raise ValueError("no_reviewed_draft")
        features.append(validate_feature(by_id[edited["article_id"]], edited))
    if not features:
        raise ValueError("no_approved_features")
    target = {"schema_version": 1, "features": features}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(features)} approved features validated; original IDs and dates retained")


if __name__ == "__main__":
    main()
