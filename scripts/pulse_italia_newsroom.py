#!/usr/bin/env python3
"""PULSE Italia: original Italian-news selection and source-led draft orchestration.

Architectural inspiration: Automated Press Review (AlessioRepetto) — no source code
copied. This module is stdlib-only and never auto-publishes generated articles.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

REGIONS = (
    "abruzzo", "basilicata", "calabria", "campania", "emilia-romagna",
    "friuli-venezia giulia", "lazio", "liguria", "lombardia", "marche",
    "molise", "piemonte", "puglia", "sardegna", "sicilia", "toscana",
    "trentino-alto adige", "umbria", "valle d'aosta", "veneto",
)
LOCALITIES = (
    "roma", "milano", "napoli", "torino", "palermo", "genova", "bologna",
    "firenze", "bari", "catania", "venezia", "verona", "padova", "trieste",
    "perugia", "cagliari", "trento", "bolzano", "l'aquila", "catanzaro",
    "aosta", "pisa", "brescia", "parma", "modena", "bergamo", "salerno",
)
ITALIAN_MARKERS = ("italia", "italiano", "italiana", "italiani", "italiane",
                   "nel paese", "nostro paese", "nazionale")
ITALIAN_OFFICIAL_HOSTS = (
    "istat.it", "inps.it", "inail.it", "mef.gov.it", "finanze.gov.it",
    "bancaditalia.it", "iss.it", "salute.gov.it", "aci.it",
    "isprambiente.gov.it", "arera.it", "terna.it", "gse.it",
    "agenziaentrate.gov.it", "istruzione.gov.it", "mur.gov.it",
    "unioncamere.gov.it",
)
TOPIC_IMPACT = {
    "SALUTE": 23, "LAVORO": 23, "ECONOMIA": 22, "DEMOGRAFIA": 22,
    "ISTRUZIONE": 20, "AMBIENTE": 20, "CASA": 21, "ENERGIA": 20,
    "MOBILITA": 18, "SOCIETA": 23, "ALTRO": 10,
}
FOREIGN_HEADLINE_MARKERS = ("new york", "germania", "francia", "stati uniti",
                            "cina", "regno unito", "spagna", "india", "russia",
                            "turchia", "londra", "parigi", "berlino", "tokyo")
ITALIAN_PRESS_EXCEPTIONS = ("open.online", "ilsole24ore.com", "ilfattoquotidiano.it",
                            "fanpage.it", "tgcom24.mediaset.it")
STATISTICAL_EDITORIAL_WORDS = (
    "statistic", "rapporto", "indagine", "rilevazione", "censimento",
    "povert", "reddito", "inflazion", "prezzi", "stipendi", "salari",
    "disoccupazion", "occupazion", "pension", "natalit", "demograf",
    "inquinament", "emission", "abitanti", "consumi", "tasso", "percent",
    "mercato immobiliare", "rifiuti", "popolazione", "indicator",
)
STAT_WORDS = (
    "rapporto", "rilevazione", "censimento", "tasso", "quota", "serie",
    "indicator", "istat", "statistic", "variazione", "povert", "occupazion",
    "natalit", "inflazion", "reddito", "consumi", "abitanti",
)
COMMON = {
    "delle", "della", "degli", "nelle", "negli", "sono", "alla", "sulla",
    "questo", "dopo", "primo", "nelle", "anche", "italia", "italiano",
    "italiana", "istat", "dati", "nuovo", "numeri", "2026", "2025",
}
UTC = timezone.utc


def _normal(s):
    return re.sub(r"\s+", " ", str(s or "").casefold()).strip()


def _matches(text, marker):
    return re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", text) is not None


def host(url):
    try:
        parsed = urlsplit(str(url))
        if parsed.scheme != "https" or parsed.username or parsed.password:
            return ""
        return (parsed.hostname or "").lower()
    except ValueError:
        return ""


def italian_official_url(url):
    h = host(url)
    return any(h == domain or h.endswith("." + domain) for domain in ITALIAN_OFFICIAL_HOSTS)


def _scope_strings(item):
    scope = item.get("geographic_scope") or {}
    if isinstance(scope, dict):
        code = str(scope.get("country_code") or scope.get("country") or "").upper()
        if code and code not in {"IT", "ITALIA", "ITALY"}:
            return False, []
        if code in {"IT", "ITALIA", "ITALY"}:
            return True, ["italia"]
    if isinstance(item.get("country_code"), str):
        code = item["country_code"].upper()
        if code not in {"IT", "ITALIA"}:
            return False, []
        return True, ["italia"]
    territories = item.get("territories") or []
    if isinstance(territories, str):
        territories = [territories]
    if isinstance(territories, list):
        return None, [_normal(x) for x in territories if isinstance(x, str)]
    return None, []


def italy_relevant(item):
    """Conservative editorial boundary: Italian subject, not merely Italian language."""
    flag, labels = _scope_strings(item)
    if flag is False:
        return False
    if flag is True:
        return True
    for label in labels:
        if label in {"it", "italia", "italy", "nazionale"}:
            return True
        if any(_matches(label, place) for place in REGIONS + LOCALITIES):
            return True
    text = _normal(" ".join(str(item.get(k) or "") for k in
                           ("headline", "summary", "pulse_title")))
    # City/region mentions are considered only as whole words; avoid matching
    # foreign names containing substrings such as "roma" inside "Romania".
    if any(_matches(_normal(item.get("headline")), foreign) for foreign in FOREIGN_HEADLINE_MARKERS):
        return False
    return any(_matches(text, name) for name in ITALIAN_MARKERS + REGIONS + LOCALITIES)


def italian_source_and_subject(item):
    """Accept Italian institutional sources or Italian press with actual statistical topic."""
    src = item.get("public_source") or {}
    url = src.get("url", "")
    h = host(url)
    if italian_official_url(url):
        return True
    if src.get("role") != "journalistic_source":
        return False
    # A foreign publication reporting in Italian is still an external source.
    if not (h.endswith(".it") or h in ITALIAN_PRESS_EXCEPTIONS):
        return False
    content = _normal(str(item.get("headline") or "") + " " + str(item.get("summary") or ""))
    return any(word in content for word in STATISTICAL_EDITORIAL_WORDS)


def canonical_url(url):
    p = urlsplit(str(url or ""))
    if not p.netloc:
        return ""
    qs = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_")
          and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."),
                      p.path.rstrip("/"), urlencode(sorted(qs)), ""))


def _tokens(item):
    text = _normal(item.get("headline") or "")
    return {w for w in re.findall(r"[a-zà-ÿ0-9]+", text) if len(w) >= 4 and w not in COMMON}


def same_story(left, right):
    la = canonical_url((left.get("public_source") or {}).get("url", ""))
    ra = canonical_url((right.get("public_source") or {}).get("url", ""))
    if la and la == ra:
        return True
    if _normal(left.get("topic")) != _normal(right.get("topic")):
        return False
    a, b = _tokens(left), _tokens(right)
    if min(len(a), len(b)) < 3:
        return False
    jaccard = len(a & b) / max(1, len(a | b))
    text_ratio = SequenceMatcher(None, _normal(left.get("headline")),
                                 _normal(right.get("headline"))).ratio()
    return jaccard >= 0.78 or (jaccard >= 0.62 and text_ratio >= 0.85)


def eligible_primary(item):
    source = item.get("public_source") or {}
    chart = item.get("chart_spec") or {}
    if not (italy_relevant(item) and source.get("role") == "primary_statistical_source"
            and italian_official_url(source.get("url"))
            and chart.get("status") == "verified"
            and len(chart.get("data") or []) >= 2):
        return False
    if not (item.get("verification_tier") == "verified_comparable_series"
            or item.get("editorial_status") in {"verified", "verified_primary_match"}):
        return False
    return bool(item.get("source_documents") or item.get("verified_series")
                or item.get("verified_series_relevant"))


def score(item, now=None):
    """Explainable ranking; never claim this is a statistical verification score."""
    now = now or datetime.now(UTC)
    source = item.get("public_source") or {}
    topic = _normal(item.get("topic")).upper()
    published = str(item.get("published_at") or "")
    try:
        t = datetime.fromisoformat(published.replace("Z", "+00:00"))
        age_hours = max(0.0, (now - t.astimezone(UTC)).total_seconds() / 3600)
    except (ValueError, TypeError):
        age_hours = 9999
    # Impact 0-25; novelty/recency 0-20; usable evidence 0-25;
    # relevance 0-20; diversity and human news judgment are separate.
    impact = TOPIC_IMPACT.get(topic, 12)
    novelty = 20 if age_hours < 24 else 14 if age_hours < 48 else 7 if age_hours < 168 else 0
    evidence = 25 if eligible_primary(item) else 4 if source.get("role") == "journalistic_source" else 0
    headline = _normal(item.get("headline"))
    relevance = min(20, 4 * sum(w in headline for w in STAT_WORDS))
    return {"impact": impact, "freshness": novelty,
            "evidence_readiness": evidence, "statistical_relevance": relevance,
            "total": min(100, impact + novelty + evidence + relevance)}


def select_candidates(articles, limit=20, now=None, per_topic=5):
    if limit < 1:
        raise ValueError("positive_limit_required")
    now = now or datetime.now(UTC)
    candidates = [x for x in articles if isinstance(x, dict)
                  and x.get("publication_status", "published") == "published"
                  and italy_relevant(x) and italian_source_and_subject(x)]
    enriched = [{**x, "_selection_score": score(x, now)} for x in candidates]
    enriched.sort(key=lambda x: (x["_selection_score"]["total"],
                                 int(eligible_primary(x)),
                                 str(x.get("published_at") or ""), str(x.get("id") or "")),
                  reverse=True)
    chosen = []
    topics = Counter()
    duplicates = 0
    for article in enriched:
        if len(chosen) >= limit:
            break
        if any(same_story(article, old) for old in chosen):
            duplicates += 1
            continue
        category = str(article.get("topic") or "ALTRO").upper()
        if topics[category] >= per_topic:
            continue
        chosen.append(article)
        topics[category] += 1
    results = []
    for a in chosen:
        source = a["public_source"]
        results.append({
            "id": a.get("id"), "headline": a.get("headline"),
            "topic": a.get("topic"), "published_at": a.get("published_at"),
            "source_url": source.get("url"), "source_role": source.get("role"),
            "pulse_editorial_priority": a["_selection_score"],
            "eligible_for_ai_draft": eligible_primary(a),
            "next_step": "prepare_verified_evidence_manifest" if not eligible_primary(a)
                         else "review_verified_source_and_prepare_draft",
            "note": ("Fonte primaria e serie nel feed: ricontrollare l'origine dei dati."
                     if eligible_primary(a) else
                     "Solo candidatura. Non attribuire cifre a fonte ufficiale non verificata."),
        })
    return {"schema_version": 1, "generated_at": now.isoformat(),
            "scope": "IT", "limit": limit, "candidate_count": len(candidates),
            "deduplicated_within_selection": duplicates,
            "selected_count": len(results), "by_topic": dict(topics),
            "selected": results}


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temporary = p.with_name(p.name + ".tmp")
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(p)


def prepare_queue(input_path, output_path, limit=20):
    doc = json.loads(Path(input_path).read_text(encoding="utf-8"))
    payload = select_candidates(doc["articles"], limit=limit)
    write_json(output_path, payload)
    return payload


def generate_verified_drafts(manifests_dir, output_dir, limit=20):
    """Use existing v1 engine. No invented datasets, no autopublishing."""
    from scripts.pulse_editorial_engine_v1 import verify_manifest
    import scripts.pulse_editorial_engine_v1 as editorial

    from scripts.pulse_cloudflare_llama import (
        BUDGET_NEURONS, configure_environment, reserved_neurons
    )
    output = Path(output_dir)
    made = []
    reserved = 0.0
    # Never reuse an unrelated key or the retired Tommy Worker.
    if not configure_environment():
        return {"status": "cloudflare_not_configured", "generated": []}
    for manifest_path in sorted(Path(manifests_dir).glob("*.json"))[:max(1, min(limit, 20))]:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        spec = verify_manifest(manifest)
        semantic = spec["semantic_columns"]
        country_col = semantic["territory"]
        territory = spec["dimensions"][country_col].casefold()
        if territory != "italia" and territory not in REGIONS:
            raise ValueError("outside_italy_manifest:" + manifest_path.name)
        if not italian_official_url(manifest["source_url"]) or not italian_official_url(manifest["dataset_url"]):
            raise ValueError("non_italian_primary_source:" + manifest_path.name)
        evidence_path = output / (manifest_path.stem + ".evidence.json")
        draft_path = output / (manifest_path.stem + ".draft.json")
        editorial.run_extract(argparse.Namespace(
            manifest=str(manifest_path), source_file=None, output=str(evidence_path)
        ))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        reservation = reserved_neurons(editorial.ai_prompt(evidence))
        if reserved + reservation > BUDGET_NEURONS:
            break  # Keep headroom below Cloudflare's 10,000 daily free Neurons.
        reserved += reservation  # Reserve even if the model's JSON is rejected.
        try:
            editorial.run_draft(argparse.Namespace(
                evidence=str(evidence_path), proposal_file=None, output=str(draft_path)
            ))
            made.append(str(draft_path))
        except ValueError:
            # Rejected drafts stay visible as artifacts, never enter production.
            continue
    return {"status": "draft_only", "generated": made, "count": len(made),
            "neuron_reservation_for_run": round(reserved, 2),
            "budget_neurons_for_run": BUDGET_NEURONS,
            "budget_estimate_only": True}


def main(argv=None):
    p = argparse.ArgumentParser(description="PULSE Italia research queue + audited draft generation")
    sub = p.add_subparsers(dest="mode", required=True)
    rank = sub.add_parser("rank")
    rank.add_argument("--articles", required=True)
    rank.add_argument("--output", required=True)
    rank.add_argument("--limit", type=int, default=20)
    rank.set_defaults(run=lambda a: print(json.dumps(
        prepare_queue(a.articles, a.output, a.limit)["by_topic"], ensure_ascii=False)))
    draft = sub.add_parser("draft")
    draft.add_argument("--manifests-dir", required=True)
    draft.add_argument("--output-dir", required=True)
    draft.add_argument("--limit", type=int, default=20)
    draft.set_defaults(run=lambda a: print(json.dumps(generate_verified_drafts(
        a.manifests_dir, a.output_dir, a.limit), ensure_ascii=False)))
    a = p.parse_args(argv)
    a.run(a)


if __name__ == "__main__":
    main()
