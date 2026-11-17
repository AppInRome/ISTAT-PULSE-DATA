#!/usr/bin/env python3
"""PROXIMA: source-checked school and regional population remote snapshots. Standard library."""
import csv,gzip,hashlib,io,json,re,urllib.parse,urllib.request
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

OUTPUT=Path("data/proxima")
POPULIV=Path("data/populiv")
SOURCES=("SCUANAGRAFESTAT","SCUANAGRAFEPAR","SCUANAAUTSTAT","SCUANAAUTPAR")
REGIONS=("Piemonte","Valle d'Aosta","Lombardia","Trentino-Alto Adige","Veneto","Friuli-Venezia Giulia","Liguria","Emilia-Romagna","Toscana","Umbria","Marche","Lazio","Abruzzo","Molise","Campania","Puglia","Basilicata","Calabria","Sicilia","Sardegna")

def fetch(url, limit=25000000):
    p=urllib.parse.urlsplit(url)
    if p.scheme!="https" or p.hostname!="dati.istruzione.it" or not p.path.startswith("/opendata/"):
        raise ValueError("Official MIM HTTPS origin required")
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req,timeout=65) as response:
        final=urllib.parse.urlsplit(response.geturl())
        if final.scheme!="https" or final.hostname!="dati.istruzione.it":
            raise ValueError("Unexpected redirect")
        b=response.read(limit+1)
    if len(b)>limit:raise ValueError("MIM source size over cap")
    return b

def latest_mim():
    result={}
    for ds in SOURCES:
        catalog=f"https://dati.istruzione.it/opendata/opendata/catalog/{ds}"
        html=fetch(catalog,3000000).decode("utf-8","replace")
        stamps=sorted(set(re.findall(rf"{ds}(20\d{{4}}20\d{{6}})\.csv",html)),reverse=True)
        stamps=[s for s in stamps if 2020<=int(s[:4])<=datetime.now(timezone.utc).year]
        if not stamps:raise ValueError("Official MIM catalog missing CSV: "+ds)
        result[ds]=f"https://dati.istruzione.it/opendata/opendata/catalog/{ds}/{ds}{stamps[0]}.csv"
    return result

def school_rows(body, source):
    raw=None
    for codec in ("utf-8-sig","cp1252"):
        try:raw=body.decode(codec);break
        except UnicodeDecodeError:pass
    if not raw or len(raw)<5000:raise ValueError("Unrecognized school CSV")
    first=raw.splitlines()[0]
    sep="\t" if first.count("\t")>first.count(";") else ";" if first.count(";")>=first.count(",") else ","
    rdr=csv.DictReader(io.StringIO(raw),delimiter=sep)
    norm={re.sub("[^A-Z0-9]","",x.upper()):x for x in (rdr.fieldnames or [])}
    print("PROXIMA MIM",source,"headers",repr((rdr.fieldnames or [])[:20]),"preview",repr(raw[:180]),flush=True)
    def col(*candidates):
        for x in candidates:
            k=norm.get(re.sub("[^A-Z0-9]","",x.upper()))
            if k:return k
        raise ValueError("MIM column missing: "+candidates[0])
    code=col("CodiceScuola");name=col("DenominazioneScuola")
    street=col("IndirizzoScuola");city=col("DescrizioneComune","ComuneScuola","Comune")
    post=col("CAPScuola","CAP")
    out=[]
    for r in rdr:
        ident=(r.get(code) or "").strip().upper()
        title=(r.get(name) or "").strip()
        town=(r.get(city) or "").strip()
        if not re.fullmatch("[A-Z0-9]{8,12}",ident) or len(title)<3 or not town:continue
        out.append([ident,title[:250],(r.get(street) or "").strip()[:200],town[:100],
                    (r.get(post) or "").strip()[:12],source])
    if len(out)<(10000 if source=="SCUANAGRAFESTAT" else 100):
        raise ValueError("MIM subset too small "+source+": "+str(len(out)))
    return out

