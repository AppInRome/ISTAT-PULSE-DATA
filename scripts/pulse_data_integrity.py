#!/usr/bin/env python3
"""Fail-closed read-only consistency check for all published PULSE DATA feeds.

HTTPS syntax != verified link reachability. Use probe_source_links.py separately
for limited external reachability sampling. Standard library, network-free.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROME=ZoneInfo("Europe/Rome")
BUCKETS=("oggi","ieri","archivio")

def iso(value):
    try:
        d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError,TypeError):
        return None

def https(url):
    try:
        u=urlsplit(str(url or ""))
        return u.scheme=="https" and bool(u.hostname) and not u.username and not u.password
    except (ValueError,TypeError):
        return False

def inspect(root:Path,now=None):
    now=now or datetime.now(timezone.utc)
    problems=[]; warnings=[]; counts={}
    def bad(text):problems.append(text)
    def caution(text):warnings.append(text)
    def j(path):
        try:return json.loads((root/path).read_text(encoding="utf-8-sig"))
        except (OSError,ValueError) as e:bad("file_invalid:"+path+":"+str(e)[:80]);return {}
    root=Path(root)
    article_root=j("news/articles.json");articles=article_root.get("articles",[])
    index=j("news/index.json")
    if not isinstance(articles,list):articles=[];bad("news_articles_not_list")
    if not articles:bad("news_articles_empty")
    ids=[a.get("id") for a in articles if isinstance(a,dict)]
    if len(ids)!=len(set(ids)):bad("news_archive_duplicate_ids")
    by_id={a["id"]:a for a in articles if isinstance(a,dict) and a.get("id")}
    counts["articles_total"]=len(articles)
    generated=iso(index.get("generated_at"))
    if not generated or generated!=iso(article_root.get("generated_at")):bad("news_generation_mismatch")
    if generated:
        age=(now-generated).total_seconds()/3600
        counts["news_age_hours"]=round(age,2)
        if age>36:caution("news_not_refreshed_in_36_hours")
        if age < -2:bad("news_generated_in_future")
    day=(generated or now).astimezone(ROME).date()
    seen=set()
    for bucket in BUCKETS:
        items=index.get(bucket)
        if not isinstance(items,list):bad("missing_bucket:"+bucket);continue
        if len(items)!=len(set(items)):bad("duplicates_in_bucket:"+bucket)
        if (index.get("counts") or {}).get(bucket)!=len(items):bad("wrong_bucket_count:"+bucket)
        counts[bucket]=len(items)
        for aid in items:
            if aid in seen:bad("overlapping_buckets:"+str(aid))
            seen.add(aid)
            article=by_id.get(aid)
            if not article:bad("indexed_article_missing:"+str(aid));continue
            if article.get("publication_status")!="published":bad("indexed_article_not_published:"+aid)
            if not https((article.get("public_source") or {}).get("url")):bad("article_source_invalid:"+aid)
            if not str(article.get("headline") or "").strip():bad("article_headline_empty:"+aid)
            pub=iso(article.get("published_at"))
            if not pub:bad("article_date_invalid:"+aid);continue
            d=pub.astimezone(ROME).date()
            expected="oggi" if d==day else "ieri" if d==day-timedelta(days=1) else "archivio"
            if d>day or bucket!=expected:bad("article_in_wrong_date_bucket:"+aid)
            if article.get("origin_kind")=="pulse_media_radar":
                if (article.get("public_source") or {}).get("role")!="journalistic_source":
                    bad("media_claimed_primary:"+aid)
                if (article.get("chart_spec") or {}).get("status")=="verified":
                    bad("unverified_media_chart:"+aid)
    counts["indexed_public"]=len(seen)
    for section in ("green","territori"):
        section_index=j("news/"+section+"_index.json")
        if iso(section_index.get("generated_at"))!=generated:bad(section+"_different_generation")
        for bucket in BUCKETS:
            sub=section_index.get(bucket)
            if not isinstance(sub,list):bad(section+"_missing_"+bucket);continue
            if len(sub)!=len(set(sub)):bad(section+"_duplicate_"+bucket)
            if not set(sub).issubset(set(index.get(bucket) or [])):bad(section+"_outside_news_"+bucket)
            if (section_index.get("counts") or {}).get(bucket)!=len(sub):
                bad(section+"_wrong_count_"+bucket)
            counts[section+"_"+bucket]=len(sub)
    obs=j("news/observer_articles.json").get("articles",[])
    if not isinstance(obs,list) or not obs:bad("observers_missing");obs=[]
    obs_ids=set();empty_body=0;invalid_meta=0
    for item in obs:
        if not isinstance(item,dict):invalid_meta+=1;continue
        aid=item.get("id")
        if aid in obs_ids:bad("duplicate_observer_id:"+str(aid))
        obs_ids.add(aid)
        if not https((item.get("public_source") or {}).get("url")):
            bad("observer_url_invalid:"+str(aid))
        if not item.get("headline") or not item.get("observer") or not iso(item.get("published_at")):
            invalid_meta+=1
        if not item.get("pulse_article_body"):empty_body+=1
    counts["observers"]=len(obs)
    counts["observers_without_body"]=empty_body
    if invalid_meta:caution("legacy_observer_metadata_incomplete:"+str(invalid_meta))
    if empty_body:caution("observer_source_cards_without_article_body:"+str(empty_body))
    manifest=j("pulse_manifest.json")
    try:
        body=(root/"pulse_events.tsv").read_bytes()
        if hashlib.sha256(body).hexdigest()!=manifest.get("feed_sha256"):bad("event_manifest_hash_mismatch")
        with (root/"pulse_events.tsv").open(encoding="utf-8-sig",newline="") as f:
            reader=csv.DictReader(f,delimiter="\t")
            mandatory={"id","source_url","source_family","indicator","period","scope"}
            if not mandatory.issubset(reader.fieldnames or []):bad("event_tsv_missing_columns")
            rows=list(reader)
        counts["events"]=len(rows)
        if manifest.get("feed_events")!=len(rows):bad("event_manifest_count_mismatch")
        if len(rows)!=len({r.get("id") for r in rows}):bad("event_duplicate_ids")
        wrong=[r for r in rows if not https(r.get("source_url"))]
        if wrong:bad("event_source_urls_invalid:"+str(len(wrong)))
        counts["event_scopes"]=dict(Counter(r.get("scope") for r in rows))
    except (OSError,UnicodeError,csv.Error) as e:
        bad("event_feed_unreadable:"+str(e)[:100]);rows=[]
    catalog=j("sources_catalog.json").get("sources",[])
    if not isinstance(catalog,list):catalog=[];bad("catalog_invalid")
    counts["source_catalog"]=len(catalog)
    if len(catalog)<5:caution("small_source_catalog")
    if any(not isinstance(x,dict) or not x.get("name") or not https(x.get("url")) for x in catalog):
        bad("catalog_has_missing_or_invalid_url")
    family={str(x.get("source_family")) for x in rows}
    known={str(x.get("name")) for x in catalog if isinstance(x,dict)}
    counts["unmapped_event_source_families"]=len(family-known)
    if family-known:caution("catalog_not_exhaustive_for_event_source_families")
    obs_manifest=j("pulse_observations_manifest.json")
    if (root/"pulse_observations.tsv").exists() and obs_manifest.get("sha256"):
        if hashlib.sha256((root/"pulse_observations.tsv").read_bytes()).hexdigest()!=obs_manifest["sha256"]:
            bad("observations_manifest_hash_mismatch")
    return {"passed":not problems,"counts":counts,"errors":problems[:80],
            "warnings":warnings[:40],"external_url_reachability_tested":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-root",default="data",type=Path)
    p.add_argument("--report",default="")
    args=p.parse_args()
    report=inspect(args.data_root)
    text=json.dumps(report,ensure_ascii=False,indent=2)
    print(text)
    if args.report:Path(args.report).write_text(text+"\n",encoding="utf-8")
    return 0 if report["passed"] else 2

if __name__=="__main__":raise SystemExit(main())
