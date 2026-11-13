#!/usr/bin/env python3
"""PULSE Editorial Engine v1: source -> evidence -> AI draft -> independent audit -> approval -> Android feed.

No automatic publication, no synthetic observations, no secret keys in files.
Use `python scripts/pulse_editorial_engine_v1.py --help` for CLI.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request

try:
    from scripts import pulse_editorial_audit_v1 as independent
except ImportError:
    import pulse_editorial_audit_v1 as independent

MAX_BYTES = 12_000_000
TRUSTED_DOMAINS = (
    "istat.it", "bancaditalia.it", "mef.gov.it", "finanze.gov.it", "inps.it", "inail.it",
    "isprambiente.gov.it", "agenziaentrate.gov.it", "eurostat.ec.europa.eu", "ec.europa.eu",
    "data.europa.eu", "iss.it", "salute.gov.it", "arera.it", "terna.it", "gse.it",
)
PERIOD = re.compile(r"(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]|Q[1-4]))?")


def allowed_url(url):
    p = urllib.parse.urlsplit(url)
    h = (p.hostname or "").casefold()
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443) or not h:
        raise ValueError("https_official_source_required")
    if not any(h == domain or h.endswith("." + domain) for domain in TRUSTED_DOMAINS):
        raise ValueError("domain_not_in_official_registry:" + h)
    return url


class NoCrossDomainRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_url(newurl)
        # Restrict redirection to same official domain family as source.
        if urllib.parse.urlsplit(req.full_url).hostname != urllib.parse.urlsplit(newurl).hostname:
            raise ValueError("cross_host_redirect_rejected")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    allowed_url(url)
    opener = urllib.request.build_opener(NoCrossDomainRedirect)
    req = urllib.request.Request(url, headers={"User-Agent":"PULSE-Editorial-Evidence/1.0"})
    with opener.open(req, timeout=20) as response:
        if response.status != 200:
            raise ValueError("source_http_error")
        payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("source_too_large")
        return payload


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Do not leave truncated output when generating a new artifact.
    temp = p.with_name(p.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(p)


def parse_numeric(raw):
    if isinstance(raw, bool) or raw is None:
        raise ValueError("invalid_or_suppressed_observation")
    token = str(raw).strip().replace("\u00a0", "")
    if re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?", token):
        token = token.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", token):
        token = token.replace(",", ".")
    else:
        raise ValueError("ambiguous_or_suppressed_observation")
    try:
        d = Decimal(token)
    except InvalidOperation as e:
        raise ValueError("invalid_numeric") from e
    if not d.is_finite():
        raise ValueError("non_finite_value")
    return independent.nfmt(d)


def decode_records(source, fmt):
    if fmt == "csv":
        text = source.decode("utf-8-sig")
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=";,\t")
        return list(csv.DictReader(io.StringIO(text), dialect=dialect))
    if fmt == "json":
        payload = json.loads(source)
        records = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise ValueError("json_must_contain_record_array")
        return records
    raise ValueError("only_csv_json_supported_for_direct_numeric_import")


def verify_manifest(manifest):
    for field in ("source_url", "dataset_url"):
        allowed_url(manifest[field])
    # Classification values must match the columns in the source. No invented groups.
    spec = manifest["schema"]
    dims = spec["dimensions"]
    if not isinstance(dims, dict) or not dims or not all(isinstance(k, str) and isinstance(v, str) and v for k,v in dims.items()):
        raise ValueError("official_dimensions_required")
    for k in ("indicator", "unit", "territory", "population", "frequency"):
        if k not in spec["semantic_columns"] or spec["semantic_columns"][k] not in dims:
            raise ValueError("missing_explicit_official_classification:" + k)
    if spec["period_column"] in dims or spec["value_column"] in dims:
        raise ValueError("value_period_cannot_be_dimension")
    # The Italian newsroom never interprets foreign-country datasets as Italy.
    from scripts.pulse_italia_newsroom import italian_official_url, REGIONS
    territory = dims[spec["semantic_columns"]["territory"]].strip().casefold()
    if territory != "italia" and territory not in REGIONS:
        raise ValueError("outside_italian_editorial_scope")
    if not all(italian_official_url(manifest[field]) for field in ("source_url", "dataset_url")):
        raise ValueError("italian_official_source_required")
    return spec


def extract(manifest, data):
    spec = verify_manifest(manifest)
    records = decode_records(data, spec["format"])
    observations = []
    locations = []
    for row_number, row in enumerate(records, 2):
        if not isinstance(row, dict):
            raise ValueError("invalid_source_row")
        if not all(str(row.get(key, "")).strip() == expected for key, expected in spec["dimensions"].items()):
            continue
        period = str(row.get(spec["period_column"], "")).strip()
        if not PERIOD.fullmatch(period):
            raise ValueError("period_must_be_official_year_or_month_or_quarter")
        try:
            value = parse_numeric(row.get(spec["value_column"]))
        except ValueError:
            # Suppressed data are not treated as zero and cannot be graphed.
            continue
        unit = spec["dimensions"][spec["semantic_columns"]["unit"]]
        if unit == "%" and not Decimal("0") <= Decimal(value) <= Decimal("100"):
            raise ValueError("percentage_outside_0_100")
        observations.append({"period":period, "value":value, "raw":str(row.get(spec["value_column"]))})
        locations.append({"period":period,"source_row":row_number})
    observations.sort(key=lambda row:row["period"])
    if len(observations) < 2:
        raise ValueError("insufficient_comparable_observations_no_trend")
    if len(set(row["period"] for row in observations)) != len(observations):
        raise ValueError("duplicate_periods_for_same_dimensions")
    dims = spec["dimensions"]
    semantic = spec["semantic_columns"]
    series = {k:dims[semantic[k]] for k in ("indicator", "unit", "territory", "population", "frequency")}
    series["observations"] = observations
    series["classification_values"] = dims
    return {
        "schema_version":1, "verified":True, "source_url":manifest["source_url"],
        "dataset_url":manifest["dataset_url"], "publisher":manifest.get("publisher", ""),
        "source_sha256":sha256(data).hexdigest(), "retrieval_mode":"local_copy" if manifest.get("_offline") else "https",
        "source_locations":locations, "extraction_method":"exact_classification_long_format_row",
        "series":series, "topic":manifest.get("topic", "ALTRO"),
        "methodology_url":manifest.get("methodology_url", manifest["source_url"]),
        "notes":"Classification values are copied from the official table; no synthetic points or interpolation."
    }


def run_extract(args):
    manifest = load_json(args.manifest)
    if args.source_file:
        data = Path(args.source_file).read_bytes()
        manifest["_offline"] = True
    else:
        data = fetch(manifest["dataset_url"])
    evidence = extract(manifest, data)
    write_json(args.output, evidence)
    print(f"[EVIDENZE] {len(evidence['series']['observations'])} osservazioni verificate -> {args.output}")


def ai_prompt(evidence):
    facts = independent.variations(evidence)
    return (
        "Scrivi un ARTICOLO giornalistico originale italiano, non una scheda tecnica. "
        "Rispondi con SOLO JSON: title (titolo vivace ma veritiero), lead (minimo 20 parole), "
        "paragraphs (4-6 paragrafi narrativi senza titoli ripetitivi). "
        "Il lead e i paragrafi devono totalizzare 15-25 frasi e 250-500 parole. "
        "Vietati sezioni 'PULSE analizza il dato', 'Perché è su PULSE', 'Analisi statistica PULSE', "
        "'Dati quantitativi citati'. Niente riempitivi per raggiungere lunghezza: se i fatti "
        "non bastano rispondi con JSON {\"insufficient_evidence\": true}. "
        "Non dichiarare cause, previsioni, quote o contesti non dimostrati. "
        "Inserisci valori e confronti soltanto dalle evidenze; ricorda che punti percentuali "
        "e variazione relativa percentuale sono cose diverse. "
        "Questi sono TUTTI i dati permessi, con definizioni ufficiali:\n" +
        json.dumps({"series":evidence["series"], "facts":facts,
                    "source_url":evidence["source_url"],"dataset_url":evidence["dataset_url"],
                    "methodology_url":evidence.get("methodology_url")}, ensure_ascii=False)
    )


def call_model(evidence):
    endpoint = os.getenv("PULSE_LLM_ENDPOINT", "").strip()
    model = os.getenv("PULSE_LLM_MODEL", "").strip()
    key = os.getenv("PULSE_LLM_API_KEY", "").strip()
    if not endpoint or not model:
        raise ValueError("configure_PULSE_LLM_ENDPOINT_and_PULSE_LLM_MODEL")
    p = urllib.parse.urlsplit(endpoint)
    if p.username or p.password or p.scheme not in {"https", "http"}:
        raise ValueError("unsafe_LLM_endpoint")
    if p.scheme == "http" and p.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("remote_LLM_must_use_https")
    max_tokens = max(500, min(2000, int(os.getenv("PULSE_LLM_MAX_OUTPUT_TOKENS", "1400"))))
    body = {"model":model,"temperature":0.2,"max_tokens":max_tokens,
            "messages":[{"role":"system","content":"Sei un giornalista statistico rigoroso. Nessuna cifra inventata."},
                        {"role":"user","content":ai_prompt(evidence)}],
            "response_format":{"type":"json_object"}}
    headers = {"Content-Type":"application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(endpoint, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=90) as reply:
        payload = json.loads(reply.read(500_000))
    text = payload["choices"][0]["message"]["content"]
    return json.loads(text)


def run_draft(args):
    evidence = load_json(args.evidence)
    proposed = load_json(args.proposal_file) if args.proposal_file else call_model(evidence)
    if proposed.get("insufficient_evidence"):
        raise ValueError("model_declared_insufficient_evidence_no_article")
    draft = {key: proposed.get(key) for key in ("title", "lead", "paragraphs")}
    draft.update({"evidence_sha256":independent.digest(evidence),
                  "source_url":evidence["source_url"],"dataset_url":evidence["dataset_url"],
                  "editorial_status":"draft_only", "publication_status":"draft"})
    result = independent.audit(draft, evidence)
    draft["audit"] = result
    write_json(args.output, draft)
    if not result["passed"]:
        raise ValueError("draft_rejected_by_independent_auditor:" + ";".join(result["issues"]))
    print(f"[BOZZA] audit superato, approvazione umana necessaria -> {args.output}")


def confirmed_approval(approval, draft, evidence):
    if independent.audit(draft, evidence)["passed"] is not True:
        raise ValueError("re_audit_failed")
    if approval.get("decision") != "publish" or not str(approval.get("reviewer", "")).strip():
        raise ValueError("human_approval_required")
    if approval.get("draft_sha256") != independent.digest({k:v for k,v in draft.items() if k!="audit"}):
        raise ValueError("draft_changed_after_approval")
    if approval.get("evidence_sha256") != independent.digest(evidence):
        raise ValueError("evidence_changed_after_approval")
    if approval.get("independent_review_completed") is not True:
        raise ValueError("independent_human_review_required")
    t = datetime.fromisoformat(str(approval["approved_at"]).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("timezone_required")


def publish_article(draft, evidence, approval):
    confirmed_approval(approval, draft, evidence)
    series = evidence["series"]
    latest = series["observations"][-1]
    source = evidence["source_url"]
    stamp = datetime.fromisoformat(approval["approved_at"].replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    id_payload = source + evidence["source_sha256"] + series["indicator"] + latest["period"]
    code = sha256(id_payload.encode("utf-8")).hexdigest()[:16].upper()
    body = [{"heading":"", "text":p.strip()} for p in draft["paragraphs"]]
    observations = [{"period":p["period"],"value":float(p["value"]),"raw":p["raw"]}
                    for p in series["observations"]]
    chart = {"status":"verified","type":"line" if len(observations)>=3 else "bar",
             "title":series["indicator"],"unit":series["unit"],
             "source_url":evidence["dataset_url"],"data":observations,
             "x_axis":"Periodo","y_axis":series["unit"],"interaction":"pan_zoom_tooltip"}
    return {
        "id":"PULSE-EDITORIAL-"+code, "publication_status":"published",
        "publication_tier":"verified_primary_data_feature", "editorial_status":"verified",
        "editorial_format":"ai_assisted_independently_audited_human_approved",
        "published_at":stamp,"first_published_at_utc":stamp,
        "headline":draft["title"],"pulse_title":draft["title"],
        "summary":draft["lead"],"pulse_summary":draft["lead"],
        "pulse_article_body":body,"topic":evidence.get("topic","ALTRO"),
        "geographic_scope":{"country_code":"IT","territory":series["territory"]},
        "public_source":{"url":source,"domain":urllib.parse.urlsplit(source).hostname,
                         "role":"primary_statistical_source"},
        "source_documents":[{"url":evidence["dataset_url"],"sha256":evidence["source_sha256"],
                             "extraction_method":evidence["extraction_method"]}],
        "verified_series":[{"indicator":series["indicator"],"unit":series["unit"],
                            # Radar 0.4 displays at most 12 comparable points.
                            "observations":observations[-12:],"verified":True,
                            # The official release URL is used for the existing Android
                            # exact-host provenance gate. The exact dataset URL is
                            # preserved separately in source_documents/chart_spec.
                            "source_url":evidence["source_url"],
                            "extraction_method":"exact_classification_long_format_row"}],
        "chart_spec":chart,
        "table_spec":{"status":"verified","source_url":evidence["dataset_url"],
                      "headers":["Periodo",series["indicator"]],
                      "rows":[[p["period"],float(p["value"])] for p in series["observations"]]},
        "editorial_review":{"reviewer":approval["reviewer"],"approved_at":stamp,
                            "independent_verification_note":approval.get("notes", ""),
                            "evidence_sha256":independent.digest(evidence),
                            "numeric_audit":independent.audit(draft,evidence)},
        "period_reference":latest["period"],
        "latest_source_update":stamp,
    }


def merge_feeds(article, original, index):
    root = dict(original)
    items = list(root.get("articles", []))
    items = [x for x in items if x.get("id") != article["id"]]
    items.append(article)
    root["articles"] = sorted(items,key=lambda x:x.get("published_at", ""),reverse=True)
    idx = dict(index)
    for bucket in ("oggi","ieri","archivio"):
        idx[bucket] = [x for x in idx.get(bucket,[]) if x != article["id"]]
    # The Android client reclassifies time buckets in Europe/Rome; this index
    # only ensures the new ID is not filtered out by its index-membership gate.
    idx["archivio"].append(article["id"])
    return root, idx


def run_publish(args):
    evidence, draft, approval = load_json(args.evidence), load_json(args.draft), load_json(args.approval)
    article = publish_article(draft, evidence, approval)
    existing = load_json(args.articles)
    index = load_json(args.index)
    merged, merged_index = merge_feeds(article, existing, index)
    # Single-purpose output artifacts: do not edit live production paths unless
    # the operator deliberately points outputs there after approving a PR.
    write_json(args.output_articles, merged)
    write_json(args.output_index, merged_index)
    write_json(args.output_article, article)
    print(f"[PUBBLICAZIONE PREPARATA] {article['id']} in {args.output_articles} e {args.output_index}")


def main(argv=None):
    p = argparse.ArgumentParser(description="PULSE Editorial Engine v1 - publication is always manually gated")
    sub=p.add_subparsers(dest="command", required=True)
    a=sub.add_parser("extract",help="Fetch official CSV/JSON, exact classifications -> evidence")
    a.add_argument("--manifest",required=True);a.add_argument("--source-file",help="offline official file; human must verify provenance")
    a.add_argument("--output",required=True);a.set_defaults(func=run_extract)
    a=sub.add_parser("draft",help="AI model writes draft; independent numeric audit")
    a.add_argument("--evidence",required=True);a.add_argument("--proposal-file",help="offline model response for tests")
    a.add_argument("--output",required=True);a.set_defaults(func=run_draft)
    a=sub.add_parser("publish",help="Require signed human decision; prepare updated Android JSON")
    for flag in ("evidence","draft","approval","articles","index","output-articles","output-index","output-article"):
        a.add_argument("--"+flag, required=True)
    a.set_defaults(func=run_publish)
    args=p.parse_args(argv)
    args.func(args)

if __name__=="__main__":
    main()
