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
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def merge_events(rows: list[dict]) -> int:
    """Never delete old sources when a service is temporarily unavailable."""
    path = DATA / "pulse_events.tsv"
    old = read_tsv(path, EVENT_FIELDS, minimum=1)
    by_id = {r["id"]: r for r in old if r.get("id")}
    added_or_changed = 0
    for item in rows:
        if not all(str(item.get(k, "")).strip() for k in ("id", "indicator", "period", "source_family", "source_url")):
            raise ValueError("Evento privo di ID, periodo, fonte o indicatore")
        prior = by_id.get(item["id"])
        if prior and str(item["period"]) < str(prior.get("period", "")):
            continue  # never downgrade a verified period
        if prior != item:
            by_id[item["id"]] = item
            added_or_changed += 1
    if added_or_changed:
        write_tsv(path, EVENT_FIELDS, sorted(by_id.values(), key=lambda x: (x.get("id", ""))))
        manifest = read_json(DATA / "pulse_manifest.json", {})
        if manifest:
            manifest["feed_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest["feed_events"] = len(by_id)
            manifest["generated_at"] = now_iso()
            manifest["note_refresh"] = "Incrementale: mantiene gli ultimi dati validi; le date dei periodi statistici restano originali."
            write_json(DATA / "pulse_manifest.json", manifest)
    return added_or_changed


def news_refresh(temp: Path) -> dict:
    work = temp / "news"
    for name in ("articles.json", "candidates.json", "index.json", "editorial_quality_status.json"):
        copy_if_exists(DATA / "news" / name, work / "data" / "news" / name)
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
    article_list = arts.get("articles", [])
    old_list = read_json(DATA / "news" / "articles.json", {}).get("articles", [])
    if not isinstance(article_list, list) or len(article_list) < max(15, len(old_list)//2):
        raise ValueError("Archivio RSS incompleto: non sostituisco la copia valida")
    if not isinstance(candidates.get("candidates"), list):
        raise ValueError("Diagnostica RSS assente")
    fail = [c for c in candidates["candidates"] if c.get("status") == "radar_error"]
    success_records = [c for c in candidates["candidates"] if c.get("status") == "radar_fetched"]
    successes = len(success_records)
    if successes < 1:
        raise ValueError("Tutti i feed RSS risultano irraggiungibili")
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
    daily = audit.get("daily", {})
    if not isinstance(daily, dict) or not all(key in daily for key in ("oggi", "ieri", "archivio")):
        raise ValueError("Contatori OGGI/IERI/ARCHIVIO non presenti nell'audit")
    for name in ("articles.json", "candidates.json", "index.json", "editorial_quality_status.json"):
        copy_if_exists(base / name, DATA / "news" / name)
    return {"status": "ok", "feeds_configured": len(feeds), "feeds_reached": successes,
            "feeds_failed": len(fail), "articles_total": len(article_list),
            "oggi": len(idx["oggi"]), "ieri": len(idx["ieri"]),
            "message": "Notizie verificabili; zero articoli recenti non equivale a errore di rete."}


def init_statistics_work(work: Path) -> Path:
    asset = work / "app" / "src" / "main" / "assets"
    asset.mkdir(parents=True, exist_ok=True)
    for name in ("sources_catalog.json", "pulse_events.tsv", "pulse_observations.tsv"):
        copy_if_exists(DATA / name, asset / name)
    copy_if_exists(DATA / "gse_fer_last_good.json", work / "data" / "gse_fer_last_good.json")
    copy_if_exists(DATA / "pulse_events_sdmx_last_good.tsv", work / "data" / "pulse_events_sdmx_last_good.tsv")
    return asset


def green_refresh(temp: Path) -> dict:
    work = temp / "green"
    asset = init_statistics_work(work)
    run_original("generate_green_events.py", work, seconds=850)
    new = read_tsv(asset / "pulse_events_green.tsv", EVENT_FIELDS, minimum=1)
    stats = read_json(asset / "pulse_green_status.json", {})
    ok = int(stats.get("feed_sources", 0))
    if ok < 1 or not stats.get("sources"):
        raise ValueError("GREEN: nessuna fonte numerica verificata; mantengo ultimo dato valido")
    changed = merge_events(new)
    # SOURCE statuses are diagnostics, not proof that every indicator was updated.
    write_json(DATA / "pulse_green_status.json", stats)
    copy_if_exists(asset / "sources_catalog.json", DATA / "sources_catalog.json")
    return {"status":"ok", "events_validated":len(new), "events_added_or_updated":changed,
            "sources_total":int(stats.get("sources_total",0)), "sources_with_events":ok,
            "sources_error":int(stats.get("error_sources",0)),
            "message":"Indicatori aggiornati solo quando la rispettiva fonte ha fornito dati verificati."}


def sdmx_refresh(temp: Path) -> dict:
    work = temp / "territori"
    asset = init_statistics_work(work)
    run_original("generate_sdmx_events.py", work, seconds=850)
    # SDMX reports individual sources and preserves last-good for offline API gaps.
    records = read_tsv(asset / "pulse_events_sdmx.tsv", EVENT_FIELDS, minimum=1)
    # A server outage can leave a valid cached event list but NO newly acquired
    # observations. Preserve previous data and report degraded, not healthy.
    observations = read_tsv(asset / "pulse_observations_sdmx.tsv", OBS_FIELDS, minimum=0)
    meta = read_json(asset / "pulse_sdmx_meta.json", {})
    connected = int(meta.get("connected_series", 0))
    fallback = int(meta.get("fallback_series", 0))
    if connected < 1 or not observations:
        return {"status": "degraded", "connected_series": connected,
                "fallback_series": fallback,
                "events_validated": len(records),
                "observations_new_or_revised": 0,
                "message": "SDMX senza osservazioni nuove verificabili: mantenuta cache precedente, riprovare al controllo seguente."}
    changes = merge_events(records)
    # Merge observations without erasing other datasets or historical periods.
    old_path = DATA / "pulse_observations.tsv"
    old = read_tsv(old_path, OBS_FIELDS, minimum=1)
    by_key = {(r["source"],r["indicator"],r["territory"],r["period"]): r for r in old}
    new_count = 0
    for row in observations:
        if not all(str(row.get(x,"")).strip() for x in ("indicator","territory","period","source","url","value")):
            raise ValueError("Osservazione SDMX incompleta")
        try: float(row["value"])
        except ValueError as exc: raise ValueError("Valore SDMX non numerico") from exc
        key=(row["source"],row["indicator"],row["territory"],row["period"])
        if by_key.get(key) != row:
            by_key[key]=row
            new_count+=1
    if new_count:
        write_tsv(old_path, OBS_FIELDS, list(by_key.values()))
        manifest={"generated_at":now_iso(),"rows":len(by_key),"sha256":hashlib.sha256(old_path.read_bytes()).hexdigest(),
                  "file":"pulse_observations.tsv","note":"Serie osservate con anno statistico originale, aggiornamento incrementale."}
        write_json(DATA / "pulse_observations_manifest.json",manifest)
    copy_if_exists(asset / "sources_catalog.json", DATA / "sources_catalog.json")
    # Keep last-good source cache only after verified inputs.
    copy_if_exists(work / "data" / "pulse_events_sdmx_last_good.tsv", DATA / "pulse_events_sdmx_last_good.tsv")
    return {"status":"ok", "connected_series":connected,"fallback_series":fallback,
            "events_validated":len(records), "events_added_or_updated":changes,
            "observations_new_or_revised":new_count,
            "message":"Serie SDMX: i periodi statistici originali restano visibili."}


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("all","news","stats"),default="all")
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
    tasks = [("notizie",news_refresh)] if args.mode=="news" else (
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
    status["note"]=("Un controllo giornaliero non significa nuovi dati ogni giorno. "
                    "L'APK va configurata per leggere AppInRome: il repository non modifica l'APK installata.")
    write_json(STATUS,status)
    # Machine-readable routing contract for future Android clients.
    endpoints = {
        "schema_version": "pulse-data-route-v1",
        "repository": "AppInRome/ISTAT-PULSE-DATA",
        "checked_at": status["last_check_at"],
        "sections": {},
        "notizie": {"index": "data/news/index.json", "articles": "data/news/articles.json"},
        "territori": {"events": "data/pulse_events.tsv", "observations": "data/pulse_observations.tsv",
                       "manifest": "data/pulse_observations_manifest.json"},
        "green": {"events": "data/pulse_events.tsv", "status": "data/pulse_green_status.json"},
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