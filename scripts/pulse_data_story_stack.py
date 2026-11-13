"""PULSE Italia — reproducible, evidence-led data-journalism stack.

Uses, when installed:
* Data Analyst Agent (indexcraft): independent descriptive CSV analysis, no LLM
* dstory (dkedar7): deterministic data-to-story HTML/graphs, no LLM
* Data2Story inspector (QinghongLin): sentence-to-evidence viewer, no LLM

LLM (Llama on Cloudflare Workers AI) is OPTIONAL, drafts only.
External MIT programs run as external dependencies; their code is not vendored.
The source evidence and PULSE's independent numeric audit remain authoritative.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
from html import escape
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
from scripts import pulse_editorial_engine_v1 as engine


def run_command(args, timeout=180, env=None):
    """Never use shell; log concise failures without disclosing credentials."""
    result = subprocess.run(args, capture_output=True, text=True,
                            timeout=timeout, env=env, check=False)
    if result.returncode:
        raise RuntimeError("external_stage_failed:" + str(result.returncode) +
                           ":" + ((result.stderr or result.stdout)[-700:]))
    return (result.stdout or "")[-2500:]


def as_float(value):
    result = float(Decimal(str(value)))
    if not (-1e300 < result < 1e300):
        raise ValueError("nonfinite_source_number")
    return result


def exact_verified_csv(evidence, path):
    """Export only observations extracted from matching official source rows."""
    series = evidence["series"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(("period", "value"))
        for item in series["observations"]:
            writer.writerow((item["period"], item["value"]))


def source_trace(evidence, draft, folder):
    """Create Data2Story-compatible audit artifacts without inventing new facts.

    This is NOT the complete 7-role Data2Story agent. It runs the actual
    Data2Story inspector scripts on a PULSE-authored verifiable mini-report.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    series = evidence["series"]
    observations = series["observations"]
    points = [(str(o["period"]), as_float(o["value"])) for o in observations]
    minimum, maximum = min(v for _, v in points), max(v for _, v in points)
    span = max(maximum - minimum, 1e-9)
    n = len(points)
    coords = " ".join("%.2f,%.2f" %
                      (24 + (i * 680 / max(n - 1, 1)),
                       220 - ((v - minimum) / span * 180))
                      for i, (_, v) in enumerate(points))
    rows = "\n".join("<tr data-ana=\"ana_01\"><th>%s</th><td>%s</td></tr>" %
                     (escape(p), escape(str(o["value"])))
                     for (p, _), o in zip(points, observations))
    # LLM drafts have independent numeric audit but need human semantic review.
    title = draft["title"] if draft else series["indicator"] + ": serie statistica ufficiale"
    paragraphs = (draft.get("paragraphs") or []) if draft else []
    if not paragraphs:
        paragraphs = ["La fonte ufficiale documenta %s osservazioni per %s, riferite a %s." %
                      (len(points), series["indicator"], series["territory"]),
                      "I periodi considerati vanno da %s a %s. Unità: %s. Popolazione: %s." %
                      (points[0][0], points[-1][0], series["unit"], series["population"])]
    para_html = "\n".join('<p data-ana="ana_01">%s</p>' % escape(p)
                           for p in paragraphs)
    url = evidence["dataset_url"]
    safe_url = escape(url, quote=True)
    source_url = escape(evidence["source_url"], quote=True)
    html = ('<!doctype html><html lang="it"><head><meta charset="utf-8">'
            '<title>%s</title><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<style>body{font:16px system-ui;line-height:1.6;max-width:900px;margin:auto;padding:24px}'
            'svg{max-width:100%%;height:auto;border:1px solid #ccd}table{border-collapse:collapse}'
            'td,th{padding:8px 15px;border-bottom:1px solid #dde}</style></head><body>'
            '<h1 data-ana="ana_01">%s</h1>%s'
            '<section data-edt="edt_01"><h2>Serie ufficiale</h2>'
            '<svg class="chart" data-des="des_01" data-ana="ana_01" viewBox="0 0 740 250" role="img" '
            'aria-label="Andamento dei valori verificati"><polyline fill="none" stroke="#176a96" '
            'stroke-width="3" points="%s"/></svg>'
            '<table><thead><tr><th>Periodo</th><th>Valore (%s)</th></tr></thead>'
            '<tbody>%s</tbody></table></section>'
            '<section class="references" data-edt="edt_01"><h2>Fonti</h2>'
            '<p data-det="det_01">Pubblicazione istituzionale: '
            '<a href="%s">%s</a>. Dataset: <a href="%s">%s</a>.</p>'
            '<p data-det="det_01">SHA-256 del file originale: %s.</p></section>'
            '</body></html>') % (
                escape(title), escape(title), para_html, coords, escape(series["unit"]),
                rows, source_url, source_url, safe_url, safe_url,
                escape(evidence["source_sha256"]))
    (folder / "index.html").write_text(html, encoding="utf-8")
    analyst = {"dataset": {"files": ["verified.csv"]}, "items": {
        "ana_01": {"label": series["indicator"], "content": "Confronto statistico con classificazioni ufficiali",
                   "type": "original_source", "strength": "verified_row_level",
                   "data_table": [{"period": p, "value": v} for p, v in points],
                   "calculation": {"code": "CSV di origine con righe verificate, senza interpolazioni.",
                                   "output": json.dumps(points, ensure_ascii=False)}}}}
    detective = {"items": {"det_01": {
        "label": "Fonte primaria italiana", "content": series["indicator"],
        "sources": [{"url": evidence["source_url"], "title": evidence.get("publisher"),
                     "facts": ["SHA256 " + evidence["source_sha256"]]},
                    {"url": evidence["dataset_url"], "title": "Dataset originale"}]}}}
    editor = {"items": {"edt_01": {
        "label": "Serie ufficiale", "purpose": "Mostrare misure realmente osservate",
        "findings": ["ana_01"], "context": ["det_01"]}}}
    designer = {"items": {"des_01": {
        "label": "Grafico cronologico", "type": "line_chart",
        "content": {"data_source": "ana_01"},
        "brief": "Solo osservazioni ufficiali; nessun dato estrapolato"}}}
    for name, obj in [("analyst.json", analyst), ("detective.json", detective),
                      ("editor.json", editor), ("designer.json", designer)]:
        (folder / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
    return folder


def run_data_analyst(executable, csv_path, output_dir, context):
    if not executable:
        return {"status": "not_configured"}
    script = Path(executable)
    if not script.is_file():
        return {"status": "missing_external_tool", "path": str(script)}
    output_dir.mkdir(parents=True, exist_ok=True)
    run_command([sys.executable, str(script), "--file", str(csv_path),
                 "--output-dir", str(output_dir), "--context", context, "--no-llm"],
                timeout=180)
    if not (output_dir / "stats.json").is_file():
        raise RuntimeError("data_analyst_missing_stats")
    return {"status": "completed", "stats": str(output_dir / "stats.json"),
            "report": str(output_dir / "report.html")}


def run_dstory(command, csv_path, output_dir, source):
    if not command:
        return {"status": "not_configured"}
    if shutil.which(command) is None:
        return {"status": "missing_external_tool", "command": command}
    output_dir.mkdir(parents=True, exist_ok=True)
    # The external project's CLI produces its own story.html and can be kept
    # as an editorial artifact. Android uses verified chart_spec from PULSE.
    stdout = run_command([command, "draft", str(csv_path), "--source", source,
                          "--no-vet"], timeout=180, env={**os.environ,
                          "PULSE_NO_AUTO_PUBLISH": "1"})
    return {"status": "completed", "cli_log": stdout}


def run_data2story_inspector(skill_root, report_dir):
    if not skill_root:
        return {"status": "not_configured"}
    folder = Path(skill_root)
    if (folder / "skills" / "data2story" / "inspector").is_dir():
        folder = folder / "skills" / "data2story"
    scripts = folder / "inspector" / "scripts"
    verifier = scripts / "verify.py"
    viewer = scripts / "generate_viewer.py"
    if not verifier.is_file() or not viewer.is_file():
        return {"status": "missing_external_tool", "folder": str(folder)}
    run_command([sys.executable, str(verifier), str(report_dir)], timeout=90)
    run_command([sys.executable, str(viewer), str(report_dir)], timeout=90)
    report = json.loads((report_dir / "verifier.json").read_text(encoding="utf-8"))
    stats = report.get("stats") or {}
    if stats.get("untraced", 1):
        raise ValueError("data2story_untraced_claims")
    return {"status": "completed", "traced_sentences": stats.get("traced"),
            "viewer": str(report_dir / "viewer.html"),
            "caution": "This checks attribution links, not factual truth."}


def pipeline(manifest_path, source_file, output_dir, data_analyst_script=None,
             dstory_command=None, data2story_root=None, ai_mode="none"):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    # PULSE engine verifies Italian official source/dataset domains and dimensions.
    spec = engine.verify_manifest(manifest)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if source_file:
        manifest["_offline"] = True
        data = Path(source_file).read_bytes()
    else:
        data = engine.fetch(manifest["dataset_url"])
    evidence = engine.extract(manifest, data)
    (output_dir / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = output_dir / "verified.csv"
    exact_verified_csv(evidence, csv_path)
    result = {"status": "research_artifacts_only", "scope": "IT",
              "source_verified": True, "dataset_sha256": evidence["source_sha256"],
              "observations": len(evidence["series"]["observations"]),
              "ai": {"mode": ai_mode, "status": "disabled"},
              "components": {}, "publish": False}
    result["components"]["data_analyst"] = run_data_analyst(
        data_analyst_script, csv_path, output_dir / "data_analyst",
        evidence["series"]["indicator"] + " - Italia")
    result["components"]["dstory"] = run_dstory(
        dstory_command, csv_path, output_dir / "dstory", evidence["dataset_url"])
    draft = None
    if ai_mode == "llama":
        expected = ("PULSE_LLM_API_KEY", "PULSE_LLM_ENDPOINT", "PULSE_LLM_MODEL")
        if not all(os.environ.get(k) for k in expected):
            result["ai"]["status"] = "credentials_absent_not_called"
        elif not os.environ["PULSE_LLM_MODEL"].startswith("@cf/meta/llama"):
            raise ValueError("llama_model_required")
        else:
            # Uses PULSE's audited editorial engine; output is a draft ONLY.
            from scripts import pulse_editorial_audit_v1 as audit
            proposal = engine.call_model(evidence)
            if proposal.get("insufficient_evidence"):
                result["ai"]["status"] = "insufficient_evidence"
            else:
                draft = {k: proposal.get(k) for k in ("title", "lead", "paragraphs")}
                draft.update({"source_url": evidence["source_url"],
                              "dataset_url": evidence["dataset_url"],
                              "evidence_sha256": audit.digest(evidence),
                              "publication_status": "draft",
                              "editorial_status": "draft_only"})
                status = audit.audit(draft, evidence)
                draft["audit"] = status
                (output_dir / "llama_draft.json").write_text(json.dumps(
                    draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                result["ai"]["status"] = "audited_draft" if status["passed"] else "rejected"
                if not status["passed"]:
                    draft = None
    trace_dir = source_trace(evidence, draft, output_dir / "data2story_trace")
    result["components"]["data2story_inspector"] = run_data2story_inspector(
        data2story_root, trace_dir)
    (output_dir / "pipeline_status.json").write_text(json.dumps(
        result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="PULSE Italia: official-data storytelling, AI optional")
    p.add_argument("--manifest", required=True)
    p.add_argument("--source-file", help="Use a local copy; no network")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--data-analyst-script")
    p.add_argument("--dstory-command", default=None)
    p.add_argument("--data2story-root")
    p.add_argument("--ai", choices=["none", "llama"], default="none")
    a = p.parse_args(argv)
    print(json.dumps(pipeline(a.manifest, a.source_file, a.output_dir,
                               a.data_analyst_script, a.dstory_command,
                               a.data2story_root, a.ai), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
