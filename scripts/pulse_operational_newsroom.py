#!/usr/bin/env python3
"""Operational PULSE newsroom: discover -> analyze/chart/table -> AI drafts ->
human review -> publish into the SAME news JSON read by Android.

Source discovery is automatic; publication is strictly approved-only.
Runs on GitHub Actions after this feature branch is merged to main.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from scripts import pulse_editorial_engine_v1 as engine
from scripts import pulse_editorial_audit_v1 as audit
from scripts.pulse_cloudflare_llama import (
    BUDGET_NEURONS, configure_environment, reserved_neurons
)
from scripts.pulse_data_story_stack import (
    exact_verified_csv, run_data_analyst, run_dstory,
    run_data2story_inspector, source_trace
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    engine.write_json(str(path), value)


def analyze_verified(evidence_path, output_dir, *, data_analyst_script=None,
                     dstory_command=None, data2story_root=None, allow_llama=True,
                     neuron_remaining=BUDGET_NEURONS):
    evidence = read_json(evidence_path)
    if evidence.get("verified") is not True or not evidence.get("auto_discovered"):
        raise ValueError("requires_auto_discovered_verifiable_primary_series")
    series = evidence["series"]
    if series["territory"].casefold() != "italia" and not series["territory"]:
        raise ValueError("not_italian_series")
    observations = series["observations"]
    if len(observations) < 2:
        raise ValueError("insufficient_comparable_observations")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tabular = output_dir / "verified_table.csv"
    exact_verified_csv(evidence, tabular)
    status = {
        "data_analyst": run_data_analyst(
            data_analyst_script, tabular, output_dir / "analysis", series["indicator"]),
        "dstory": run_dstory(
            dstory_command, tabular, output_dir / "data_story", evidence["dataset_url"]),
    }
    draft = None
    model_status = "disabled"
    booked = 0.0
    if allow_llama and configure_environment():
        booked = reserved_neurons(engine.ai_prompt(evidence))
        if booked <= neuron_remaining:
            model_status = "attempted"
            try:
                proposed = engine.call_model(evidence)
                if isinstance(proposed, dict) and proposed.get("insufficient_evidence"):
                    model_status = "model_says_not_enough_evidence"
                elif isinstance(proposed, dict):
                    candidate = {key: proposed.get(key) for key in ("title", "lead", "paragraphs")}
                    candidate.update({
                        "evidence_sha256": audit.digest(evidence),
                        "source_url": evidence["source_url"],
                        "dataset_url": evidence["dataset_url"],
                        "editorial_status": "draft_only",
                        "publication_status": "draft",
                    })
                    candidate["audit"] = audit.audit(candidate, evidence)
                    if candidate["audit"]["passed"]:
                        draft = candidate
                        model_status = "audited_draft_requires_editor"
                        write_json(output_dir / "draft.json", draft)
                    else:
                        model_status = "draft_rejected_by_numeric_audit"
                        write_json(output_dir / "rejected_draft.json", candidate)
            except (ValueError, KeyError, TypeError, TimeoutError, OSError,
                    json.JSONDecodeError) as exc:
                model_status = "model_request_or_format_error:" + type(exc).__name__
        else:
            booked = 0.0
            model_status = "cloudflare_budget_reached"
    elif allow_llama:
        model_status = "cloudflare_credentials_not_set"

    trace_dir = source_trace(evidence, draft, output_dir / "evidence_report")
    status["data2story"] = run_data2story_inspector(data2story_root, trace_dir)
    result = {
        "source_url": evidence["source_url"],
        "dataset_url": evidence["dataset_url"],
        "data_sha256": evidence["dataset_bytes_sha256"],
        "series": {"indicator": series["indicator"], "territory": series["territory"],
                   "periods": len(observations), "unit": series["unit"]},
        "table_csv": str(tabular),
        "graph_and_table_prepared": True,
        "components": status,
        "llama": model_status,
        "neuron_reservation_estimate": round(booked, 2),
        "publication_status": "unpublished_research",
    }
    write_json(output_dir / "result.json", result)
    return result


def run_batch(discovery_dir, output_dir, limit=12, **kwargs):
    source = Path(discovery_dir) / "evidence"
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    used = 0.0
    results = []
    for evidence in sorted(source.glob("*.json"))[:max(1, min(limit, 20))]:
        try:
            item = analyze_verified(evidence, output / evidence.stem,
                                    neuron_remaining=max(0, BUDGET_NEURONS - used),
                                    **kwargs)
            used += item["neuron_reservation_estimate"]
            results.append({"id": evidence.stem, **item})
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
            results.append({"id": evidence.stem, "status": "rejected",
                            "reason": type(exc).__name__})
    summary = {
        "checked": len(results),
        "drafts_accepted_for_review": sum(
            x.get("llama") == "audited_draft_requires_editor" for x in results),
        "all_results": results,
        "cloudflare_estimated_neurons_reserved": round(used, 2),
        "auto_published": 0,
    }
    write_json(output / "batch_status.json", summary)
    return summary


def approve_and_merge(approved_dir, articles_path, index_path):
    """Only explicitly reviewed bundles can enter the app's existing feeds."""
    articles = read_json(articles_path)
    index = read_json(index_path)
    count = 0
    for path in sorted(Path(approved_dir).glob("*.json")) if Path(approved_dir).exists() else []:
        casefile = read_json(path)
        if set(casefile) != {"evidence", "draft", "approval"}:
            raise ValueError("review_casefile_requires_evidence_draft_approval")
        evidence = casefile["evidence"]
        draft = casefile["draft"]
        approval = casefile["approval"]
        if evidence.get("auto_discovered") is not True or not evidence.get("verified"):
            raise ValueError("unverified_auto_discovery_in_approved_dir")
        article = engine.publish_article(draft, evidence, approval)
        articles, index = engine.merge_feeds(article, articles, index)
        count += 1
    return articles, index, count


def main(argv=None):
    p = argparse.ArgumentParser(description="PULSE official data newsroom")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--discovery-dir", required=True)
    a.add_argument("--output-dir", required=True)
    a.add_argument("--limit", type=int, default=12)
    a.add_argument("--data-analyst-script")
    a.add_argument("--dstory-command")
    a.add_argument("--data2story-root")
    a.add_argument("--no-ai", action="store_true")
    z = sub.add_parser("publish-approved")
    z.add_argument("--approvals-dir", required=True)
    z.add_argument("--articles", required=True)
    z.add_argument("--index", required=True)
    args = p.parse_args(argv)
    if args.cmd == "analyze":
        outcome = run_batch(
            args.discovery_dir, args.output_dir, args.limit,
            data_analyst_script=args.data_analyst_script,
            dstory_command=args.dstory_command,
            data2story_root=args.data2story_root, allow_llama=not args.no_ai)
        print(json.dumps({"checked": outcome["checked"],
                          "drafts_accepted_for_review": outcome["drafts_accepted_for_review"],
                          "auto_published": 0}, ensure_ascii=False))
    else:
        articles, index, count = approve_and_merge(
            args.approvals_dir, args.articles, args.index)
        if count:
            write_json(args.articles, articles)
            write_json(args.index, index)
        print(json.dumps({"approved_articles_merged_into_android_feed": count}))


if __name__ == "__main__":
    main()
