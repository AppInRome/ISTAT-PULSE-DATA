#!/usr/bin/env python3
"""Conservative data-only refresh for AppInRome/ISTAT-PULSE-DATA.

Each legacy acquisition program runs in an isolated temporary directory. Files
are promoted only after checks; a failed or partial fetch preserves last-good
content and is reported explicitly. Never builds APKs or uploads artifacts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATUS = DATA / "refresh_status.json"
EVENT_FIELDS = [
    "id", "municipality_code", "municipality", "province", "region", "indicator",
    "patterns", "scope", "score", "validation_status", "period", "summary", "annual",
    "rolling12", "benchmark_local", "benchmark_rest", "analysis", "source_family", "source_url",
]
OBS_FIELDS = ["area", "indicator", "territory", "period", "value", "unit", "source", "url", "note", "status"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stage=path.with_suffix(path.suffix+".stage")
    stage.write_text(json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True)+"\n",encoding="utf-8")
    stage.replace(path)


def copy_if_exists(source: Path, destination: Path) -> None:
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def run_original(script: str, working_dir: Path, seconds: int) -> dict:
    program = ROOT / "scripts" / script
    cp = subprocess.run([sys.executable, "-u", str(program)], cwd=working_dir,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, errors="replace", timeout=seconds, check=False)
    # Show bounded diagnostic text, not unchecked HTML/credentials.
    print(f"[{script}] return={cp.returncode}\n{cp.stdout[-5500:]}", flush=True)
    if cp.returncode:
        raise RuntimeError(f"{script}: uscita {cp.returncode}")
    return {"output_tail": cp.stdout[-1200:]}


def read_tsv(path: Path, fields: list[str], minimum: int = 1) -> list[dict]:
    if not path.exists():
        raise ValueError(f"Manca {path.name}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames or any(field not in reader.fieldnames for field in fields):
            raise ValueError(f"Colonne mancanti in {path.name}")
        rows = list(reader)
    if len(rows) < minimum:
        raise ValueError(f"{path.name}: {len(rows)} righe inferiori al minimo {minimum}")
    return rows


def write_tsv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".stage")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def period_key(value):
    """Sort calendar months, quarters and annual references chronologically."""
    match=re.fullmatch(r"(\d{4})(?:-(?:(\d{2})|Q([1-4])))?",str(value or ""))
    if not match: return (0,0,0)
    year,month,quarter=match.groups()
    return (int(year),int(month) if month else int(quarter)*3 if quarter else 12,
            2 if month else 1 if quarter else 0)


def refresh_manifest(**extra):
    path=DATA/"pulse_events.tsv"
    rows=read_tsv(path,EVENT_FIELDS)
    manifest=read_json(DATA/"pulse_manifest.json",{}) or {}
    by_source={}
    latest={}
    for row in rows:
        family=row["source_family"]
        by_source[family]=by_source.get(family,0)+1
        if period_key(row["period"])>period_key(latest.get(family)):
            latest[family]=row["period"]
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if manifest.get("feed_sha256")!=digest or not manifest.get("generated_at"):
        manifest["generated_at"]=now_iso()
    manifest.update({"feed_sha256":digest,"feed_events":len(rows),
                     "events_by_source":by_source,
                     "green_events":sum(r["scope"]=="GREEN" for r in rows),
                     "indicators":sorted({r["indicator"] for r in rows}),
                     "latest_period":max(latest.values(),key=period_key,default=""),
                     "latest_period_by_source":latest,"last_checked_at":now_iso(),
                     "note_refresh":"Periodi statistici reali; last_checked_at non equivale a una nuova osservazione."})
    manifest.update(extra)
    write_json(DATA/"pulse_manifest.json",manifest)


def merge_events(rows: list[dict]) -> int:
    """Never delete old sources when a service is temporarily unavailable."""
    path=DATA/"pulse_events.tsv"
    old=read_tsv(path,EVENT_FIELDS,minimum=1)
    by_id={r["id"]:r for r in old if r.get("id")}
    changed=0
    for item in rows:
        if not all(str(item.get(k,"")).strip() for k in ("id","indicator","period","source_family","source_url")):
            raise ValueError("Evento privo di ID, periodo, fonte o indicatore")
        prior=by_id.get(item["id"])
        if prior and period_key(item["period"])<period_key(prior["period"]):
            continue
        if prior!=item:
            by_id[item["id"]]=item
            changed+=1
    if changed:
        write_tsv(path,EVENT_FIELDS,sorted(by_id.values(),key=lambda x:x["id"]))
    refresh_manifest()
    return changed


def merge_observations(observations):
    path=DATA/"pulse_observations.tsv"
    old=read_tsv(path,OBS_FIELDS)
    key=lambda r:(r["source"],r["indicator"],r["territory"],r["period"])
    by_key={key(r):r for r in old}
    changed=0
    for row in observations:
        if not all(str(row.get(x,"")).strip() for x in ("indicator","territory","period","source","url","value")):
            raise ValueError("Osservazione incompleta")
        import math
        if not math.isfinite(float(row["value"])):
            raise ValueError("Valore statistico non finito")
        if by_key.get(key(row))!=row:
            by_key[key(row)]=row
            changed+=1
    if changed:
        write_tsv(path,OBS_FIELDS,list(by_key.values()))
        write_json(DATA/"pulse_observations_manifest.json",{
            "generated_at":now_iso(),"rows":len(by_key),
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "file":"pulse_observations.tsv","note":"Serie osservate, periodo originale."})
    return changed


def demo_refresh(temp: Path) -> dict:
    work=temp/"demo"
    asset=init_statistics_work(work)
    run_original("generate_territories.py",work,seconds=180)
    run_original("generate_pulse_events.py",work,seconds=4800)
    events=read_tsv(asset/"pulse_events.tsv",EVENT_FIELDS,minimum=50)
    observations=read_tsv(asset/"pulse_observations_demo.tsv",OBS_FIELDS,minimum=1)
    meta=read_json(asset/"pulse_manifest.json",{})
    period=meta.get("latest_period","")
    prior=read_json(DATA/"pulse_manifest.json",{})
    prior_period=(prior.get("demo") or {}).get("latest_period","")
    if not period or period_key(period)<period_key(prior_period):
        raise ValueError("DEMO: periodo precedente all'ultimo dato valido")
    if any(row["source_family"]!="DEMO ISTAT — Bilancio demografico mensile" or row["period"]!=period for row in events):
        raise ValueError("DEMO: eventi di provenienza o periodo incoerenti")
    changed_obs=merge_observations(observations)
    changed=merge_events(events)
    refresh_manifest(demo=meta)
    return {"status":"ok","latest_period":period,
            "events_validated":len(events),"events_added_or_updated":changed,
            "observations_new_or_revised":changed_obs,
            "coverage":meta.get("demo_coverage",{}),
            "message":"DEMO: acquisizione e motore statistico originali, nessuna generazione forzata."}


def news_refresh(temp: Path) -> dict:
    work = temp / "news"
    for name in ("articles.json", "candidates.json", "index.json", "editorial_quality_status.json",
                 "green_index.json", "territori_index.json"):
        copy_if_exists(DATA / "news" / name, work / "data" / "news" / name)
    copy_if_exists(DATA / "news" / "approved_features.json", work / "data" / "news" / "approved_features.json")
    copy_if_exists(DATA / "news_radar_sources.json", work / "data" / "news_radar_sources.json")
    # Previously verified source events are eligible for original PULSE analysis.
    # No live ISTAT request and no redistribution of an entire external article.
    copy_if_exists(DATA / "pulse_events.tsv", work / "data" / "pulse_events.tsv")
    copy_if_exists(DATA / "editorial_casefiles.json", work / "data" / "editorial_casefiles.json")
    cfg = read_json(DATA / "news_radar_sources.json", {})
    feeds = cfg.get("feeds", [])
    if not isinstance(feeds, list) or len(feeds) < 2:
        raise ValueError("Catalogo RSS insufficiente")
    run_original("update_news_radar.py", work, seconds=850)
    base = work / "data" / "news"
    arts = read_json(base / "articles.json", {})
    candidates = read_json(base / "candidates.json", {})
    idx = read_json(base / "index.json", {})
    # Reapply separately retained, independently reviewed Italian longforms.
    # A normal RSS refresh must never silently erase approved PULSE journalism.
    approved_store = DATA / "editorial_italia" / "published_articles.json"
    if approved_store.exists() and os.environ.get('PULSE_SOURCE_ONLY') != '1':
        try:
            from scripts.pulse_italia_reviewed_publish import overlay_approved
        except ModuleNotFoundError:
            from pulse_italia_reviewed_publish import overlay_approved
        arts, idx, restored = overlay_approved(
            arts, idx, read_json(approved_store, {"articles": []}))
        write_json(base / "articles.json", arts)
        write_json(base / "index.json", idx)
        print("PULSE editoriale Italia: mantenuti", restored,
              "approfondimenti verificati nel feed", flush=True)
    article_list = arts.get("articles", [])
    old_list = read_json(DATA / "news" / "articles.json", {}).get("articles", [])
    topical_stream=(os.environ.get("PULSE_SOURCE_ONLY")=="1"
                    and idx.get("source_topic_policy")=="v2")
    if not isinstance(article_list,list) or not article_list:
        raise ValueError("Archivio RSS vuoto: non sostituisco la copia valida")
    if not topical_stream and len(article_list) < max(15, len(old_list)//2):
        raise ValueError("Archivio RSS incompleto: non sostituisco la copia valida")
    if not isinstance(candidates.get("candidates"), list):
        raise ValueError("Diagnostica RSS assente")
    fail = [c for c in candidates["candidates"] if c.get("status") == "radar_error"]
    success_records = [c for c in candidates["candidates"] if c.get("status") == "radar_fetched"]
    successes = len(success_records)
    if successes < 1:
        raise ValueError("Tutti i feed RSS risultano irraggiungibili")
    if topical_stream and len(article_list)<len(old_list) and successes < max(1,len(feeds)//2):
        raise ValueError("Pulizia archivio sospesa: raggiunto meno di metà delle fonti")
    article_ids = {x.get("id") for x in article_list}
    subsets = []
    for key in ("oggi", "ieri", "archivio"):
        ids = idx.get(key)
        if not isinstance(ids, list) or not set(ids).issubset(article_ids):
            raise ValueError(f"Indice {key} incoerente con archivio")
        subsets.extend(ids)
    if len(set(subsets)) != len(subsets):
        raise ValueError("Articoli duplicati fra OGGI/IERI/ARCHIVIO")
    if not idx.get("generated_at"):
        raise ValueError("Nessuna data generazione indice")
    audit = read_json(base / "editorial_quality_status.json", None)
    if not isinstance(audit, dict) or audit.get("discovery_feeds_reached") != successes:
        raise ValueError("Diagnostica editoriale nuova incoerente con i feed raggiunti")
    if topical_stream and audit.get("source_topic_policy")!="v2":
        raise ValueError("Diagnostica filtro tematico incoerente")
    daily = audit.get("daily", {})
    if not isinstance(daily, dict) or not all(key in daily for key in ("oggi", "ieri", "archivio")):
        raise ValueError("Contatori OGGI/IERI/ARCHIVIO non presenti nell'audit")
    for sectional in ("green","territori"):
        section=read_json(base/(sectional+"_index.json"),None)
        if not isinstance(section,dict) or section.get("type")!="editorial_news_index_not_api_observations":
            raise ValueError(f"Indice editoriale {sectional} non valido")
        for bucket in ("oggi","ieri","archivio"):
            ids=section.get(bucket)
            if not isinstance(ids,list) or not set(ids).issubset(set(idx[bucket])):
                raise ValueError(f"{sectional}/{bucket}: indici incoerenti con News")
    for name in ("articles.json", "candidates.json", "index.json", "editorial_quality_status.json",
                 "green_index.json", "territori_index.json"):
        copy_if_exists(base / name, DATA / "news" / name)
    return {"status": "ok", "feeds_configured": len(feeds), "feeds_reached": successes,
            "feeds_failed": len(fail), "articles_total": len(article_list),
            "oggi": len(idx["oggi"]), "ieri": len(idx["ieri"]),
            "oggi_verificati": int(daily["oggi"].get("original_pulse_verified",0)),
            "oggi_stampa": int(daily["oggi"].get("media_reports_not_primary_verified",0)),
            "ieri_verificati": int(daily["ieri"].get("original_pulse_verified",0)),
            "ieri_stampa": int(daily["ieri"].get("media_reports_not_primary_verified",0)),
            "message": "Radar titoli originali: nessuna elaborazione editoriale, grafico o AI."}


def init_statistics_work(work: Path) -> Path:
    asset = work / "app" / "src" / "main" / "assets"
    asset.mkdir(parents=True, exist_ok=True)
    for name in ("sources_catalog.json", "pulse_events.tsv", "pulse_observations.tsv"):
        copy_if_exists(DATA / name, asset / name)
    copy_if_exists(DATA / "gse_fer_last_good.json", work / "data" / "gse_fer_last_good.json")
    copy_if_exists(DATA / "pulse_events_sdmx_last_good.tsv", work / "data" / "pulse_events_sdmx_last_good.tsv")
    return asset


def green_refresh(temp: Path) -> dict:
    work=temp/"green"
    asset=init_statistics_work(work)
    run_original("generate_green_events.py",work,seconds=1200)
    new=read_tsv(asset/"pulse_events_green.tsv",EVENT_FIELDS,minimum=0)
    stats=read_json(asset/"pulse_green_status.json",{}) or {}
    if not stats.get("sources"):
        raise ValueError("GREEN: diagnostica delle fonti assente")
    changed=merge_events(new) if new else 0
    blocked=[]
    for name,source in stats["sources"].items():
        if source.get("status") in ("error","credential_required") or source.get("fallback_last_good") or source.get("refresh_degraded") or source.get("http_ok") is False:
            blocked.append({"source":name,"status":source.get("status"),
                            "error":source.get("refresh_error") or source.get("note",""),
                            "latest_period":source.get("latest_period","")})
    write_json(DATA/"pulse_green_status.json",stats)
    copy_if_exists(asset/"sources_catalog.json",DATA/"sources_catalog.json")
    copy_if_exists(work/"data"/"gse_fer_last_good.json",DATA/"gse_fer_last_good.json")
    refresh_manifest()
    return {"status":"degraded" if blocked or not new else "ok",
            "events_validated":len(new),"events_added_or_updated":changed,
            "sources_total":int(stats.get("sources_total",0)),
            "sources_with_events":int(stats.get("feed_sources",0)),
            "sources_error":int(stats.get("error_sources",0)),
            "sources_blocked":blocked,
            "message":"Controllo Green: cache e credenziali mancanti non sono nuovi dati."}


def sdmx_refresh(temp: Path) -> dict:
    work=temp/"territori"
    asset=init_statistics_work(work)
    run_original("generate_sdmx_events.py",work,seconds=950)
    records=read_tsv(asset/"pulse_events_sdmx.tsv",EVENT_FIELDS,minimum=0)
    observations=read_tsv(asset/"pulse_observations_sdmx.tsv",OBS_FIELDS,minimum=0)
    meta=read_json(asset/"pulse_sdmx_meta.json",{}) or {}
    sources=meta.get("sources",[])
    if not sources:
        raise ValueError("SDMX: diagnostica per serie assente")
    previous=(read_json(DATA/"pulse_manifest.json",{}) or {}).get("istatdata_sdmx",{})
    prev_by_name={x.get("name"):x for x in previous.get("sources",[])}
    now=datetime.now(timezone.utc)
    stale=[]
    for row in sources:
        prior=prev_by_name.get(row.get("name"),{})
        if row.get("acquisition_status")=="ok":
            row["last_success_at"]=now_iso()
        else:
            row["last_success_at"]=prior.get("last_success_at")
            row["latest_period"]=row.get("cached_period") or prior.get("latest_period") or ""
        try:
            age=(now-datetime.fromisoformat(row["last_success_at"])).total_seconds()/3600
        except (TypeError,KeyError,ValueError):
            age=None
        row["hours_since_verified"]=round(age,1) if age is not None else None
        if age is None or age>72 or row.get("acquisition_status") in ("fetch_error","series_not_found"):
            stale.append(row["name"])
    meta["latest_period"]=max((x.get("latest_period","") for x in sources),key=period_key,default="")
    changes=merge_events(records) if records else 0
    new_count=merge_observations(observations)
    refresh_manifest(istatdata_sdmx=meta)
    copy_if_exists(asset/"sources_catalog.json",DATA/"sources_catalog.json")
    copy_if_exists(work/"data"/"pulse_events_sdmx_last_good.tsv",DATA/"pulse_events_sdmx_last_good.tsv")
    return {"status":"degraded" if stale or not observations else "ok",
            "connected_series":int(meta.get("connected_series",0)),
            "fallback_series":int(meta.get("fallback_series",0)),
            "deferred_series":int(meta.get("deferred_series",0)),
            "failed_series":int(meta.get("failed_series",0)),
            "stale_or_failed_series":stale,"events_validated":len(records),
            "events_added_or_updated":changes,"observations_new_or_revised":new_count,
            "message":"SDMX: serie non previste nel lotto distinte da errori e ultimo periodo verificato."}


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("all","news","stats","demo","audit"),default="all")
    p.add_argument("--dry-run",action="store_true",help="Convalida risorse locali; non effettua download")
    args=p.parse_args()
    if args.dry_run:
        print("Validazione sola lettura dei dati esistenti")
        print("Notizie:",len(read_json(DATA/"news"/"articles.json",{}).get("articles",[])))
        print("Eventi:",len(read_tsv(DATA/"pulse_events.tsv",EVENT_FIELDS)))
        print("Osservazioni:",len(read_tsv(DATA/"pulse_observations.tsv",OBS_FIELDS)))
        print("Fonti RSS:",len(read_json(DATA/"news_radar_sources.json",{}).get("feeds",[])))
        return 0
    status = read_json(STATUS, {"version":1,"sections":{}})
    sections=status.setdefault("sections",{})
    status["last_check_at"]=now_iso()
    tasks = [("green",green_refresh),("territori",sdmx_refresh),("regioni",demo_refresh)] if args.mode=="audit" else [("regioni",demo_refresh)] if args.mode=="demo" else [("notizie",news_refresh)] if args.mode=="news" else (
            [("notizie",news_refresh),("green",green_refresh),("territori",sdmx_refresh)] if args.mode=="all"
            else [("green",green_refresh),("territori",sdmx_refresh)])
    failed=0
    with tempfile.TemporaryDirectory(prefix="pulse_refresh_") as tmp:
        for name,job in tasks:
            print(f"\n===== PULSE: {name.upper()} =====",flush=True)
            prior=sections.get(name,{})
            try:
                result=job(Path(tmp))
                result["last_attempt_at"] = now_iso()
                if result.get("status") == "ok":
                    result["last_success_at"] = result["last_attempt_at"]
                else:
                    failed += 1
                    result["last_success_at"] = prior.get("last_success_at")
                    print(f"::warning::{name} degradato: {result.get('message', 'dati non aggiornati')}", flush=True)
                sections[name] = result
            except (Exception,subprocess.TimeoutExpired) as exc:
                failed+=1
                sections[name]={**prior,"status":"error","last_attempt_at":now_iso(),
                                "error":str(exc)[:240]}
                print(f"::warning::{name}: {type(exc).__name__}: {exc}",flush=True)
    status["sections"]=sections
    status["latest_check_errors"]=failed
    status["note"]=("Notizie, DEMO, Green e SDMX hanno controlli distinti; "
                    "seguono la frequenza dei rispettivi servizi API. Un controllo non equivale "
                    "a nuove osservazioni. Le APK installate non sono modificate dal repository.")
    write_json(STATUS,status)
    # Machine-readable routing contract for future Android clients.
    endpoints = {
        "schema_version": "pulse-data-route-v1",
        "repository": "AppInRome/ISTAT-PULSE-DATA",
        "checked_at": status["last_check_at"],
        "sections": {},
        "notizie": {"index": "data/news/index.json", "articles": "data/news/articles.json",
                    "quality": "data/news/editorial_quality_status.json",
                    "green_index": "data/news/green_index.json",
                    "territori_index": "data/news/territori_index.json"},
        "pubblicazioni": {"articles": "data/news/observer_articles.json",
                          "sources": "data/observer_sources_registry.json",
                          "status": "data/observer_refresh_status.json"},
        "territori": {"events": "data/pulse_events.tsv", "observations": "data/pulse_observations.tsv",
                       "manifest": "data/pulse_observations_manifest.json",
                       "editorial_news_index":"data/news/territori_index.json"},
        "regioni": {"events":"data/pulse_events.tsv","observations":"data/pulse_observations.tsv","manifest":"data/pulse_manifest.json"},
        "green": {"events": "data/pulse_events.tsv", "status": "data/pulse_green_status.json",
                  "editorial_news_index":"data/news/green_index.json"},
    }
    for section, info in sections.items():
        endpoints["sections"][section] = {"status": info.get("status", "unknown"),
            "last_success_at": info.get("last_success_at"),
            "last_attempt_at": info.get("last_attempt_at")}
    write_json(DATA / "live_data_index.json", endpoints)
    print(json.dumps(status,ensure_ascii=False,indent=2))
    # Do not discard successful updates if a different section fails. The
    # workflow commits the diagnostic status and fails in its final check.
    return 0


if __name__=="__main__":
    raise SystemExit(main())