def school_document():
    sources=latest_mim()
    schools={}
    for src,url in sources.items():
        for entry in school_rows(fetch(url),src):
            if entry[0] in schools and schools[entry[0]]!=entry:
                raise ValueError("Duplicate code across MIM sets")
            schools[entry[0]]=entry
    if not 45000<=len(schools)<=90000:raise ValueError("National MIM registry count implausible")
    year=int(sources["SCUANAGRAFESTAT"].split("/")[-1].replace("SCUANAGRAFESTAT","")[:4])
    return {"schema":1,"family":"schools","reference_year":year,"source":"Ministero Istruzione e Merito, anagrafiche sedi scolastiche",
            "source_urls":sources,"completeness":"MIM statali/paritarie/autonome, coordinates independent",
            "coordinate_policy":"retain_only_when_original_location_matches",
            "records":list(sorted(schools.values()))}

def territorial_document():
    manifest=json.loads((POPULIV/"manifest.json").read_text())
    blob=(POPULIV/manifest["filename"]).read_bytes()
    if hashlib.sha256(blob).hexdigest()!=manifest["sha256"]:raise ValueError("POSAS source SHA mismatch")
    posas=json.loads(gzip.decompress(blob))
    if posas["family"]!="istat_posas_age_sex" or len(posas["observations"])!=4242:
        raise ValueError("POSAS structure mismatch")
    national=0;regs=defaultdict(int)
    for y,level,code,label,age,sex,n in posas["observations"]:
        if level=="ITALIA":national+=n
        elif level=="REGIONE":regs[code]+=n
        else:raise ValueError("Unknown POSAS level")
    if len(regs)!=20 or sum(regs.values())!=national or national!=posas["national_total"]:
        raise ValueError("POSAS 20 region totals do not reconcile")
    return {"schema":1,"family":"territorial_population","reference_year":posas["reference_year"],
            "source":"ISTAT POSAS","source_url":posas["source_url"],"period":posas["period"],
            "unit":"residenti","not_census_grid":True,"national_total":national,
            "records":[["00","Italia",national]]+[[f"{i:02d}",REGIONS[i-1],regs[f"{i:02d}"]] for i in range(1,21)]}

def add_family(state,family,data):
    year=data["reference_year"]
    prior=state.get("families",{}).get(family,{})
    if prior.get("reference_year",0)>year:raise ValueError("Backdated pack rejected")
    raw=gzip.compress(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode(),compresslevel=9,mtime=0)
    sha=hashlib.sha256(raw).hexdigest()
    if prior.get("sha256")==sha:return False
    if len(raw)>20000000:raise ValueError("Family package >20MB")
    name=f"{family}_{year}_{sha[:10]}.json.gz"
    (OUTPUT/name).write_bytes(raw)
    state.setdefault("families",{})[family]={
      "status":"ready","schema":1,"family":family,"reference_year":year,
      "filename":name,"sha256":sha,"bytes":len(raw),"rows":len(data["records"]),
      "source":data["source"],"source_url":data.get("source_url",list(data.get("source_urls",{}).values())[0] if data.get("source_urls") else ""),
      "published_at":datetime.now(timezone.utc).isoformat()}
    return True

def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    dest=OUTPUT/"manifest.json"
    state=json.loads(dest.read_text()) if dest.exists() else {"schema":1,"families":{}}
    errors={}
    for name,fn in (("territorial_population",territorial_document),("schools",school_document)):
        try:add_family(state,name,fn())
        except Exception as exc:errors[name]=str(exc)[:300]
    state["geographies"]={
      "status":"catalog_only","official_reference_year":2026,
      "source":"ISTAT confini amministrativi",
      "source_url":"https://www.istat.it/notizia/confini-delle-unita-amministrative-a-fini-statistici-al-1-gennaio-2018-2/",
      "note":"Administrative boundaries cannot replace ISTAT BT2021 census-section polygons"}
    dest.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n")
    (OUTPUT/"refresh_status.json").write_text(json.dumps({
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "families_available":sorted(state["families"]),"errors":errors},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"available":sorted(state["families"]),"errors":errors},ensure_ascii=False))
    if not state["families"]:raise RuntimeError("No validated data family available")

if __name__=="__main__":main()
