#!/usr/bin/env python3
"""Original PULSE articles. Only independently traceable statistical comparisons."""
from __future__ import annotations
import re
import math
from urllib.parse import urlsplit

STOP={"italia","italiani","italiano","italiana","anno","anni","dati","dato",
      "statistiche","rapporto","indice","valore","valori","numero","numeri",
      "totale","percentuale","della","delle","degli","nella","nelle",
      "secondo","risultati","studio","rilevazione","dalle","fonte","statistica"}
TOPICS={"ECONOMIA":"economia","LAVORO":"lavoro","SALUTE":"salute",
        "ISTRUZIONE":"istruzione","AMBIENTE":"ambiente","ENERGIA":"energia",
        "MOBILITA":"mobilità","CASA":"casa","DEMOGRAFIA":"demografia",
        "DIGITALE":"digitale","GIUSTIZIA":"giustizia","ALTRO":"società"}

def words(s):
    return {w for w in re.findall(r"[a-zà-ù]{4,}",str(s or "").casefold()) if w not in STOP}

def fmt(n):
    t=f"{float(n):,.2f}".rstrip("0").rstrip(".")
    return t.replace(",","_").replace(".",",").replace("_",".")

def series_for_story(raw, title, primary_url):
    """Require same-source primary evidence and one comparable, relevant indicator."""
    if not isinstance(raw,list):return []
    title_words=words(title)
    origin=(urlsplit(primary_url).hostname or "").lower()
    accepted=[]
    for record in raw:
        if not isinstance(record,dict) or record.get("verified") is not True:continue
        indicator=str(record.get("indicator") or "").strip()
        unit=str(record.get("unit") or "").strip()
        if not indicator or not unit or not (words(indicator)&title_words):continue
        doc=str(record.get("source_url") or primary_url)
        host=(urlsplit(doc).hostname or "").lower()
        if urlsplit(doc).scheme!="https" or not host or not origin:continue
        if not (origin==host or origin.endswith("."+host) or host.endswith("."+origin)):continue
        obs=record.get("observations")
        if not isinstance(obs,list) or len(obs)<1:continue
        points=[]
        for row in obs[:30]:
            try:
                period=str(row["period"]).strip()
                value=float(row["value"])
                if not re.fullmatch(r"(?:19|20)\d{2}(?:-(?:Q[1-4]|\d{2}))?",period):raise ValueError
                if not math.isfinite(value):raise ValueError
                points.append({"period":period,"value":value})
            except (KeyError,TypeError,ValueError):
                points=[];break
        points.sort(key=lambda x:x["period"])
        if len(points)<1 or len({x["period"] for x in points})!=len(points):continue
        accepted.append({"indicator":indicator[:140],"unit":unit[:40],
                         "observations":points[-12:],"source_url":doc,
                         "method":record.get("extraction_method",""),
                         "relevance":len(words(indicator)&title_words)})
    return sorted(accepted,key=lambda x:(x["relevance"],len(x["observations"]),
                                         x["observations"][-1]["period"]),reverse=True)[:2]

