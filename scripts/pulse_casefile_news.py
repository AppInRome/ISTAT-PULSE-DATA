#!/usr/bin/env python3
"""PULSE evidence-based casefiles: original articles tied to official dated releases.

No scraping article text, no fabricated date, no duplicated news after repeat runs.
These are curated editorial inputs, not a substitute for the broad RSS radar.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def _official_url(url: str) -> bool:
    p=urlsplit(url or "")
    return p.scheme=="https" and (p.hostname=="istat.it" or (p.hostname or "").endswith(".istat.it")) and bool(p.path.strip("/"))


def _validate(case: dict, now: datetime) -> None:
    if not case.get("id","").startswith("PULSE-"):
        raise ValueError("Casefile without stable PULSE ID")
    if not _official_url(case.get("statistical_primary","")):
        raise ValueError("Casefile without original official document")
    published=datetime.fromisoformat(case["published_at"].replace("Z","+00:00"))
    if published.tzinfo is None:
        raise ValueError("Casefile published_at must be timezone aware")
    if published.astimezone(timezone.utc)>now.astimezone(timezone.utc):
        raise ValueError("Future-dated casefile")
    if case.get("source_publication_day")!=published.date().isoformat():
        raise ValueError("Source publication date does not match timestamp")
    values=case.get("chart_categories")
    if not isinstance(values,list) or len(values)<2 or len(values)>20:
        raise ValueError("Missing finite source-backed chart categories")
    if sum(float(pair[1]) for pair in values)!=float(case.get("denominator")):
        raise ValueError("Chart values do not reconcile with official total")
    if not case.get("body") or not case.get("summary"):
        raise ValueError("Casefile missing independent PULSE narrative")


def add_verified_casefiles(by_id: dict, casefile_path: Path, now: datetime) -> int:
    if not casefile_path.is_file():
        return 0
    bundle=json.loads(casefile_path.read_text(encoding="utf-8"))
    cases=bundle.get("cases",[])
    if not isinstance(cases,list):
        raise ValueError("Cases must be a list")
    added=0
    for c in cases:
        _validate(c,now)
        case_id=c["id"]
        if case_id in by_id:
            continue
        original=c["statistical_primary"]
        publisher="istat.it"
        label=c.get("source_name","ISTAT")
        data=[{"period":str(name),"value":int(count)} for name,count in c["chart_categories"]]
        rows=[[name,str(count)] for name,count in c["chart_categories"]]
        fp=hashlib.sha256(("PULSE-CASEFILE|"+case_id).encode()).hexdigest()[:24]
        brief={
            "id":case_id,
            "story_fingerprint":fp,
            "published_at":c["published_at"],
            "publication_time_precision":c.get("publication_time_precision","day"),
            "source_published_at":c["source_publication_day"],
            "period_reference":c.get("data_reference_period"),
            "last_seen_at":now.isoformat(),
            "topic":c.get("topic","ECONOMIA"),
            "origin_kind":"pulse_casefile",
            "publication_status":"published",
            "editorial_status":"verified",
            "verification_tier":"manually_checked_official_release_with_explicit_table",
            "pulse_score":92,
            "byline":"Redazione PULSE",
            "headline":c["headline"],
            "summary":c["summary"],
            "pulse_title":c["headline"],
            "pulse_summary":c["summary"],
            "pulse_article_body":c["body"],
            "territories":["italia"],
            "patterns":[],
            "sources":[
                {"role":"statistical_primary","name":label,"url":original},
                {"role":"statistical_primary","name":"ISTAT - Povertà assoluta","url":c.get("additional_primary",original)},
                {"role":"journalistic_discovery","name":"Corriere della Sera","url":c.get("discovered_from","")}
            ],
            "public_source":{
                "url":original,"domain":publisher,"role":"primary_statistical_source",
                "verification_method":"checked_original_istat_report",
                "verification_score":100
            },
            "discovery":{"visible":False,"role":"journalistic_radar",
                         "outlet":"Corriere della Sera",
                         "original_url":c.get("discovered_from",""),
                         "evidence_gate":"strong_primary_match"},
            "statistical_claims":[
                {"raw_value":str(item["value"]),"label":item["period"],
                 "indicator":"Indicatori BES confrontabili","period":c.get("data_reference_period"),
                 "verified":True} for item in data
            ],
            "verified_series":[
                {"indicator":"Indicatori BES confrontabili","unit":"indicatori",
                 "observations":data,"source_url":original,"verified":True}
            ],
            "chart_spec":{
                "type":"bar","status":"verified",
                "title":"Andamento degli indicatori BES (numero)",
                "unit":"indicatori","source_url":original,
                "category_axis":True,"data":data
            },
            "table_spec":{
                "status":"verified","columns":["Andamento","N. indicatori"],
                "rows":rows,"source_url":original
            },
            "map_spec":None
        }
        by_id[case_id]=brief
        added+=1
    return added
