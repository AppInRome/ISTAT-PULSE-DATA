#!/usr/bin/env python3
"""PRAEVOL: official ISTAT PPR median by sex/age, nationally and by region.

Never infer municipal projections from regional results. This publisher is
fail-closed: new snapshots are exposed only after all 21 geographies pass.
"""
from __future__ import annotations
import csv,gzip,hashlib,io,json,re,urllib.request,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit

HOME="https://demo.istat.it/app/?i=PPR"
REG="https://demo.istat.it/data/previsioni/Previsioni-Popolazione_per_eta-Regioni.zip"
ITA="https://demo.istat.it/data/previsioni/Previsioni-Popolazione_per_eta-Ripartizioni.zip"
OUT=Path("data/praevol")
REGIONS={
"Piemonte":"R:01","Valle_d_Aosta-Vallee_d_Aoste":"R:02","Lombardia":"R:03",
"Trentino-Alto_Adige":"R:04","Veneto":"R:05","Friuli-Venezia_Giulia":"R:06",
"Liguria":"R:07","Emilia-Romagna":"R:08","Toscana":"R:09","Umbria":"R:10",
"Marche":"R:11","Lazio":"R:12","Abruzzo":"R:13","Molise":"R:14",
"Campania":"R:15","Puglia":"R:16","Basilicata":"R:17","Calabria":"R:18",
"Sicilia":"R:19","Sardegna":"R:20"}
SOURCE_URLS={"regions":REG,"italy":ITA}

def fetch(url,limit):
    u=urlsplit(url)
    if u.scheme!="https" or u.hostname!="demo.istat.it" or not (
        u.path=="/app/" or u.path.startswith("/data/previsioni/")):
        raise ValueError("Origine non ufficiale")
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req,timeout=65) as response:
        final=urlsplit(response.geturl())
        if final.scheme!="https" or final.hostname!="demo.istat.it":
            raise ValueError("Redirect fuori dal dominio ISTAT")
        result=response.read(limit+1)
    if len(result)>limit:raise ValueError("Risorsa troppo grande")
    return result

def base_year(page):
    html=page.decode("utf-8","replace")
    match=re.search(r"Base\s*1\s*/\s*1\s*/\s*(20\d\d)",html,re.I)
    if not match:raise ValueError("Anno base ufficiale non trovato")
    year=int(match.group(1))
    if not 2025<=year<=2050:raise ValueError("Anno base non compatibile con PRAEVOL")
    links=(REG.rsplit("/",1)[-1],ITA.rsplit("/",1)[-1])
    if not all(x in html for x in links):raise ValueError("ZIP di previsione ufficiali non elencati")
    return year

