#!/usr/bin/env python3
"""Fast national/local statistical-news radar, separate from verified PULSE articles.

The newsroom MUST distinguish an outlet-reported claim from an independently
verified official number. This module never fabricates a table or chart.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

EXCLUDED = re.compile(
    r"\b(?:israele|gaza|hamas|netanyahu|elezioni (?:usa|israeliane)|"
    r"calcio|serie a|champions|marathon|maratona|scommess|slot|"
    r"pokerstars|bet365|borsa di tokyo|ftse mib|bitcoin|crypto|"
    r"premio nobel|personaggio televisivo|scandalo|omicidio|"
    r"bonus colonnine|ravvedimento speciale|rottamazione|"
    r"backlog|nuov[ea] commess[ae]|opa|titoli azionari|"
    r"trimestrale aziendale|prodotto pubblicitario|"
    r"previsioni astrologiche)\b", re.I
)
PUBLIC_INTEREST = re.compile(
    r"\b(?:istat|eurostat|censis|ispra|inps|inail|gimbe|"
    r"consumo di suolo|povert[aà]|reddit[io]|occupazion[ei]|"
    r"disoccupazion[ei]|salari?|stipendi?|pension[ei]|"
    r"prezz[io]|inflazion[ei]|cost[io] della vita|"
    r"mercato auto|auto usate|autovetture|immobil[ei]|case|"
    r"nascit[ea]|fecondit[aà]|residenti|demografi[ae]|"
    r"export|importazioni|turism[oi]|presenz[ea] turist|"
    r"emissioni di gas|clima|ambient[ea]|rifiut[io]|"
    r"energia|fonti rinnovabili|scuola|studenti|"
    r"sanit[aà]|salute|aspettativa di vita|"
    r"istruzione|neet|imprese|industrial[ei]|"
    r"rapport[oi] (?:bes|annual[ei]|statistic[io])|"
    r"statistic[hae]|indagin[ei]|rilevazion[ei])\b", re.I
)
NUMERIC_CLAIM = re.compile(
    r"(?<![\w])(?:[+-]?\d{1,3}(?:[.,]\d{1,3})?)\s*%"
    r"|(?<![\w])\d[\d.,]*\s*(?:milioni|miliardi|mila|migliaia|"
    r"kmq|km²|chilometri quadrati|tonnellate|persone|abitanti|"
    r"lavoratori|posti di lavoro|occupati|veicoli|euro|famiglie)\b"
    r"|(?<![\w])\d{1,3}[.,]\d{1,3}(?!\w)", re.I
)
LOCAL_CONTEXT = re.compile(
    r"\b(?:italia|italian[ioe]|lombardia|piemonte|veneto|"
    r"toscana|lazio|emilia|romagna|campania|puglia|calabria|"
    r"sicilia|sardegna|liguria|friuli|umbria|marche|molise|"
    r"basilicata|trentino|abruzzo|valle d.aosta|"
    r"roma|milano|torino|napoli|bari|genova|palermo|"
    r"firenze|bologna|venezia|province|comuni|"
    r"ue|europe[ao]|eurostat|istat|inps|ispra|"
    r"coldiretti|confcommercio|en[eia]|aci)\b", re.I
)
TOPIC_NAMES = {
    "ECONOMIA":"economia", "LAVORO":"lavoro",
    "DEMOGRAFIA":"popolazione", "AMBIENTE":"ambiente",
    "ENERGIA":"energia", "SALUTE":"salute",
    "ISTRUZIONE":"istruzione", "MOBILITA":"mobilità",
    "CASA":"abitazioni", "DIGITALE":"tecnologia",
    "ALTRO":"statistiche", "TERRITORI":"territori"
}

def item_datetime(item):
    try:
        date=parsedate_to_datetime(item.get("published_raw",""))
        if date.tzinfo is None: return None
        return date.astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError,IndexError):
        return None

def clean_title(text):
    title=re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",str(text or ""))).strip()
    return title.rsplit(" - ",1)[0].strip() if " - " in title else title

def source_from(item, feed):
    url=item.get("url","")
    domain=(urlsplit(url).hostname or "").lower().removeprefix("www.")
    title=item.get("title","")
    if domain.endswith("news.google.com"):
        if " - " in title: return title.rsplit(" - ",1)[1].strip()[:90]
        return str(feed.get("name","Google News"))
    return (domain or str(feed.get("name","Fonte stampa")))[:90]

def _normalised_headline(title):
    clean=clean_title(title).casefold()
    clean=re.sub(r"[^\wà-ù ]+"," ",clean)
    return " ".join(clean.split())[:190]

def eligible(item, now):
    date=item_datetime(item)
    if not date or not timedelta(0) <= now-date <= timedelta(days=3): return False
    title=clean_title(item.get("title",""))
    summary=item.get("summary","")
    if not (28<=len(title)<=260): return False
    if EXCLUDED.search(title):return False
    # Avoid global geopolitical/financial headlines merely containing a number.
    context=title+" "+str(summary)[:450]
    if not PUBLIC_INTEREST.search(context):return False
    if not NUMERIC_CLAIM.search(context) and not re.search(
            r"\b(?:statistiche|rapporto bes|indagine|rilevazione)\b",title,re.I):
        return False
    if not LOCAL_CONTEXT.search(context):return False
    return True

def media_brief(item,feed,now,topic,score,geos):
    if not eligible(item,now):return None
    title=clean_title(item.get("title",""))
    published=item_datetime(item)
    source_url=item.get("url","")
    if urlsplit(source_url).scheme not in ("https","http"):return None
    source=source_from(item,feed)
    base=_normalised_headline(title)
    if len(base)<18:return None
    fp=hashlib.sha256(("MEDIA|"+base).encode("utf-8")).hexdigest()
    pid="PULSE-MEDIA-"+fp[:16].upper()
    numbers=list(dict.fromkeys(m.group(0).strip() for m in NUMERIC_CLAIM.finditer(title)))
    if not numbers:
        numbers=list(dict.fromkeys(m.group(0).strip()
                                  for m in NUMERIC_CLAIM.finditer(item.get("summary",""))))[:4]
    metric=", ".join(numbers[:4]) or "i dati citati"
    subject=TOPIC_NAMES.get(topic,"statistiche")
    statement=(f"La testata {source} segnala una notizia su {subject}. "
               f"Nel titolo o nell'estratto sono riportati {metric}. "
               "Questi valori sono attribuiti alla testata: la corrispondenza "
               "con la pubblicazione statistica originale non è ancora stata verificata da PULSE.")
    context=(f"Il radar PULSE ha rilevato questa pubblicazione attraverso il canale "
             f"«{feed.get('name','Rassegna stampa')}». "
             "Il testo del giornale non viene riprodotto: per approfondire "
             "e conoscere definizioni, territorio e periodo esatti consulta la fonte collegata.")
    methodology=("Per produrre un grafico PULSE servono una fonte primaria "
                 "accessibile, l'indicatore, l'unità di misura e i periodi "
                 "di riferimento. Finché questi elementi non sono verificati "
                 "non viene disegnato alcun grafico né simulata una variazione.")
    return {
        "id":pid,"story_fingerprint":fp,
        "published_at":published.isoformat(),"last_seen_at":now.isoformat(),
        "headline":title,"reported_headline":item.get("title",""),
        "summary":statement,"pulse_title":title,"pulse_summary":statement,
        "pulse_article_body":[
            {"heading":"La notizia segnalata","text":statement},
            {"heading":"Fonte e contesto","text":context},
            {"heading":"Verifica statistica PULSE","text":methodology}
        ],
        "topic":topic,"pulse_score":min(75,int(score)),
        "public_source":{
            "url":source_url,"domain":source,"role":"journalistic_source",
            "verification_method":"rss_dated_media_report_not_primary_statistical_verification",
            "verification_score":0
        },
        "byline":"PULSE Radar · rassegna stampa",
        "statistical_claims":[{"raw_value":n,"verified":False}
                              for n in numbers[:4]],
        "territories":geos,"patterns":[],
        "origin_kind":"pulse_media_radar",
        "publication_tier":"reported_by_media_pending_primary_verification",
        "editorial_status":"journalistic_sourced",
        "publication_status":"published",
        "chart_spec":{"type":"none","status":"requires_primary_source"},
        "table_spec":{"status":"requires_primary_source","columns":[],"rows":[]},
        "discovery":{"role":"journalistic_radar","outlet":source,
                     "original_url":source_url,
                     "evidence_gate":"journalistic_rss_report_not_verified"}
    }
