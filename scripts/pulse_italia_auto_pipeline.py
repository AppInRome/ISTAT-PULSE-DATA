#!/usr/bin/env python3
"""PULSE Italia end-to-end RESEARCH: official discovery -> numeric evidence ->
analyst + dstory + inspector -> optional Llama -> audited drafts -> review queue.

This script does not equate an automated numeric audit with human editorial
approval. Publication of a long-form news feature is a separate reviewed step.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError

from scripts import pulse_italia_official_discovery as official
from scripts import pulse_data_story_stack as storytelling
from scripts import pulse_editorial_engine_v1 as engine
from scripts import pulse_editorial_audit_v1 as audit
from scripts.pulse_cloudflare_llama import (
    BUDGET_NEURONS, configure_environment, reserved_neurons
)

UTC = timezone.utc


def save(path, payload):
    engine.write_json(path, payload)


def evidence_id(e):
    """Stable for *one publication/series/period*, changes on source revision."""
    s = e["series"]
    identity = (e["dataset_url"], s["indicator"], s["territory"],
                s["observations"][-1]["period"], e["source_sha256"])
    return sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:20]


def run_data_tools(e, destination, data_analyst_script=None,
                   dstory_command=None, data2story_root=None):
    """Execute real open-source tools; keep full source and chart data linked."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    csv_path = destination / "verified_observations.csv"
    storytelling.exact_verified_csv(e, csv_path)
    outcome = {}
    # External programs are independent; a rendering problem must never alter
    # numeric evidence or permit a publication without the missing component.
    for name, action in [
        ("data_analyst", lambda: storytelling.run_data_analyst(
            data_analyst_script, csv_path, destination / "data_analyst",
            e["series"]["indicator"] + " — Italia")),
        ("dstory", lambda: storytelling.run_dstory(
            dstory_command, csv_path, destination / "dstory", e["dataset_url"])),
    ]:
        try:
            outcome[name] = action()
        except (RuntimeError, OSError, ValueError) as exc:
            outcome[name] = {"status": "failed", "type": type(exc).__name__}
    trace = storytelling.source_trace(e, None, destination / "data2story_trace")
    try:
        outcome["data2story_inspector"] = storytelling.run_data2story_inspector(
            data2story_root, trace)
    except (RuntimeError, OSError, ValueError) as exc:
        outcome["data2story_inspector"] = {"status": "failed", "type": type(exc).__name__}
    return outcome


def audit_draft(e, proposal):
    if not isinstance(proposal, dict) or proposal.get("insufficient_evidence"):
        return None, {"status": "insufficient_evidence"}
    draft = {name: proposal.get(name) for name in ("title", "lead", "paragraphs")}
    draft.update({"evidence_sha256": audit.digest(e),
                  "source_url": e["source_url"], "dataset_url": e["dataset_url"],
                  "publication_status": "draft", "editorial_status": "draft_only"})
    report = audit.audit(draft, e)
    draft["audit"] = report
    return draft, {"status": "audited_draft" if report.get("passed") else "rejected",
                   "issues": report.get("issues", [])}


def build_preview(e, draft=None):
    """Full article + exact graphic/table values, but explicitly NOT published."""
    s = e["series"]
    obs = s["observations"][-12:]
    result = {
        "schema_version": 1, "publication_status": "draft",
        "editorial_status": "requires_human_semantic_review",
        "publisher": e["publisher"], "topic": e["topic"], "country_code": "IT",
        "geographic_scope": {"country_code": "IT", "territory": s["territory"]},
        "headline": (draft.get("title") if draft else None) or s["indicator"],
        "summary": (draft.get("lead") if draft else None)
                   or ("Serie ufficiale: %s (%s); ultimi periodi %s e %s." %
                       (s["indicator"], s["unit"], obs[-2]["period"], obs[-1]["period"])),
        "pulse_article_body": [
            {"heading": "", "text": p} for p in (draft.get("paragraphs") or [])
        ] if draft else [],
        "public_source": {"url": e["source_url"],
                          "role": "primary_statistical_source"},
        "chart_spec": {"status": "verified", "type": "line" if len(obs) > 2 else "bar",
                       "title": s["indicator"], "unit": s["unit"],
                       "source_url": e["dataset_url"], "x_axis": "Periodo",
                       "y_axis": s["unit"],
                       "data": [{"period": r["period"], "value": float(r["value"])}
                                for r in obs]},
        "table_spec": {"status": "verified",
                       "source_url": e["dataset_url"],
                       "headers": ["Periodo", s["indicator"] + " (" + s["unit"] + ")"],
                       "rows": [[r["period"], float(r["value"])] for r in obs]},
        "verification_tier": "verified_comparable_series",
        "verified_series": [{
            "indicator": s["indicator"], "unit": s["unit"],
            "source_url": e["source_url"], "verified": True,
            "extraction_method": "sdmx_xml_explicit_series_dimensions"
            if str(e["extraction_method"]).startswith("sdmx_")
            else "exact_classification_long_format_row",
            "observations": [{"period": r["period"], "value": float(r["value"]),
                              "raw": r.get("raw", r["value"])} for r in obs]}],
        "source_documents": [{"url": e["dataset_url"], "sha256": e["source_sha256"],
                              "extraction_method": e["extraction_method"]}],
        "review_required": True,
        "publishable_without_review": False,
    }
    return result


