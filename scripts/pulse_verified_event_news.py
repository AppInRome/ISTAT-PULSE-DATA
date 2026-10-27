"""PULSE original analytical briefs from existing *validated* public-source events.

Editorial publication date is today's date, while statistical period stays
unaltered. Never imply that an older dataset was released today.
"""
from __future__ import annotations

import csv
import hashlib
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ALLOWED = ("SEGNALE PULSE", "ULTIMO DATO UFFICIALE")
UNIT_RE = re.compile(r"Unità di misura dichiarata:\s*([^¦.\n]+)", re.I)


def _format(value):
    number = f"{value:,.2f}".rstrip("0").rstrip(".")
    return number.replace(",", "_").replace(".", ",").replace("_", ".")


def _extract_unit(analysis):
    match=UNIT_RE.search(analysis or "")
    if not match: return None
    unit=match.group(1).strip()
    if unit.casefold() in ("valori percentuali", "percentuale", "percentuali"):
        return "%"
    return unit if 0 < len(unit) < 60 else None


def candidate_event(row):
    if row.get("scope") != "GREEN": return None
    if not str(row.get("validation_status", "")).startswith(ALLOWED): return None
    period=str(row.get("period", "")).strip()
    if not re.fullmatch(r"20\d{2}", period): return None
    if not (2024 <= int(period) <= datetime.now(timezone.utc).year): return None
    original=str(row.get("source_url",""))
    host=urlsplit(original).hostname or ""
    if urlsplit(original).scheme != "https" or not host: return None
    unit=_extract_unit(row.get("analysis", ""))
    if not unit: return None
    annual=str(row.get("annual","")).split("|")
    if not annual or not annual[-1]: return None
    try:
        value=float(annual[-1].strip())
        if not math.isfinite(value): return None
    except ValueError: return None
    indicator=str(row.get("indicator","")).split(" · ")[-1].strip()
    if len(indicator)<7: return None
    return {"indicator":indicator,"period":period,"value":value,"unit":unit,
            "host":host.removeprefix("www."),"url":original,"row":row}


def augment_with_verified_events(by_id, events_file: Path, now, max_articles=4):
    """Stable source-diverse selection. Never rebirth the same dataset tomorrow."""
    if not events_file.is_file(): return 0
    with events_file.open("r", encoding="utf-8-sig", newline="") as handle:
        events=[e for row in csv.DictReader(handle,delimiter="\t")
                if (e:=candidate_event(row))]
    events.sort(key=lambda e:(e["period"],
                              float(e["row"].get("score",0) or 0),
                              e["row"].get("id","")),reverse=True)
    selected=[]; publishers=set()
    for event in events:
        producer=event["row"].get("source_family","")
        if producer in publishers: continue
        publishers.add(producer)
        selected.append(event)
        if len(selected)>=max_articles:break
    added=0
    for event in selected:
        row=event["row"]
        identity=(row["id"] + "|" + event["period"] + "|" + event["indicator"])
        fp=hashlib.sha256(identity.encode()).hexdigest()[:24]
        article_id="PULSE-"+fp[:16].upper()
        if article_id in by_id:continue
        topic=("ENERGIA" if "energi" in event["indicator"].lower() else
               "MOBILITA" if "mobilit" in row.get("indicator","").lower() else "AMBIENTE")
        indicator=event["indicator"]
        value=event["value"]
        unit=event["unit"]
        period=event["period"]
        source=event["host"]
        territory=row.get("municipality") or "Italia"
        title=f"{indicator}: {_format(value)} {unit} nel {period}"
        intro=(f"PULSE analizza il dato ufficiale di {source} relativo a {indicator.lower()}: "
               f"nel {period} il valore per {territory} è {_format(value)} {unit}. "
               "Questa è un'analisi editoriale PULSE, non la data di pubblicazione della fonte.")
        commentary=(f"Il periodo statistico documentato è {period}. L'indicatore è espresso in "
                    f"{unit}; un singolo valore non permette di dedurre un andamento o le sue cause.")
        payload={
            "id":article_id,"story_fingerprint":fp,
            "published_at":now.astimezone(timezone.utc).isoformat(),
            "last_seen_at":now.astimezone(timezone.utc).isoformat(),
            "topic":topic,"pulse_score":min(99,max(70,int(float(row.get("score",70) or 70)))),
            "patterns":row.get("patterns","").split("|"),
            "public_source":{"url":event["url"],"domain":source,
                              "role":"primary_statistical_source",
                              "verification_method":"previously_validated_source_event",
                              "verification_score":100},
            "discovery":{"visible":False,"role":"independent_statistical_analysis"},
            "origin_kind":"pulse_verified_event",
            "period_reference":period,
            "headline":title,"summary":intro,
            "pulse_title":title,"pulse_summary":intro,
            "pulse_article_body":[
                {"heading":"Il dato statistico","text":intro},
                {"heading":"Come interpretarlo","text":commentary},
                {"heading":"Trasparenza e fonti","text":
                 f"La serie è stata acquisita e validata dal motore PULSE da {source}. "
                 "La fonte originale è collegata in questa notizia; la data di PULSE "
                 "indica l'uscita dell'analisi, non la diffusione del dataset."}
            ],
            "byline":"Redazione PULSE",
            "statistical_claims":[{"raw_value":f"{_format(value)} {unit}","verified":True,
                                   "period":period,"indicator":indicator}],
            "verified_series":[{"indicator":indicator,"unit":unit,"verified":True,
                                "source_url":event["url"],
                                "observations":[{"period":period,"value":value}]}],
            "territories":[territory],
            "chart_spec":{"type":"bar","status":"verified","title":indicator,"unit":unit,
                          "single_observation":True,"source_url":event["url"],
                          "data":[{"period":period,"value":value}]},
            "table_spec":{"status":"verified",
                          "columns":["Periodo","Indicatore","Territorio","Valore","Unità"],
                          "rows":[[period,indicator,territory,_format(value),unit]],
                          "source_url":event["url"]},
            "editorial_status":"verified_primary_match",
            "publication_status":"published",
            "verification_tier":"previously_verified_official_single_observation"
        }
        by_id[article_id]=payload
        added+=1
    return added
