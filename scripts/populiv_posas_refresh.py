#!/usr/bin/env python3
"""POPULIV: ISTAT POSAS annual official ZIP -> validated regional/national pack."""
import csv,gzip,hashlib,io,json,re,urllib.request,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

REGIONS=dict(zip([f"{i:02d}" for i in range(1,21)],[
"Piemonte","Valle d'Aosta","Lombardia","Trentino-Alto Adige","Veneto",
"Friuli-Venezia Giulia","Liguria","Emilia-Romagna","Toscana","Umbria",
"Marche","Lazio","Abruzzo","Molise","Campania","Puglia",
"Basilicata","Calabria","Sicilia","Sardegna"]))
SOURCE="https://demo.istat.it/data/posas/POSAS_{year}_it_Comuni.zip"
REGISTRY="https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv"
OUTPUT=Path("data/populiv")

def fetch(url,limit):
    if not (url.startswith("https://demo.istat.it/data/posas/") or url==REGISTRY):
        raise ValueError("Sorgente non autorizzata")
    request=urllib.request.Request(url,headers={"User-Agent":
        "Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(request,timeout=60) as reply:
        if not (reply.geturl().startswith("https://demo.istat.it/data/posas/") or
                reply.geturl()==REGISTRY):
            raise ValueError("Redirect non ISTAT")
        body=reply.read(limit+1)
    if len(body)>limit:raise ValueError("Risposta eccessiva")
    return body

def field(cols,name):
    for c in cols:
        if re.sub(r"\s+"," ",c.strip().lower())==name.lower():return c
    raise ValueError("Schema cambiato, colonna mancante: "+name)

def count(text):
    x=str(text).strip().replace(".","")
    if not re.fullmatch(r"\d+",x):raise ValueError("Conteggio non intero")
    return int(x)

def from_istat(year, zipped, registry, url):
    rows=csv.DictReader(io.StringIO(registry.decode("cp1252")),delimiter=";")
    code=field(rows.fieldnames or [],"Codice Comune formato alfanumerico")
    region=field(rows.fieldnames or [],"Codice Regione")
    codes={str(r[code]).strip().zfill(6):str(r[region]).strip().zfill(2) for r in rows}
    if len(codes)<7000:raise ValueError("Anagrafica comuni insufficiente")
    with zipfile.ZipFile(io.BytesIO(zipped)) as z:
        members=[n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(members)!=1:raise ValueError("Numero CSV ISTAT imprevisto")
        if z.getinfo(members[0]).file_size>400_000_000:raise ValueError("CSV enorme")
        original=z.read(members[0]).decode("utf-8-sig")
    stream=io.StringIO(original)
    stream.readline() # first line: source description
    csvrows=csv.DictReader(stream,delimiter=";")
    headers=csvrows.fieldnames or []
    print("POPULIV POSAS: intestazioni ufficiali", repr(headers[:30]), flush=True)
    idcol=field(headers,"Codice comune")
    agecol=field(headers,"Età")
    # The official 2026 export names these columns “Totale maschi/femmine”.
    mcol=field(headers,"Totale maschi" if "Totale maschi" in headers else "Maschi")
    fcol=field(headers,"Totale femmine" if "Totale femmine" in headers else "Femmine")
    by_region=defaultdict(lambda:[0,0])
    seen=defaultdict(set)
    city_total={}
    city_by_age=defaultdict(lambda:[0,0])
    for r in csvrows:
        ident=str(r[idcol]).strip().zfill(6)
        reg=codes.get(ident)
        if reg not in REGIONS:raise ValueError("Comune non presente in anagrafica "+ident)
        age=str(r[agecol]).strip()
        m,f=count(r[mcol]),count(r[fcol])
        if age=="999":
            city_total[ident]=(m,f)
            continue
        if not age.isdigit() or int(age)>100:continue
        a=int(age)
        if a in seen[ident]:raise ValueError("Fascia età duplicata")
        seen[ident].add(a)
        by_region[reg,a][0]+=m
        by_region[reg,a][1]+=f
        city_by_age[ident][0]+=m
        city_by_age[ident][1]+=f
    if not 7000<len(seen)<9000:raise ValueError("Comuni insufficienti")
    for city,ages in seen.items():
        if len(ages)!=101 or tuple(city_by_age[city])!=city_total.get(city):
            raise ValueError("Distribuzione comunale incompleta: "+city)
    if len(by_region)!=2020:raise ValueError("Regioni mancanti")
    italy=defaultdict(lambda:[0,0])
    observed=[]
    for (reg,age),(m,f) in sorted(by_region.items()):
        italy[age][0]+=m
        italy[age][1]+=f
        observed.extend([[year,"REGIONE",reg,REGIONS[reg],age,s,n] for s,n in (("M",m),("F",f))])
    for age,(m,f) in sorted(italy.items()):
        observed.extend([[year,"ITALIA","00","Italia",age,s,n] for s,n in (("M",m),("F",f))])
    population=sum(sum(pair) for pair in italy.values())
    if len(observed)!=4242 or not 55_000_000<population<62_000_000:
        raise ValueError("Popolazione o osservazioni non plausibili")
    return {"schema":1,"family":"istat_posas_age_sex","source":"ISTAT Demo POSAS",
        "source_url":url,"reference_year":year,"period":f"1 gennaio {year}",
        "unit":"residenti","denominator_definition":"residenti dello stesso territorio e periodo",
        "national_total":population,"municipalities_checked":len(seen),
        "observations":observed}

def publish(payload):
    year=payload["reference_year"]
    name=f"posas_age_sex_{year}.json.gz"
    archive=gzip.compress(json.dumps(payload,sort_keys=True,
        ensure_ascii=False,separators=(",",":")).encode(),compresslevel=9,mtime=0)
    checksum=hashlib.sha256(archive).hexdigest()
    manifest=OUTPUT/"manifest.json"
    if manifest.exists():
        old=json.loads(manifest.read_text())
        if old.get("reference_year",0)>year:raise ValueError("Anno più vecchio rifiutato")
        if old.get("sha256")==checksum:return False
        if old.get("reference_year")==year and old.get("national_total"):
            diff=abs(payload["national_total"]-old["national_total"])/old["national_total"]
            if diff>.05:raise ValueError("Revisione anomala superiore a 5%")
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/name).write_bytes(archive)
    data={"schema":1,"family":payload["family"],"reference_year":year,
       "period":payload["period"],"source_url":payload["source_url"],
       "source":payload["source"],"unit":payload["unit"],
       "denominator_definition":payload["denominator_definition"],
       "national_total":payload["national_total"],"observations":4242,
       "filename":name,"sha256":checksum,
       "generated_at":datetime.now(timezone.utc).isoformat()}
    manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    return True

def main():
    now=datetime.now(timezone.utc).year
    choice=None
    for year in range(now,max(2025,now-3)-1,-1):
        url=SOURCE.format(year=year)
        try:
            archive=fetch(url,160_000_000)
            if zipfile.is_zipfile(io.BytesIO(archive)):
                choice=(year,archive,url)
                break
        except (OSError,ValueError) as exc:
            print(f"ISTAT POSAS {year} non raggiungibile: {exc}",flush=True)
    if choice is None:raise ValueError("Nessun archivio POSAS ufficiale disponibile")
    year,archive,url=choice
    payload=from_istat(year,archive,fetch(REGISTRY,20_000_000),url)
    print(json.dumps({"updated":publish(payload),"year":year,
        "observations":len(payload["observations"]),"national_total":payload["national_total"]}),flush=True)

if __name__=="__main__":main()
