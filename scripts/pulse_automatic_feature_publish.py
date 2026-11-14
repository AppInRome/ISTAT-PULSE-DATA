#!/usr/bin/env python3
"""Publish a separate, rigorously checked, AI-FREE PULSE statistical features feed.

This is not the human-approved AI editor: it is an explicitly labelled
automatic bulletin built solely from authenticated numerical observations.
All PULSE media reports stay in the existing news feed. Never copies
copyrighted newspaper articles, fabricates charts, or self-approves AI copy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from scripts import pulse_editorial_audit_v1 as audit
from scripts import pulse_headline_editor as headline_editor
from scripts import pulse_regional_editing as regional
from scripts import pulse_editorial_selector as selector
from scripts import pulse_story_composer as composer
from scripts import pulse_editorial_architecture_v2 as verify
from scripts.pulse_italia_newsroom import italian_official_url

SCHEMA = "pulse-automatic-official-features-v1"
MAX_FEED_ENTRIES = 1200


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stable_id(evidence):
    s = evidence["series"]
    identity = [evidence["dataset_url"], s["indicator"], s["territory"],
                s["observations"][-1]["period"]]
    return "PULSE-DATA-" + sha256(verify.canonical(identity).encode()).hexdigest()[:24].upper()


def validated_article(folder, published_at):
    folder = Path(folder)
    evidence, preview, draft, review = (
        read_json(folder / filename) for filename in
        ("evidence.json", "preview.json", "deterministic_draft.json", "review_required.json"))
    errs, analytics = verify.check_evidence(evidence)
    if analytics is None:
        raise ValueError("numeric_evidence_incomplete")
    errs += verify.verify_preview(preview, evidence, analytics)
    if errs:
        raise ValueError("invalid_numeric_evidence:" + ",".join(errs))
    if not italian_official_url(evidence["source_url"]) or not italian_official_url(evidence["dataset_url"]):
        raise ValueError("non_official_origin")
    components = review.get("data_components") or {}
    if (components.get("data_analyst", {}).get("status") != "completed"
            or components.get("data2story_inspector", {}).get("status") != "completed"
            or components.get("dstory", {}).get("status") not in ("completed", "verified_fallback")):
        raise ValueError("independent_data_tools_incomplete")
    if (components["dstory"].get("status") == "verified_fallback"
            and components["dstory"].get("chart_engine") != "pulse_italia_chart_analytics.calculate"):
        raise ValueError("faked_renderer_fallback")
    if review.get("evidence_sha256") != audit.digest(evidence):
        raise ValueError("review_evidence_hash_mismatch")
    if review.get("draft_origin") != "deterministic_no_ai":
        raise ValueError("not_deterministically_written")
    if draft.get("writer") != "historical_PULSE_deterministic_restored_v1":
        raise ValueError("unknown_deterministic_writer")
    if review.get("draft_sha256") != audit.digest({k:v for k,v in draft.items() if k!="audit"}):
        raise ValueError("draft_hash_changed")
    checked = audit.audit(draft, evidence)
    if not checked["passed"]:
        raise ValueError("independent_numeric_audit_failed:" + ",".join(checked["issues"]))
    if draft.get("audit") != checked:
        raise ValueError("writer_audit_changed")
    if (preview.get("headline") != draft["title"]
            or preview.get("summary") != draft["lead"]
            or [p.get("text") for p in preview.get("pulse_article_body", [])] != draft["paragraphs"]):
        raise ValueError("article_preview_changed")
    observations = evidence["series"]["observations"][-24:]
    if len(observations) < 2 or len(observations) > 24:
        raise ValueError("chart_out_of_mobile_range")
    source = evidence["source_url"]
    s = evidence["series"]
    # APK supports the internal extraction mechanism only after an explicit allowlist update.
    method = evidence.get("extraction_method") or ""
    if method not in {
        "sdmx_original_XML_series_key_and_observation",
        "original_inps_csv_fixed_classification_rows",
        "sdmx_xml_explicit_series_dimensions",
        "exact_classification_long_format_row",
        "sdmx_csv_explicit_dimensions",
        "sdmx_flat_json_explicit_dimensions",
        "sdmx_json_indexed_resolved_dimensions",
        "eurostat_jsonstat2_exact_multidimensional_cell",
        "same_row_explicit_year_html_table",
        "same_row_explicit_year_structured_table",
    }:
        raise ValueError("extraction_method_not_supported_by_mobile")
    if len(str(evidence["source_sha256"])) != 64:
        raise ValueError("source_fingerprint_invalid")
    item = {
        "id": stable_id(evidence),
        "published_at": published_at,
        "first_published_at_utc": published_at,
        "headline": draft["title"],
        "summary": draft["lead"],
        "pulse_title": draft["title"],
        "pulse_summary": draft["lead"],
        "pulse_article_body": [{"heading":"", "text":p} for p in draft["paragraphs"]],
        "topic": evidence.get("topic", "ALTRO"),
        "territories": [s["territory"].casefold()],
        "pulse_score": 0,
        "patterns": [],
        "public_source": {"url":source, "domain":evidence["publisher"],
                          "role":"primary_statistical_source",
                          "verification_method":"official_dataset_sha256_and_deterministic_arithmetic_audit",
                          "verification_score":100},
        "source_documents":[{"url":evidence["dataset_url"],"sha256":evidence["source_sha256"]}],
        "verified_series_relevant": [{
            "indicator":s["indicator"], "unit":s["unit"], "verified": True,
            "territory":s["territory"], "population":s["population"],
            "extraction_method":method,"source_url":source,
            "observations":[{"period":r["period"],"value":float(r["value"]),"raw":str(r.get("raw",r["value"]))}
                            for r in observations]
        }],
        "chart_spec":preview["chart_spec"],
        "table_spec":preview["table_spec"],
        "editorial_format":"deterministic_source_locked_auto_audited",
        "editorial_status":"automatically_audited_official_numbers",
        "publication_tier":"verified_official_deterministic",
        "publication_status":"published",
        "editorial_method":"original_pulse_deterministic_from_official_data_no_ai",
        "byline":"PULSE — bollettino statistico automatico",
        "automatic_review":{
            "schema":SCHEMA,"passed":True,
            "audit":"recomputed_against_primary_series",
            "evidence_sha256":audit.digest(evidence),
            "original_source_sha256":evidence["source_sha256"],
            "model_used":False,"human_editorial_approval":False,
        },
        "period_reference":observations[-1]["period"],
    }
    # All checks and the signed draft are completed BEFORE this display-only
    # two-field adapter. The original draft, charts and audit are untouched.
    return headline_editor.with_editorial_headline(item)


def publish(review_root, output_file, now=None, *, smart=False,
            versions_file=None, frontpage_file=None):
    review_root, output_file = Path(review_root), Path(output_file)
    now = now or utc_now()
    old = read_json(output_file) if output_file.exists() else {}
    previous = old.get("articles", [])
    if smart and (versions_file is None or frontpage_file is None):
        raise ValueError("smart_mode_requires_both_persistent_files")
    versions_file = Path(versions_file) if versions_file is not None else None
    frontpage_file = Path(frontpage_file) if frontpage_file is not None else None
    old_versions = read_json(versions_file) if smart and versions_file.exists() else {}
    old_frontpage = read_json(frontpage_file) if smart and frontpage_file.exists() else {}
    if not isinstance(previous,list):
        raise ValueError("malformed_existing_feed")
    accepted = {r["id"]:r for r in previous if isinstance(r,dict)
                and isinstance(r.get("id"),str) and r.get("id","").startswith("PULSE-DATA-")}
    # One-time, idempotent update of already published technical headings.
    # All unchanged article content, images, graphics, timestamps and IDs
    # remain exactly as they were in the persisted feed.
    retitled = 0
    for key, old_item in list(accepted.items()):
        updated = headline_editor.with_editorial_headline(old_item)
        if updated is not old_item:
            accepted[key] = updated
            retitled += 1
    checked = rejected = added = 0
    verified_pairs = []
    prospective = []
    for folder in sorted(review_root.iterdir()) if review_root.is_dir() else []:
        if not folder.is_dir():
            continue
        checked += 1
        try:
            item = validated_article(folder, now)
            evidence = read_json(folder / "evidence.json")
        except (KeyError, IndexError, TypeError, ValueError, OSError, json.JSONDecodeError):
            rejected += 1
            continue
        if smart:
            # Selection uses verified evidence only, after all audits, but
            # BEFORE a new article enters the permanent published feed.
            prospective.append((item,evidence))
        else:
            if item["id"] not in accepted:
                accepted[item["id"]] = item
                added += 1
            verified_pairs.append((accepted[item["id"]], evidence))
    frontpage, ledger = None, None
    approved_ids = set()
    context_ids = set()
    selected_stats = {}
    if smart:
        frontpage, ledger, selected_stats = selector.evaluate(
            prospective, previous, old_versions, old_frontpage, now)
        context_ids = set(frontpage["context_analyses_new"])
        approved_ids = set(frontpage["featured_article_ids"]) | context_ids
        for item, evidence in prospective:
            if item["id"] in accepted:
                verified_pairs.append((accepted[item["id"]], evidence))
            elif item["id"] in approved_ids:
                if item["id"] in context_ids:
                    # PULSE publishes original background analysis now;
                    # its source observations are NOT newly released news.
                    period = str(item["period_reference"])
                    notice = ("Analisi di contesto PULSE sui dati ufficiali "
                              "riferiti al periodo " + period
                              + "; non segnala una nuova pubblicazione dell'ente.")
                    item = {**item,
                            "editorial_kind":"verified_context_analysis",
                            "editorial_context_notice":notice,
                            "publication_tier":"verified_official_context_not_new_release",
                            "byline":"PULSE — approfondimento statistico di contesto",
                            "summary":notice+" "+item["summary"],
                            "pulse_summary":notice+" "+item["pulse_summary"]}
                accepted[item["id"]] = item
                verified_pairs.append((item, evidence))
                added += 1
        # Never expose a featured ID that was not actually published.
        frontpage["featured_article_ids"] = [
            id_ for id_ in frontpage["featured_article_ids"] if id_ in accepted]
        frontpage["features_new"] = [
            id_ for id_ in frontpage["features_new"] if id_ in accepted]
        frontpage["context_analyses_new"] = [
            id_ for id_ in frontpage["context_analyses_new"] if id_ in accepted]
    # The writer, chart renderer and independent audit have already finished.
    # Add only a safe optional presentation object; never overwrite original
    # article prose, titles, source metadata, graph or table values.
    story_updated = 0
    for key, current_item in list(accepted.items()):
        enriched = composer.attach(current_item)
        if enriched is not current_item:
            accepted[key] = enriched
            story_updated += 1
    old_digest = old.get("regional_editorial")
    digest = regional.build_digest(verified_pairs, old_digest, now)
    digest_changed = regional.canonical(digest) != regional.canonical(
        old_digest if isinstance(old_digest, dict) else {})
    # Do NOT change the generation timestamp or create a new Git commit
    # when the source series and the published article IDs are unchanged.
    # Otherwise a daily noop races with the radar or unrelated PR merges.
    frontpage_changed = bool(smart and (
        not frontpage_file.exists() or
        {k:v for k,v in frontpage.items() if k!="generated_at"} !=
        {k:v for k,v in old_frontpage.items() if k!="generated_at"} or
        str(old_frontpage.get("generated_at",""))[:10] != now[:10]))
    ledger_changed = bool(smart and (
        not versions_file.exists() or
        (ledger.get("series") or {}) != (old_versions.get("series") or {})))
    if (added == 0 and retitled == 0 and story_updated == 0 and not digest_changed
            and not frontpage_changed and not ledger_changed
            and output_file.exists()):
        return {"research_checked":checked,"rejected":rejected,
                "published_new":0,"retitled_existing":0,
                "regional_groups":len(digest["groups"]),"digest_changed":False,
                "smart_editorial":smart,"new_features_selected":0,
                "new_context_analyses_published":0,
                "journalistic_story_updates":0,
                "short_briefs":len(frontpage["briefs"]) if smart else 0,
                "persisted_in_mobile_feed":len(previous),
                "ai_calls":0,"source_facts_required":True,"status":"unchanged"}
    final = sorted(accepted.values(),key=lambda x:x["published_at"],reverse=True)
    if len(final) > MAX_FEED_ENTRIES:
        # Feed is bounded for mobile. Historical published entries are retained
        # separately in Git history; no deletion from the source research bundles.
        final = final[:MAX_FEED_ENTRIES]
    result = {"schema":SCHEMA,"generated_at":now,"articles":final,
              "regional_editorial":digest}
    def save_atomic(path, document):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(document,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        temp.replace(path)
    if added or retitled or story_updated or digest_changed or not output_file.exists():
        save_atomic(output_file, result)
    if smart and frontpage_changed:
        save_atomic(frontpage_file, frontpage)
    if smart and ledger_changed:
        save_atomic(versions_file, ledger)
    return {"research_checked":checked,"rejected":rejected,
            "published_new":added,"retitled_existing":retitled,
            "regional_groups":len(digest["groups"]),"digest_changed":digest_changed,
            "journalistic_story_updates":story_updated,
            "smart_editorial":smart,
            "new_features_selected":len(frontpage["features_new"]) if smart else added,
            "new_context_analyses_published":len(frontpage["context_analyses_new"]) if smart else 0,
            "short_briefs":len(frontpage["briefs"]) if smart else 0,
            "revision_alerts":len(frontpage["revision_review"]) if smart else 0,
            "persisted_in_mobile_feed":len(final),
            "ai_calls":0,"source_facts_required":True}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--review-root", default="editorial_output/official_data_stories")
    p.add_argument("--output", default="data/news/automatic_features.json")
    p.add_argument("--smart",action="store_true",help="source-version and newsworthy publication gate")
    p.add_argument("--versions-file",default="data/news/source_versions.json")
    p.add_argument("--frontpage-file",default="data/news/editorial_frontpage.json")
    a=p.parse_args(argv)
    print(json.dumps(publish(a.review_root,a.output, smart=a.smart,
                             versions_file=a.versions_file if a.smart else None,
                             frontpage_file=a.frontpage_file if a.smart else None),
                     ensure_ascii=False))


if __name__=="__main__":
    main()
