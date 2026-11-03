#!/usr/bin/env python3
"""Automatic, fail-closed promotion of reported statistical news.

A news item is checked against a primary statistical document. Only observations
from the same labelled structured table, with provenance, may be promoted.
No model-generated numbers, fabricated approval, or new publication dates.
"""
from __future__ import annotations
import math
import re
from urllib.parse import urlparse

try:
    from scripts.pulse_original_editorial import compose_verified, series_for_story
except ModuleNotFoundError:
    from pulse_original_editorial import compose_verified, series_for_story

_NUMBER = re.compile(r"(?<!\d)[+-]?\d+(?:[.,]\d+)?(?!\d)")


def reported_values(article):
    """Ignore bare years and numbers that cannot be interpreted unambiguously."""
    values = set()
    for claim in article.get("statistical_claims") or []:
        if not isinstance(claim, dict):
            continue
        token = str(claim.get("raw_value") or "").strip()
        # A source label such as '5,4 milioni' needs scaling context; no
        # inferred conversion between units or percentages is permitted.
        if not re.fullmatch(r"[+-]?\d+(?:[.,]\d{1,2})?\s*%?", token):
            continue
        match = _NUMBER.fullmatch(token.rstrip("%").strip())
        if not match:
            continue
        number = float(match.group().replace(",", "."))
        if math.isfinite(number) and not (1900 <= number <= 2100 and number.is_integer()):
            values.add(round(number, 6))
    return values


def evidence_from_dossier(dossier):
    for check in dossier.get("source_checks") or []:
        for item in check.get("candidate_evidence") or []:
            if isinstance(item, dict):
                yield item


def promote_media_brief(article, dossier):
    """Return a verified source-backed feature or None (preserve press alert)."""
    src = article.get("public_source") or {}
    if (article.get("publication_status") != "published" or
            src.get("role") != "journalistic_source" or
            dossier.get("article_id") != article.get("id")):
        return None
    claims = reported_values(article)
    if not claims or dossier.get("status") != "manual_primary_review_required":
        return None
    headline = str(article.get("reported_headline") or article.get("headline") or "")
    for record in evidence_from_dossier(dossier):
        if record.get("verified") is not True:
            continue
        document = str(record.get("source_url") or "")
        source_host = urlparse(document).hostname or ""
        if not document.startswith("https://") or not source_host:
            continue
        if (not re.fullmatch(r"[a-fA-F0-9]{64}", str(record.get("source_sha256") or ""))
                or not record.get("location") or not record.get("extraction_method")):
            continue
        observations = record.get("observations") or []
        if len(observations) < 2 or len(observations) > 30:
            continue
        # The source and reported unit must agree; a '5%' headline cannot be
        # matched to an unrelated 5-euro or 5-person table value.
        reported_claims = article.get("statistical_claims") or []
        if any("%" in str(c.get("raw_value") or "") for c in reported_claims
               if isinstance(c, dict)) and record.get("unit") != "%":
            continue
        # When the headline explicitly names a reference year, that year must
        # actually occur in the extracted time series.
        headline_years = set(re.findall(r"(?<!\\d)(?:19|20)\\d{2}(?!\\d)", headline))
        source_years = {str(x.get("period"))[:4] for x in observations
                        if isinstance(x, dict)}
        if headline_years and not (headline_years & source_years):
            continue
        # Hard gate: at least one numeric claim reported by the newspaper must
        # agree with an observation in the actual, named primary-source row.
        try:
            source_values = {round(float(x["value"]), 6) for x in observations}
        except (KeyError, ValueError, TypeError):
            continue
        if not claims.intersection(source_values):
            continue
        matching = series_for_story([record], headline, document)
        if not matching or len(matching[0]["observations"]) < 2:
            continue
        candidate = dict(article)
        candidate["public_source"] = {
            "url": document, "domain": source_host,
            "role": "primary_statistical_source",
            "verification_method": "same_row_structured_primary_source",
            "verification_score": 100
        }
        candidate["discovery"] = {
            **(article.get("discovery") or {}),
            "role": "journalistic_radar",
            "original_url": src.get("url"),
            "evidence_gate": "strong_primary_match"
        }
        candidate["original_discovery_headline"] = headline
        candidate["reported_claims"] = article.get("statistical_claims") or []
        promoted = compose_verified(candidate, {"verified_series": [record]})
        if (promoted.get("verification_tier") != "verified_comparable_series"
                or (promoted.get("chart_spec") or {}).get("status") != "verified"
                or (promoted.get("table_spec") or {}).get("status") != "verified"):
            continue
        promoted["publication_status"] = "published"
        promoted["editorial_status"] = "verified_primary_match"
        promoted["origin_kind"] = "pulse_primary_automatic"
        promoted["editorial_format"] = "automated_verified_analysis"
        promoted["verification_review"] = "automated_structural_check_not_human_review"
        promoted["evidence_provenance"] = {
            "source_url": document,
            "source_sha256": record["source_sha256"],
            "source_location": record["location"],
            "extraction_method": record["extraction_method"],
            "matched_reported_values": sorted(claims.intersection(source_values))
        }
        promoted["statistical_claims"] = [
            {"raw_value": str(p["value"]), "verified": True,
             "indicator": record["indicator"], "period": p["period"],
             "unit": record["unit"]} for p in matching[0]["observations"]
        ]
        # Unlike a new article, a promotion keeps the exact old identity/date.
        if (promoted["id"] != article["id"] or
                promoted.get("published_at") != article.get("published_at")):
            raise ValueError("identity_or_publication_date_changed")
        return promoted
    return None


def run_pending_research(by_id, domains, now, budget=2, research_fn=None):
    """Probe a bounded number of unverified stories on every normal refresh."""
    if research_fn is None:
        try:
            from scripts.pulse_primary_research import research_article
        except ModuleNotFoundError:
            from pulse_primary_research import research_article
        research_fn = research_article
    eligible = [
        a for a in by_id.values()
        if a.get("publication_status") == "published"
        and (a.get("public_source") or {}).get("role") == "journalistic_source"
        and a.get("origin_kind") == "pulse_media_radar"
    ]
    # Unchecked, recent stories first. Previously checked stories are retried
    # after 36 hours; the backlog is preserved across future daily runs.
    def days_since_attempt(a):
        previous = a.get("primary_research_last_attempt_at")
        if not previous:
            return None
        try:
            from datetime import datetime
            d = datetime.fromisoformat(previous.replace("Z", "+00:00"))
            return (now - d).total_seconds() / 3600
        except (TypeError, ValueError):
            return None
    due = [a for a in eligible if days_since_attempt(a) is None
           or days_since_attempt(a) >= 36]
    due.sort(key=lambda a:(not bool(a.get("primary_research_last_attempt_at")),
                           a.get("published_at", "")), reverse=True)
    summary = {"attempted": 0, "promoted": 0, "pending": len(due)}
    for article in due[:max(0, budget)]:
        current = by_id[article["id"]]
        try:
            report = research_fn(current, domains)
            improved = promote_media_brief(current, report)
            if improved:
                improved["primary_research_last_attempt_at"] = now.isoformat()
                by_id[current["id"]] = improved
                summary["promoted"] += 1
            else:
                current["primary_research_last_attempt_at"] = now.isoformat()
                current["primary_research_status"] = report.get("status", "no_matched_evidence")
        except (OSError, ValueError, TypeError, KeyError, TimeoutError) as exc:
            current["primary_research_last_attempt_at"] = now.isoformat()
            current["primary_research_status"] = "research_error_" + type(exc).__name__
        summary["attempted"] += 1
    return summary
