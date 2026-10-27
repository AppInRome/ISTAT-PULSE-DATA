#!/usr/bin/env python3
"""Aggiornamento conservativo Pubblicazioni: solo RSS ufficiali verificati.

Non attribuisce numeri non verificati, non sovrascrive l'archivio quando
una fonte fallisce, non legge risultati Google News come fonte primaria.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ARCHIVE = Path("data/news/observer_articles.json")
STATUS = Path("data/observer_refresh_status.json")
FEEDS = (
    ("CNA", "cna.it", "https://www.cna.it/feed/"),
    ("CNR", "cnr.it", "https://www.cnr.it/it/news/rss"),
    ("SVIMEZ", "svimez.info", "https://lnx.svimez.info/svimez/feed/"),
    ("SINAB", "sinab.it", "https://sinab.it/feed/"),
)
STAT = re.compile(
    r"\b(dat[io]|statistic[hae]|rapport[oi]|osservator[io]|indagin[ei]|ricerc[hae]"
    r"|mercat[oi]|rinnovabil[ie]|energ[ia]|ambient[ea]|occupazion[ei]|imprese"
    r"|salut[ei]|tass[oi]|percentual[ie]|prezz[io]|reddit[io]|pension[ei]"
    r"|agricoltur[ae]|biologic[oa]|clima|economi[ae]|industria)\b", re.I
)

def host_allowed(url: str, domain: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and (host == domain or host.endswith("." + domain))
    except Exception:
        return False

def get_feed(url: str, domain: str) -> bytes:
    if not host_allowed(url, domain):
        raise ValueError("Dominio RSS non ufficiale")
    req = urllib.request.Request(url, headers={"User-Agent": "PulseData/2026 official-publication-monitor", "Accept": "application/rss+xml,application/atom+xml,application/xml"})
    with urllib.request.urlopen(req, timeout=12) as response:
        final = response.geturl()
        if not host_allowed(final, domain):
            raise ValueError("Redirect verso dominio non autorizzato")
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Feed troppo grande")
    return raw

def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()

def items_from_xml(payload: bytes):
    root = ET.fromstring(payload)
    result = []
    for item in root.iter():
        if local(item.tag) not in ("item", "entry"):
            continue
        title = link = date = ""
        for child in item:
            tag = local(child.tag)
            value = ("".join(child.itertext()) or "").strip()
            if tag == "title": title = re.sub(r"\s+", " ", value)
            elif tag == "link": link = child.attrib.get("href", "") or value
            elif tag in ("pubdate", "published", "updated", "date") and not date:
                date = value
        if title and link and date:
            result.append((title[:250], link.strip(), date))
    return result[:45]

def parse_date(text: str):
    try:
        dt = parsedate_to_datetime(text)
    except (ValueError, TypeError, IndexError):
        try: dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError: return None
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def topic_for(title: str):
    text = title.casefold()
    if re.search(r"titoli di stato|emissioni obbligazion|debito pubblico", text):
        return "ECONOMIA"
    if re.search(r"clima|rinnovabil|energia|rifiut|ambient|biodivers|agricoltur|emissioni (di co2|gas serra)", text):
        return "AMBIENTE"
    if re.search(r"lavor|occupazion|imprese|stipend", text): return "LAVORO"
    if re.search(r"sanit|salute|malatti", text): return "SALUTE"
    if re.search(r"scuola|universit|istruzion", text): return "ISTRUZIONE"
    return "ECONOMIA"

def update(archive: Path = ARCHIVE, status_path: Path = STATUS, fetcher=get_feed, now=None):
    now = now or datetime.now(timezone.utc)
    obj = json.loads(archive.read_text(encoding="utf-8"))
    original = obj.get("articles", [])
    if not isinstance(original, list) or len(original) < 1000:
        raise ValueError("Archivio Osservatori precedente incompleto: annullo")
    by_id = {x["id"]: x for x in original if isinstance(x, dict) and x.get("id")}
    existing_urls = {x.get("public_source", {}).get("url") for x in by_id.values()}
    stats = {}
    additions = 0
    for name, domain, url in FEEDS:
        checked = {"status": "error", "new": 0}
        try:
            data = fetcher(url, domain)
            parsed = items_from_xml(data)
            checked["status"] = "ok"
            checked["items"] = len(parsed)
            for title, link, date in parsed:
                dt = parse_date(date)
                if not dt or dt.year != now.year or dt > now + timedelta(hours=6):
                    continue
                if not host_allowed(link, domain) or not STAT.search(title):
                    continue
                uid = "OBS-" + hashlib.sha256((name + "|" + link.split("#", 1)[0]).encode()).hexdigest()[:18].upper()
                if uid in by_id or link in existing_urls:
                    continue
                date_text = dt.strftime("%d/%m/%Y")
                summary = f"{name} ha pubblicato il {date_text} il documento «{title}». PULSE segnala la pubblicazione ufficiale; eventuali cifre vanno verificate nel documento originale."
                by_id[uid] = {
                    "id": uid, "published_at": dt.isoformat().replace("+00:00", "Z"),
                    "observer": name, "topic": topic_for(title),
                    "article_type": "DOCUMENTO_SENZA_DATI_NUMERICI",
                    "pulse_title": title, "pulse_summary": summary,
                    "pulse_article_body": [summary],
                    "key_figures": [], "chart_points": [], "pulse_score": 0, "patterns": [],
                    "public_source": {"url": link, "domain": domain, "role": "primary_institutional_source",
                                      "verification_method": "official_rss_link_and_publication_date"},
                    "headline": title, "summary": summary, "territories": ["italia"],
                    "editorial_status": "source_publication_verified",
                    "publication_status": "published",
                }
                existing_urls.add(link)
                additions += 1
                checked["new"] += 1
        except Exception as exc:
            checked["error"] = str(exc)[:180]
        stats[name] = checked
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps({
        "checked_at": now.isoformat(), "feeds_configured": len(FEEDS),
        "feeds_reached": sum(x["status"] == "ok" for x in stats.values()),
        "articles_new": additions, "articles_total": len(by_id),
        "sources": stats, "other_institutions": "not_yet_connected"
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if additions:
        obj["articles"] = sorted(by_id.values(), key=lambda a: a.get("published_at", ""), reverse=True)
        obj["generated_at"] = now.isoformat()
        obj["source_count"] = max(65, int(obj.get("source_count", 0)))
        tmp = archive.with_suffix(".staging.json")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(archive)
    return {"new": additions, "total": len(by_id), "reached": sum(x["status"] == "ok" for x in stats.values())}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("4 feed ufficiali configurati; archivio:",
              len(json.loads(ARCHIVE.read_text(encoding="utf-8")).get("articles", [])))
    else:
        print(json.dumps(update(), ensure_ascii=False), flush=True)
