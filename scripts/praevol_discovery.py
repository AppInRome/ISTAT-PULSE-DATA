"""Read-only diagnostic for official ISTAT forecast download links."""
import re,requests,urllib.parse,json
from bs4 import BeautifulSoup
URL="https://demo.istat.it/app/?i=PPR"
session=requests.Session();session.headers.update({"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36"})
page=session.get(URL,timeout=40);print("SITE",page.status_code,len(page.content),page.url)
page.raise_for_status()
soup=BeautifulSoup(page.text,"html.parser")
print("TITLE",soup.title.get_text(" ",strip=True) if soup.title else "none")
links=set()
for tag in soup.find_all(["a","script"],src=True)+soup.find_all("a",href=True):
 url=tag.get("src") or tag.get("href")
 url=urllib.parse.urljoin(URL,url)
 if any(x in url.lower() for x in ("ppr","app","zip","download","js","forecast")):links.add(url)
print("LINKS",json.dumps(sorted(links)[:100],ensure_ascii=False))
for match in re.findall(r".{0,120}(?:\.zip|PPR|previsioni|download).{0,180}",page.text,re.I)[:25]:
 print("MATCH",match[:380])
for url in sorted(links):
 if url.endswith(".js") and ("app" in url or "main" in url or "ppr" in url):
  try:
   r=session.get(url,timeout=30)
   print("JS",url,r.status_code,len(r.content))
   for match in re.findall(r".{0,140}(?:PPR|\\.zip|download|previsioni).{0,230}",r.text,re.I)[:20]:print("JS-MATCH",match[:400])
  except Exception as e:print("JS-ERR",type(e).__name__,str(e)[:100])


import zipfile,io
for group in ("Previsioni-Popolazione_per_eta-Regioni.zip","Previsioni-Popolazione_per_eta-Ripartizioni.zip"):
 url="https://demo.istat.it/data/previsioni/"+group
 try:
  resp=session.get(url,timeout=90)
  print("ZIP",group,resp.status_code,len(resp.content))
  with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
   print("MEMBERS",[(n.filename,n.file_size) for n in z.infolist()[:30]])
   for entry in z.infolist()[:3]:
    if entry.file_size>10_000_000:continue
    content=z.read(entry.filename)
    sample=content[:1600].decode("utf-8-sig","replace")
    print("SAMPLE",entry.filename,repr(sample[:1500]))
 except Exception as e:print("ZIP-ERR",type(e).__name__,str(e)[:250])