def run_pipeline(output_dir, max_sources=3, discovery_fn=None, ai_enabled=True,
                 data_analyst_script=None, dstory_command=None,
                 data2story_root=None, now=None):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    sources, report = ((discovery_fn or official.discover)())
    now = now or datetime.now(UTC)
    budget = 0.0
    can_ai = bool(ai_enabled and configure_environment())
    results = []
    for evidence in sources[:max(0, min(max_sources, 3))]:
        ident = evidence_id(evidence)
        folder = output / ident
        folder.mkdir(parents=True, exist_ok=True)
        save(folder / "evidence.json", evidence)
        components = run_data_tools(evidence, folder,
                                    data_analyst_script, dstory_command,
                                    data2story_root)
        # Nothing may be marked publication-ready if external validation failed.
        all_tools_ok = all(c.get("status") == "completed" for c in components.values())
        draft, status = None, {"status": "ai_disabled"}
        if can_ai:
            estimate = reserved_neurons(engine.ai_prompt(evidence))
            if budget + estimate > BUDGET_NEURONS:
                status = {"status": "daily_budget_estimate_exceeded"}
            else:
                budget += estimate
                try:
                    proposed = engine.call_model(evidence)
                    draft, status = audit_draft(evidence, proposed)
                    if draft:
                        save(folder / "llama_draft.json", draft)
                except (ValueError, TypeError, KeyError, OSError, URLError,
                        HTTPError, json.JSONDecodeError) as exc:
                    status = {"status": "ai_unavailable_or_invalid",
                              "error_type": type(exc).__name__}
        save(folder / "preview.json", build_preview(
            evidence, draft if status.get("status") == "audited_draft" else None))
        review = {
            "review_status": "pending_human_signoff",
            "id": ident, "publication_allowed": False,
            "source_sha256": evidence["source_sha256"],
            "evidence_sha256": audit.digest(evidence),
            "draft_sha256": audit.digest({k: v for k, v in draft.items()
                                          if k != "audit"}) if draft else None,
            "data_components": components, "llama": status,
        }
        save(folder / "review_required.json", review)
        results.append({"id": ident, "source": evidence["publisher"],
                        "indicator": evidence["series"]["indicator"],
                        "period": evidence["series"]["observations"][-1]["period"],
                        "valid_values": len(evidence["series"]["observations"]),
                        "graph_and_table": True,
                        "all_external_tools_complete": all_tools_ok,
                        "llama": status["status"], "article_published": False,
                        "preview": str(folder / "preview.json")})
    index = {
        "generated_at": now.isoformat(), "scope": "IT",
        "official_discovery": report, "results": results,
        "candidate_articles": len(results), "published_articles": 0,
        "reserved_neurons_estimate": round(budget, 2),
        "budget_limit_estimate": BUDGET_NEURONS,
        "requires_human_editorial_review": True,
    }
    save(output / "pipeline_report.json", index)
    return index


def main(argv=None):
    p = argparse.ArgumentParser(description="Discover official data, create verified figures and Llama drafts")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-sources", type=int, default=3)
    p.add_argument("--no-ai", action="store_true")
    p.add_argument("--data-analyst-script")
    p.add_argument("--dstory-command")
    p.add_argument("--data2story-root")
    args = p.parse_args(argv)
    result = run_pipeline(
        output_dir=args.output_dir, max_sources=args.max_sources,
        ai_enabled=not args.no_ai,
        data_analyst_script=args.data_analyst_script,
        dstory_command=args.dstory_command,
        data2story_root=args.data2story_root)
    print(json.dumps({"candidates": result["candidate_articles"],
                      "published": 0, "ai_budget_reserved_estimate": result["reserved_neurons_estimate"],
                      "discovery_checks": len(result["official_discovery"]["sources_considered"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
