#!/usr/bin/env python3
"""Editorial recovery safeguards for ISTAT PULSE DATA.

Pure, deterministic, network-free transformations. Do not assert that matching
numeric strings verify a statistical claim; source publication and quantitative
verification are distinct. No automated approval of AI text.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlsplit

WORD = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
STOP = {"della", "delle", "degli", "dello", "nella", "nelle", "nelle", "dalla",
        "sulla", "sulle", "per", "con", "che", "una", "uno", "non", "gli", "del",
        "dei", "alla", "alle", "nel", "nei", "sono", "questa", "questo", "anche",
        "come", "dopo", "prima", "anno", "anni", "pubblicazione", "fonte"}
RELATED_MARKERS = ("contenuti correlati", "articoli correlati", "leggi anche",
                   "potrebbe interessarti", "altre notizie", "news correlate")
FALLBACK_MARKERS = ("p​​ulse", "istat pulse mantiene il collegamento",
                    "è classificata da istat pulse come documento",
                    "non aggiunge dati, cause o conclusioni")
FORMULAIC_RADAR = ("valori individuati:", "per associare ogni valore al suo indicatore")


def _text(block: Any) -> str:
    return (str(block.get("text") or "") if isinstance(block, dict)
            else str(block) if isinstance(block, str) else "").strip()


def _words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text or "") if len(w) > 3 and w.lower() not in STOP]


def _source_card_summary(article: dict) -> str:
    title = str(article.get("pulse_title") or article.get("headline") or "Documento").strip()
    return (f"Scheda della fonte ufficiale: «{title}». Il documento originale è consultabile "
            "tramite il collegamento alla fonte. PULSE non attribuisce cifre a "
            "indicatori, unità, territori o periodi senza una verifica statistica completa.")


def evidence_ledger(article: dict) -> dict:
    """Expose typed, already-verified observations, not guessed claim bindings."""
    source = article.get("public_source") or {}
    url = str(source.get("url") or "")
    if (source.get("role") != "primary_statistical_source" or
            urlsplit(url).scheme != "https" or not urlsplit(url).hostname):
        return {"verified": False, "observations": [], "reason": "no_primary_statistical_source"}
    primary_host = (urlsplit(url).hostname or "").lower()
    series = article.get("verified_series_relevant") or []
    if not isinstance(series, list):
        series = []
    chart = article.get("chart_spec") or {}
    if not series and chart.get("status") == "verified":
        # Chart is a downstream artifact. Its labels are useful, but without
        # a complete source-linked series it is not an independently audited fact.
        return {"verified": False, "observations": [], "reason": "typed_primary_series_missing"}
    result = []
    for record in series:
        if not isinstance(record, dict):
            continue
        indicator = str(record.get("indicator") or "").strip()
        unit = str(record.get("unit") or "").strip()
        record_url = str(record.get("source_url") or "")
        doc_parts = urlsplit(record_url)
        document_host = (doc_parts.hostname or "").lower()
        # PULSE's upstream validator also allows a document hosted in a
        # subdomain of the same institution (e.g., static.istat.it). Preserve
        # the actual document link in the ledger; never silently substitute it.
        same_institution = (primary_host == document_host or
                            primary_host.endswith("." + document_host) or
                            document_host.endswith("." + primary_host))
        if not (indicator and unit and doc_parts.scheme == "https" and
                document_host and same_institution):
            continue
        for point in (record.get("observations") or []):
            if not isinstance(point, dict):
                continue
            try:
                value = float(point["value"])
                from math import isfinite
                if not isfinite(value):
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            period = str(point.get("period") or "").strip()
            if not period:
                continue
            result.append({"indicator": indicator, "unit": unit,
                           "value": value, "period": period,
                           "source_url": record_url, "territory": str(record.get("territory") or ""),
                           "denominator": str(record.get("denominator") or "")})
    return {"verified": bool(result), "observations": result,
            "reason": "verified_typed_observations" if result else "no_typed_observations"}


def _seems_related_title(text: str, title_terms: set[str]) -> bool:
    low = text.casefold()
    if any(marker in low for marker in RELATED_MARKERS):
        return True
    words = _words(text)
    # A short, standalone headline without a terminal sentence mark and with
    # almost no overlap with the main document is a *candidate*, not proof.
    if not (5 <= len(words) <= 26 and 25 <= len(text) <= 210):
        return False
    if re.search(r"[.!?][\s\"”']*$", text):
        return False
    return len(set(words) & title_terms) <= 1


def clean_observer_article(original: dict) -> tuple[dict, list[str]]:
    """Conservatively demote proven boilerplate/related-links contamination.

    Never delete the record, its source URL, first-seen date or provenance.
    Do not claim that the original page was independently audited.
    """
    article = dict(original)
    body = article.get("pulse_article_body") or []
    if not isinstance(body, list):
        return article, []
    content = [_text(p) for p in body]
    content = [p for p in content if p]
    if not content:
        return article, []
    issues = []
    # Source-only records previously padded with three generic paragraphs.
    if (len(content) >= 3 and content[0] == str(article.get("pulse_summary") or "").strip()
            and any(marker in " ".join(content[1:]).casefold() for marker in FALLBACK_MARKERS)):
        article["pulse_article_body"] = [content[0]]
        article["editorial_format"] = "source_card"
        issues.append("boilerplate_observer_article_demoted")
    else:
        title_terms = set(_words(str(article.get("pulse_title") or article.get("headline") or "")))
        candidates = [_seems_related_title(s, title_terms) for s in content[1:]]
        # Require a RUN of >=3 candidate link-headlines after a meaningful
        # first paragraph, preventing removal of legitimate isolated subtitles.
        if (len(_words(content[0])) >= 20 and len(candidates) >= 3
                and sum(candidates) >= 3 and all(candidates)):
            article["pulse_article_body"] = [content[0]]
            article["pulse_summary"] = content[0][:620]
            if str(article.get("summary") or ""):
                article["summary"] = content[0][:620]
            # The naive figures were extracted from the entire HTML page;
            # they are not individually source-linked statistical indicators.
            if article.get("key_figures"):
                article["key_figures"] = []
                issues.append("untyped_page_numbers_removed")
            article["editorial_format"] = "source_card"
            issues.append("related_page_headlines_removed")
    if issues:
        article["editorial_recovery"] = {
            "version": 1, "classification": "source_card",
            "issues": issues,
            "original_body_sha256": hashlib.sha256(
                json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "source_verified_is_not_statistic_verified": True}
    return article, issues


def repair_observer_archive(articles: list[dict]) -> tuple[list[dict], dict]:
    fixed = 0
    tally = Counter()
    output = []
    for old in articles:
        if not isinstance(old, dict):
            output.append(old)
            continue
        repaired, issues = clean_observer_article(old)
        if issues:
            fixed += 1
            tally.update(issues)
        output.append(repaired)
    return output, {"changed": fixed, "issue_counts": dict(tally),
                    "articles_examined": len(articles)}


def audit_news_archive(articles: list[dict]) -> tuple[list[dict], dict]:
    """Separate verified features from source cards without breaking IDs/indexes."""
    fixed, ledger_count = 0, 0
    output = []
    for old in articles:
        article = dict(old)
        src = article.get("public_source") or {}
        if src.get("role") == "primary_statistical_source":
            ledger = evidence_ledger(article)
            if ledger["verified"]:
                article["editorial_evidence_ledger"] = ledger
                ledger_count += 1
            elif (article.get("publication_status") == "published"
                    and article.get("editorial_status") in ("verified", "verified_primary_match")
                    and any(x in (str(article.get("summary") or "")).casefold()
                            for x in FORMULAIC_RADAR)):
                # A primary-source URL plus coincidental digits are not enough
                # to call an item a statistical feature. Preserve the record
                # and its indexes, but label honestly as a *source card*.
                new_summary = _source_card_summary(article)
                article["summary"] = new_summary
                article["pulse_summary"] = new_summary
                article["pulse_article_body"] = [new_summary]
                article["editorial_format"] = "source_card"
                article["editorial_recovery"] = {
                    "version": 1, "classification": "source_card",
                    "issues": ["untyped_numbers_not_statistical_claims"],
                    "source_verified_is_not_statistic_verified": True}
                fixed += 1
        output.append(article)
    return output, {"source_cards_reclassified": fixed,
                    "typed_evidence_ledgers": ledger_count,
                    "articles_examined": len(articles)}


def stage_ai_draft(original: dict, proposed: dict, at: str | None = None) -> dict:
    """Create a review-only candidate. Never mark text approved/published."""
    ledger = evidence_ledger(original)
    chart = original.get("chart_spec") or {}
    chart_points = chart.get("data") or []
    observed_periods = {p["period"] for p in ledger["observations"]}
    if (not ledger["verified"] or len(observed_periods) < 2
            or chart.get("status") != "verified" or len(chart_points) < 2):
        raise ValueError("verified_comparable_series_required")
    # Every chart point must match a typed observation from the primary source.
    typed = {(str(p["period"]), float(p["value"])) for p in ledger["observations"]}
    try:
        if any((str(p["period"]), float(p["value"])) not in typed for p in chart_points):
            raise ValueError("chart_contains_unmapped_values")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid_chart_points") from exc
    src = original.get("public_source") or {}
    if (original.get("verification_tier") != "verified_comparable_series"
            or original.get("publication_status") != "published"
            or src.get("role") != "primary_statistical_source"):
        raise ValueError("comparable_primary_series_required")
    if proposed.get("editorial_format") != "ai_assisted_evidence_checked":
        raise ValueError("ai_draft_format_required")
    automated_review = proposed.get("editorial_review") or {}
    if (automated_review.get("human_editorial_review") is not False
            or automated_review.get("automatic_numeric_validation") is not True):
        raise ValueError("numeric_check_and_human_review_pending_required")
    at = at or datetime.now(timezone.utc).isoformat()
    payload = {
        "article_id": original.get("id"), "created_at": at,
        "source_url": src.get("url"), "source_publication_date": original.get("published_at"),
        "candidate": {"headline": proposed.get("headline"),
                      "lead": proposed.get("summary"),
                      "paragraphs": [_text(p) for p in (proposed.get("pulse_article_body") or [])]},
        "evidence_ledger": ledger,
        "review_status": "human_review_required",
        "publication_allowed": False,
        "pending_checks": ["source_document_hash", "number_to_indicator_links",
                           "independent_semantic_review", "human_copy_editor_approval"]}
    if not payload["article_id"]:
        raise ValueError("missing_article_id")
    return payload