def csv_records(contents,expected_base):
    text=contents.decode("utf-8-sig")
    records=csv.reader(io.StringIO(text),delimiter=";")
    banner=next(records,[])
    if not banner or "Previsioni regionali" not in banner[0]:
        raise ValueError("Intestazione di fonte non conforme")
    match=re.search(r"base\s*1\s*[./]\s*1\s*[./]\s*(20\d\d)",banner[0],re.I)
    if not match or int(match.group(1))!=expected_base:
        raise ValueError("ZIP riferito a una base ISTAT differente")
    next(records,[]) # region/ripartition label
    head=next(records,[])
    mandatory=("Anno","Sesso","Età","Scenario mediano")
    cols={item.strip():i for i,item in enumerate(head)}
    if not all(k in cols for k in mandatory):raise ValueError("Manca scenario mediano o una dimensione")
    data=defaultdict(lambda:[0,0])
    checks=defaultdict(set)
    for r in records:
        if len(r)<len(head):continue
        year_text=r[cols["Anno"]].strip()
        sex_text=r[cols["Sesso"]].strip()
        age_text=r[cols["Età"]].strip()
        if not year_text.isdecimal() or sex_text not in ("Maschi","Femmine"):
            continue # documented footnotes / total rows
        year=int(year_text)
        if not expected_base<=year<=2050:continue
        if age_text.isdecimal():age=int(age_text)
        elif re.match(r"^100\s*(?:e|anni|\+|ed|o)",age_text,re.I):age=100
        else:continue
        if not 0<=age<=100:raise ValueError("Età impossibile")
        gender=0 if sex_text=="Maschi" else 1
        key=(year,gender)
        if age in checks[key]:raise ValueError("Duplicazione età/sesso")
        checks[key].add(age)
        value=r[cols["Scenario mediano"]].strip().replace(".","")
        if not re.fullmatch(r"\d+",value):raise ValueError("Scenario mediano non intero")
        count=int(value)
        if count<0:raise ValueError("Valore demografico negativo")
        band=min(age//5,19)
        data[year,band][gender]+=count
    required=set(range(101))
    for year in range(expected_base,2051):
        for gender in (0,1):
            if checks.get((year,gender))!=required:
                raise ValueError("Età mancanti/non riconosciute nel CSV per "+str(year))
    if len(data)!=(2051-expected_base)*20:
        raise ValueError("Anni o classi quinquennali mancanti")
    return data

def extract(zipped,base,geographies):
    with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
        names=archive.namelist()
        if any(x.startswith("/") or ".." in x for x in names):
            raise ValueError("ZIP con percorso non valido")
        results={}
        for suffix,geo in geographies.items():
            matches=[name for name in names if name.endswith("_"+suffix+".csv")]
            if len(matches)!=1:raise ValueError("CSV regionale mancante o ambiguo: "+suffix)
            info=archive.getinfo(matches[0])
            if info.file_size>3_000_000:raise ValueError("CSV troppo grande: "+suffix)
            results[geo]=csv_records(archive.read(info),base)
        return results

def build(base,regions_zip,italy_zip):
    reg=extract(regions_zip,base,REGIONS)
    ita=extract(italy_zip,base,{"Italia":"I:ITA"})
    if len(reg)!=20 or len(ita)!=1:raise ValueError("Geografie ufficiali incomplete")
    records=[]
    delta_max=0
    for year in range(base,2051):
        italy_by_sex=[0,0]
        regional_by_sex=[0,0]
        for geo in ["I:ITA"]+[f"R:{i:02d}" for i in range(1,21)]:
            src=ita if geo=="I:ITA" else reg
            if geo not in src:raise ValueError("Codice geografico mancante")
            for band in range(20):
                male,female=src[geo][year,band]
                if not 0<=male<=2_000_000 or not 0<=female<=2_000_000:
                    raise ValueError("Conteggio demografico anomalo")
                records.append([geo,year,band,male,female])
                if geo=="I:ITA":
                    italy_by_sex[0]+=male;italy_by_sex[1]+=female
                else:
                    regional_by_sex[0]+=male;regional_by_sex[1]+=female
        for i in range(2):
            delta=abs(italy_by_sex[i]-regional_by_sex[i])/max(1,italy_by_sex[i])
            delta_max=max(delta_max,delta)
            # Median for each region is not mathematically additive to Italy median.
            if delta>.02:raise ValueError("Italia e Regioni divergono oltre 2%")
        if not 40_000_000<sum(italy_by_sex)<65_000_000:raise ValueError("Totale Italia non plausibile")
    return {"schema":1,"family":"istat_ppr_median","kind":"ISTAT","reference_base":f"{base}-01-01",
      "base_year":base,"last_year":2050,"scenario":"Scenario mediano",
      "source":"ISTAT Demo PPR","source_urls":SOURCE_URLS,
      "source_zip_sha256":{"regions":hashlib.sha256(regions_zip).hexdigest(),
                           "italy":hashlib.sha256(italy_zip).hexdigest()},
      "age_encoding":"0=0-4 ... 18=90-94 19=95+",
      "period_definition":"popolazione residente al 1 gennaio dell'anno",
      "sex":"male/female separate","geographies":21,
      "national_regional_median_difference_max":round(delta_max,7),
      "experimental_rebased":False,
      "experimental_note":"Le stime comunali PRAEVOL rimangono legate al loro modello originale; non sono aggiornate automaticamente da una nuova base regionale.",
      "observations":records}

def publish(payload):
    OUT.mkdir(exist_ok=True,parents=True)
    manifest=OUT/"manifest.json"
    base=payload["base_year"]
    if manifest.exists():
        old=json.loads(manifest.read_text())
        if base<old["base_year"]:raise ValueError("Downgrade previsione ISTAT rifiutato")
        if old.get("source_zip_sha256")==payload["source_zip_sha256"]:
            print("Nessuna nuova revisione ISTAT ufficiale")
            return False
    compressed=gzip.compress(json.dumps(payload,ensure_ascii=False,separators=(",",":"),sort_keys=True).encode(),compresslevel=9,mtime=0)
    sha=hashlib.sha256(compressed).hexdigest()
    name=f"ppr_median_{base}_{sha[:12]}.json.gz"
    (OUT/name).write_bytes(compressed)
    new={"schema":1,"family":"istat_ppr_median","status":"ready","base_year":base,
       "reference_base":payload["reference_base"],"last_year":2050,
       "scenario":"Scenario mediano","kind":"ISTAT","source":"ISTAT Demo PPR",
       "source_urls":SOURCE_URLS,"source_zip_sha256":payload["source_zip_sha256"],
       "filename":name,"sha256":sha,"bytes":len(compressed),
       "observations":len(payload["observations"]),"geographies":21,
       "experimental_rebased":False,
       "generated_at":datetime.now(timezone.utc).isoformat()}
    tmp=OUT/"manifest.staging.json"
    tmp.write_text(json.dumps(new,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(manifest)
    print(json.dumps({"published":True,"reference_base":payload["reference_base"],
         "observations":len(payload["observations"]),"sha256":sha},ensure_ascii=False))
    return True

def main():
    base=base_year(fetch(HOME,1_000_000))
    pack=build(base,fetch(REG,50_000_000),fetch(ITA,30_000_000))
    if len(pack["observations"])!=(2051-base)*420:
        raise ValueError("Numero di righe ufficiali incongruente")
    publish(pack)

if __name__=="__main__":
    main()
