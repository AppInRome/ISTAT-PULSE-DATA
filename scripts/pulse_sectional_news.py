#!/usr/bin/env python3
"""Separate editorial OGGI/IERI for GREEN and TERRITORI.

These are *news* classifications, never fabricated API observations.
Each referenced ID exists in data/news/articles.json; source dates are retained.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

SUBNATIONAL = (
    "abruzzo", "basilicata", "calabria", "campania", "emilia-romagna",
    "friuli-venezia giulia", "lazio", "liguria", "lombardia",
    "marche", "molise", "piemonte", "puglia", "sardegna",
    "sicilia", "toscana", "trentino-alto adige", "umbria",
    "valle d'aosta", "veneto", "roma", "milano", "napoli",
    "torino", "bologna", "firenze", "genova", "palermo", "bari",
    "venezia", "brescia", "bergamo", "lecce", "catania", "cagliari",
    "perugia", "foggia", "andria", "verona", "trieste", "ancona",
    "potenza", "matera", "trento", "bolzano", "regione", "province",
    "provincia", "comuni", "comune", "capoluoghi", "capoluogo",
)
GREEN_TERMS = (
    "ambient", "rifiut", "ricicl", "suolo", "cemento", "verde",
    "clima", "co2", "gas serra", "emissioni", "rinnovabil", "energi",
    "biodivers", "acqua", "idric", "inquin", "mobilità sostenibile",
    "autovetture elettriche", "auto elettriche", "fotovolta",
    "terranatur", "sostenibil", "foreste", "imballaggi", "siccità",
    "efficienza energetica"
)
GREEN_TOPICS = frozenset(("AMBIENTE","ENERGIA"))
NORMALIZE_REGIONS = {"italia","europe","europa","ue","unione europea","ue27","nazionale"}

def _word_match(text: str, term: str) -> bool:
    # Match word boundaries, without accidental cases such as "romano" = "roma".
    return re.search(r"(?<!\w)"+re.escape(term)+r"(?!\w)", text, re.I) is not None

def belongs_green(article: dict) -> bool:
    topic=str(article.get("topic","")).upper()
    title=str(article.get("headline","")).casefold()
    if topic in GREEN_TOPICS: return True
    # MOBILITA is not always environmental; gas or electric transport is.
    if topic=="MOBILITA":
        return any(term in title for term in GREEN_TERMS)
    return any(term in title for term in GREEN_TERMS if len(term)>5)

def belongs_territori(article: dict) -> bool:
    territories=article.get("territories") or []
    if isinstance(territories,str): territories=[territories]
    if any(str(p).strip().casefold() not in NORMALIZE_REGIONS
           for p in territories if str(p).strip()):
        return True
    title=str(article.get("headline","")).casefold()
    return any(_word_match(title,name) for name in SUBNATIONAL)

def make_indices(articles: list, index: dict, generated_at: str) -> dict:
    lookup={x["id"]:x for x in articles if isinstance(x,dict) and x.get("id")}
    outputs={}
    for section,predicate in (("green",belongs_green),("territori",belongs_territori)):
        grouped={"oggi":[],"ieri":[],"archivio":[]}
        for bucket in grouped:
            for aid in index.get(bucket,[]):
                article=lookup.get(aid)
                if not article or article.get("publication_status")!="published":
                    continue
                if predicate(article):
                    grouped[bucket].append(aid)
        ids=[x for values in grouped.values() for x in values]
        if len(ids)!=len(set(ids)): raise ValueError("Duplicated sectional article")
        verified=sum((lookup[aid].get("public_source") or {}).get("role")=="primary_statistical_source"
                     for aid in ids)
        unverified=sum(lookup[aid].get("publication_tier")==
                     "reported_by_media_pending_primary_verification" for aid in ids)
        outputs[section]={
            "generated_at":generated_at,
            "type":"editorial_news_index_not_api_observations",
            "articles_file":"data/news/articles.json",
            "statistics_file":"data/pulse_events.tsv" if section=="green" else "data/pulse_observations.tsv",
            "data_status_file":"data/pulse_green_status.json" if section=="green"
                              else "data/pulse_observations_manifest.json",
            "source_publication_dates_preserved":True,
            "counts":{"oggi":len(grouped["oggi"]),"ieri":len(grouped["ieri"]),
                      "archivio":len(grouped["archivio"]),
                      "officially_verified_stories":verified,
                      "press_reports_pending_primary_verification":unverified},
            **grouped
        }
    return outputs

def save_indices(articles: list, index: dict, output_folder: Path):
    generated=str(index.get("generated_at") or "")
    if not generated: raise ValueError("Index lacks generated_at")
    result=make_indices(articles,index,generated)
    output_folder.mkdir(parents=True,exist_ok=True)
    for section,payload in result.items():
        target=output_folder/(section+"_index.json")
        stage=target.with_suffix(".staging")
        stage.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        stage.replace(target)
    return result