def compose_verified(article,resolved):
    """Produce an independent original summary; NEVER reproduce newspaper prose."""
    result=dict(article)
    src=result.get("public_source") or {}
    primary=str(src.get("url") or "")
    if src.get("role")!="primary_statistical_source" or not primary.startswith("https://"):
        return result
    original=result.get("headline","")
    domain=(urlsplit(primary).hostname or "").removeprefix("www.")
    topic=TOPICS.get(result.get("topic"),"società")
    discovered=(result.get("discovery") or {}).get("original_url") or ""
    result["original_discovery_headline"]=original
    result["byline"]="Redazione PULSE"
    result["editorial_method"]="testo originale da evidenza statistica, non copia della testata"
    result["sources"]=[{"role":"statistical_primary","url":primary,"name":domain}]
    if discovered and discovered!=primary:
        result["sources"].append({"role":"discovery","url":discovered,
                                  "name":(result.get("discovery") or {}).get("outlet","Segnalazione stampa")})
    evidence=series_for_story((resolved or {}).get("verified_series",[]),original,primary)
    result["verified_series_relevant"]=evidence
    if evidence:
        serie=evidence[0]
        indicator=serie["indicator"]
        unit=serie["unit"]
        p=serie["observations"]
        latest=p[-1]
        if len(p)>1:
            before=p[-2]
            delta=latest["value"]-before["value"]
            action="in aumento" if delta>0 else "in diminuzione" if delta<0 else "invariato"
            result["headline"]=f"{indicator[:1].upper()+indicator[1:]}: dato {action} nel {latest['period']}"
            result["summary"]=(f"Secondo i dati originali di {domain}, {indicator.lower()} "
                               f"passa da {fmt(before['value'])} {unit} ({before['period']}) "
                               f"a {fmt(latest['value'])} {unit} ({latest['period']}).")
            change=(f"{fmt(delta)} punti percentuali" if unit=="%" else f"{fmt(delta)} {unit}")
            context=(f"Il confronto tra i due ultimi periodi disponibili mostra "
                     f"una variazione di {change}. Non attribuiamo cause che la fonte "
                     "non documenta.")
            if abs(before["value"])>1e-9:
                rel=delta/abs(before["value"])*100
                context+=(f" La variazione relativa rispetto al periodo precedente "
                          f"è di {fmt(rel)}%.")
            if len(p)>2:
                lowest=min(p,key=lambda x:x["value"])
                highest=max(p,key=lambda x:x["value"])
                context+=(f" Tra i {len(p)} periodi effettivamente disponibili "
                          f"il minimo è {fmt(lowest['value'])} {unit} ({lowest['period']}) "
                          f"e il massimo è {fmt(highest['value'])} {unit} ({highest['period']}).")
            result["verification_tier"]="verified_comparable_series"
        else:
            result["headline"]=(f"{indicator[:1].upper()+indicator[1:]}: "
                                f"{fmt(latest['value'])} {unit} nel {latest['period']}")
            result["summary"]=(f"Il documento statistico originale pubblicato da {domain} "
                               f"riporta {fmt(latest['value'])} {unit} per "
                               f"{indicator.lower()} nel {latest['period']}.")
            context=("La tabella ufficiale disponibile contiene un solo periodo verificabile. "
                     "Il grafico rappresenta un valore singolo: non è una crescita "
                     "né una diminuzione e non consente di calcolare una tendenza.")
            result["verification_tier"]="verified_single_observation"
        result["pulse_article_body"]=[
          {"heading":"I numeri verificati","text":result["summary"]},
          {"heading":"Come leggere il dato","text":context},
          {"heading":"Fonte e metodo","text":
           f"I dati provengono da un prospetto strutturato di {domain}. "
           "Fonte, indicatore, unità e periodo sono riportati nella tabella. "
           "La data del fenomeno statistico non coincide necessariamente "
           "con quella di pubblicazione."}
        ]
        result["chart_spec"]={
            "type":"line" if len(p)>2 else "bar",
            "status":"verified",
            "title":indicator,
            "unit":unit,
            "source_url":serie["source_url"],
            "single_observation":len(p)==1,
            "data":[{"period":x["period"],"value":x["value"]} for x in p]
        }
        result["table_spec"]={
            "status":"verified",
            "columns":["Periodo",indicator,"Unità"],
            "rows":[[x["period"],fmt(x["value"]),unit] for x in p],
            "source_url":serie["source_url"]
        }
        result["editorial_status"]="verified_primary_match"
    else:
        # A figure merely occurring on a long web page is NOT proof that we
        # know its unit, period, or indicator. No fabricated graphics.
        result["headline"]=f"Dati di {topic}: nuova pubblicazione della fonte {domain}"
        result["summary"]=(f"PULSE ha individuato un aggiornamento sul tema {topic} "
                           f"e localizzato un documento di {domain}. "
                           "Non è ancora disponibile una serie omogenea verificata "
                           "da cui derivare confronti numerici.")
        result["pulse_article_body"]=[
          {"heading":"La pubblicazione","text":result["summary"]},
          {"heading":"Fonte e verifiche","text":
           "La notizia è stata individuata attraverso la stampa. "
           "Il documento originale è disponibile tra le fonti; "
           "PULSE non trasforma singole cifre prive di contesto in statistiche confrontabili."}
        ]
        result["chart_spec"]={"type":"none","status":"no_verified_comparable_series"}
        result["table_spec"]={"status":"no_verified_comparable_series","columns":[],"rows":[]}
        result["verification_tier"]="primary_page_identified_series_pending"
        # A page with coincidental matching digits is not sufficient for an
        # original statistical article. Keep it as a research draft, never OGGI.
        result["publication_status"]="quarantined"
        result["editorial_status"]="needs_verified_comparable_series"
    result["pulse_title"]=result["headline"]
    result["pulse_summary"]=result["summary"]
    return result
