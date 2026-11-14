#!/usr/bin/env python3
"""PULSE Editorial Architecture 2: independent, source-led, AI-free newsroom gate.

Reads real verified evidence bundles created by existing ISTAT/INPS discovery.
Creates accountable editorial briefs, deterministic graph/table validation and
a review queue. It does NOT generate prose, consume AI credits or publish.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from scripts import pulse_editorial_audit_v1 as audit
from scripts import pulse_italia_chart_analytics as chart
from scripts import pulse_italia_official_discovery as official
from scripts.pulse_italia_newsroom import italian_official_url

SCHEMA = "pulse_editorial_architecture_v2"
MAX_DAILY_TARGET = 30


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def identity(evidence):
    series = evidence["series"]
    fields = [evidence["dataset_url"], series["indicator"],
              series["territory"], series["observations"][-1]["period"]]
    return sha256(canonical(fields).encode("utf-8")).hexdigest()[:24]


def safe_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def check_evidence(evidence):
    problems = []
    if not isinstance(evidence, dict):
        return ["invalid_evidence"], None
    series = evidence.get("series")
    if evidence.get("verified") is not True:
        problems.append("source_not_verified")
    if not all(italian_official_url(evidence.get(field)) for field in ("source_url", "dataset_url")):
        problems.append("official_italian_source_missing")
    if not isinstance(evidence.get("source_sha256"), str) or len(evidence["source_sha256"]) != 64:
        problems.append("missing_source_sha256")
    if not isinstance(series, dict):
        return problems + ["invalid_series"], None
    if not all(str(series.get(k) or "").strip() for k in
               ("indicator", "territory", "population", "frequency", "unit")):
        problems.append("missing_statistical_dimensions")
    try:
        views = chart.calculate(series)
    except (ValueError, TypeError, KeyError, IndexError, ArithmeticError):
        problems.append("unverifiable_numerical_series")
        views = None
    return problems, views


def verify_preview(preview, evidence, analytics):
    """Fail closed if chart, table or derived views diverge from original values."""
    problems = []
    if not isinstance(preview, dict):
        return ["missing_preview"]
    if preview.get("publishable_without_review") is not False:
        problems.append("unsafe_publication_flag")
    source = preview.get("chart_spec") or {}
    table = preview.get("table_spec") or {}
    # Android previews intentionally expose the last 24 original data points.
    original = evidence["series"]["observations"][-24:]
    expected = [(str(p["period"]), float(p["value"]))
                for p in original]
    actual = [(str(p["period"]), float(p["value"]))
              for p in source.get("data", [])] if isinstance(source.get("data"), list) else []
    rows = table.get("rows")
    tabulated = [(str(p[0]), float(p[1])) for p in rows] if isinstance(rows, list) and all(isinstance(p,list) and len(p) == 2 for p in rows) else []
    if actual != expected:
        problems.append("chart_differs_from_verified_observations")
    if tabulated != expected:
        problems.append("table_differs_from_verified_observations")
    preview_analytics = chart.calculate({
        **evidence["series"], "observations": original
    })
    if preview.get("chart_analyses") != preview_analytics:
        problems.append("derived_graphs_do_not_match_recalculation")
    if preview.get("publication_status") not in ("draft", "not_published"):
        problems.append("preview_claims_publication")
    return problems


def build_brief(evidence, analytics):
    series = evidence["series"]
    obs = series["observations"]
    first, last = obs[0], obs[-1]
    return {
        "statistical_subject": series["indicator"],
        "territory": series["territory"],
        "population": series["population"],
        "frequency": series["frequency"],
        "measurement_unit": series["unit"],
        "first_observation": {"period": first["period"], "value": first["value"]},
        "latest_observation": {"period": last["period"], "value": last["value"]},
        "observations_count": len(obs),
        "possible_story_structure": [
            "Il fatto: ultimo periodo realmente disponibile, senza inventare la data di uscita",
            "Il confronto: solo differenze calcolate da periodi effettivamente comparabili",
            "Il contesto: definizioni e popolazione della serie originale",
            "Limiti e cautele: distinguere misure da interpretazioni e cause non dimostrate",
        ],
        "visualizations_available": [
            {"view_id": view["id"], "label": view["label"],
             "usable_points": view["usable_points"], "graph_types": view["graph_types"]}
            for view in analytics["views"]
        ],
        "source": {
            "publisher": evidence.get("publisher"),
            "release_url": evidence["source_url"],
            "dataset_url": evidence["dataset_url"],
            "methodology_url": evidence.get("methodology_url"),
            "source_sha256": evidence["source_sha256"],
            "evidence_sha256": audit.digest(evidence),
        },
        "publication_date_not_inferred_from_statistical_period": True,
        "no_model_generated_claims": True,
    }


def prepare(review_root, output_dir, headline_file=None, published_store=None, target=30, now=None):
    review_root, output_dir = Path(review_root), Path(output_dir)
    now = now or datetime.now(timezone.utc)
    if target < 1 or target > MAX_DAILY_TARGET:
        raise ValueError("target_must_be_between_1_and_30")
    published = set()
    if published_store and Path(published_store).exists():
        for item in safe_json(published_store).get("articles", []):
            if not isinstance(item, dict):
                continue
            if item.get("story_identity"):
                published.add(str(item["story_identity"]))
                continue
            # Older PULSE approved articles predate the v2 story identity.
            # Recover it from the exact verified dataset, indicator, territory and period.
            try:
                source = item["source_documents"][0]["url"]
                series = item["verified_series"][0]
                period = item["chart_spec"]["data"][-1]["period"]
                territory = item["geographic_scope"]["territory"]
                fields = [source, series["indicator"], territory, period]
                published.add(sha256(canonical(fields).encode("utf-8")).hexdigest()[:24])
            except (KeyError, IndexError, TypeError, ValueError):
                pass
    headlines = {}
    if headline_file and Path(headline_file).exists():
        doc = safe_json(headline_file)
        headlines = {"selected_leads": len(doc.get("selected", []) if isinstance(doc.get("selected"), list) else []),
                     "selection_report_present": True}
    accepted, excluded, seen = [], [], set()
    for folder in sorted(review_root.iterdir()) if review_root.is_dir() else []:
        if not folder.is_dir():
            continue
        efile, pfile, rfile = [folder / name for name in
                                ("evidence.json", "preview.json", "review_required.json")]
        if not all(p.is_file() for p in (efile, pfile, rfile)):
            excluded.append({"bundle": folder.name, "reasons": ["incomplete_research_bundle"]})
            continue
        try:
            e, preview, review = safe_json(efile), safe_json(pfile), safe_json(rfile)
            reasons, analytics = check_evidence(e)
            if analytics is not None:
                reasons.extend(verify_preview(preview, e, analytics))
            if (review.get("publication_allowed") is not False or
                    review.get("review_status") != "pending_human_signoff" or
                    review.get("evidence_sha256") != audit.digest(e)):
                reasons.append("missing_independent_review_lock")
            components = review.get("data_components")
            if not (isinstance(components, dict) and len(components) >= 3
                    and all(isinstance(c, dict) and c.get("status") == "completed"
                            for c in components.values())):
                reasons.append("independent_analytics_incomplete")
            key = identity(e) if not reasons else None
            if key in seen and key is not None:
                reasons.append("duplicate_statistical_story")
            if key in published and key is not None:
                reasons.append("already_published_story")
            if reasons:
                excluded.append({"bundle": folder.name, "reasons": sorted(set(reasons))})
                continue
            seen.add(key)
            entry = {
                "story_identity": key,
                "bundle_id": folder.name,
                "editorial_stage": "verified_data_pending_ai_and_human_review",
                "eligible_for_ai": True,
                "publish_allowed": False,
                "topic": official.official_topic(e["series"]["indicator"]),
                "evidence_sha256": audit.digest(e),
                "brief": build_brief(e, analytics),
                "not_yet_an_article": True,
            }
            accepted.append(entry)
        except (ValueError, TypeError, KeyError, IndexError, OSError, ArithmeticError, json.JSONDecodeError) as exc:
            excluded.append({"bundle": folder.name,
                             "reasons": ["invalid_research_bundle_" + type(exc).__name__]})
    # Round-robin topics to avoid filling the whole feed with one discipline.
    # Do not claim data period order is a news release timestamp.
    topics = defaultdict(list)
    for story in accepted:
        topics[story["topic"]].append(story)
    pools = {topic: deque(sorted(items, key=lambda x: x["story_identity"]))
             for topic, items in topics.items()}
    queue = []
    while len(queue) < target and any(pools.values()):
        for topic in sorted(pools):
            if pools[topic] and len(queue) < target:
                queue.append(pools[topic].popleft())
    for item in queue:
        atomic_json(output_dir / "briefs" / (item["story_identity"] + ".json"), item)
    report = {
        "schema_version": SCHEMA, "generated_at": now.isoformat(),
        "daily_article_target": target, "target_is_not_a_publication_guarantee": True,
        "research_bundles_checked": len(accepted) + len(excluded),
        "verified_numeric_story_candidates": len(accepted),
        "briefs_prepared_for_ai": len(queue),
        "not_written_due_to_lack_of_verified_sources": max(0, target-len(queue)),
        "excluded": excluded, "by_topic": dict(Counter(a["topic"] for a in queue)),
        "source_leads": headlines, "ai_calls": 0, "ai_spend_usd": 0,
        "automatically_published": 0,
        "publication_requires_human_review": True,
        "status": "ready_for_editorial_review" if queue else "no_eligible_verified_numeric_stories",
    }
    atomic_json(output_dir / "editorial_architecture_report.json", report)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description="Verify official statistical evidence and prepare source-led PULSE briefs; never use AI")
    p.add_argument("--review-root", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--headline-file")
    p.add_argument("--published-store", default="data/editorial_italia/published_articles.json")
    p.add_argument("--daily-target", type=int, default=30)
    a = p.parse_args(argv)
    result = prepare(a.review_root, a.output_dir, a.headline_file, a.published_store, a.daily_target)
    print(json.dumps({"status": result["status"], "candidates": result["briefs_prepared_for_ai"],
                      "target": result["daily_article_target"], "invented_articles": 0},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
