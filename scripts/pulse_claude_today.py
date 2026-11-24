#!/usr/bin/env python3
"""One-time Claude 5.5 summaries for TODAY PULSE items, through one budgeted gateway.

Never calls Anthropic directly, stores no AI key, never fabricates article content
from a title, skips inaccessible sources and Google News transport pages.
Requires PULSE_CLAUDE_ENABLED=true, VALE_CLAUDE_GATEWAY_URL and PULSE_JOB_TOKEN.
"""
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests

MAX_NEW=20

def text_from_original(url):
    parsed=urlparse(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.hostname in ("news.google.com","google.com","www.google.com"):
        return None
    try:
        from trafilatura import extract
        response=requests.get(url,timeout=12,allow_redirects=True,
                              headers={"User-Agent":"PULSE-VerifiedSourceReader/2.20"})
        response.raise_for_status()
        final=urlparse(response.url)
        if final.scheme!="https" or final.hostname in ("news.google.com","google.com","www.google.com"):
            return None
        if "html" not in response.headers.get("content-type","").lower() or len(response.content)>1_500_000:
            return None
        text=extract(response.text,include_comments=False,include_tables=False,include_links=False)
        if not text or len(text)<650 or re.search(r"enable javascript|javascript disabled",text[:400],re.I):
            return None
        return text[:7300]
    except (requests.RequestException, ValueError):
        return None

def publish(articles_file,index_file,endpoint,token):
    data=json.loads(Path(articles_file).read_text(encoding="utf-8"))
    index=json.loads(Path(index_file).read_text(encoding="utf-8"))
    by_id={a["id"]:a for a in data.get("articles",[])}
    today=index.get("oggi",[])
    if not isinstance(today,list):raise ValueError("invalid_news_index")
    report={"today":len(today),"created":0,"already_present":0,"unavailable_source":0,
            "rejected":0,"budget_exhausted":False}
    for article_id in today:
        if report["created"]>=MAX_NEW:break
        item=by_id.get(article_id)
        if not item:continue
        if item.get("ai_article",{}).get("status")=="published":
            report["already_present"]+=1;continue
        source=item.get("public_source") or {}
        url=source.get("url","")
        headline=item.get("headline","")
        if len(headline)<25:continue
        original=text_from_original(url)
        if not original:
            report["unavailable_source"]+=1;continue
        try:
            response=requests.post(endpoint.rstrip("/")+"/pulse/draft",json={
                "source_url":url,"headline":headline,"source_text":original},
                headers={"Authorization":"Bearer "+token},timeout=60)
        except requests.RequestException:
            report["rejected"]+=1
            break  # ambiguous timeout MAY be billable; never retry automatically
        if response.status_code in (402,429):
            report["budget_exhausted"]=True;break
        if response.status_code!=200:
            report["rejected"]+=1;continue
        payload=response.json()
        text=str(payload.get("text") or "").strip()
        if not 180<=len(text)<=7000 or payload.get("model")!="claude-sonnet-5-5":
            report["rejected"]+=1;continue
        if payload.get("source_url")!=url or payload.get("source_headline")!=headline:
            report["rejected"]+=1;continue
        item["ai_article"]={"status":"published","model":"claude-sonnet-5-5",
            "source_url":url,"source_headline":headline,"text":text,
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "method":"AI_summary_from_readable_source_not_independent_fact_check"}
        report["created"]+=1
    if report["created"]:
        path=Path(articles_file)
        temp=path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        temp.replace(path)
    return report

def main():
    if os.getenv("PULSE_CLAUDE_ENABLED")!="true":
        print("PULSE Sonnet disattivato: nessuna chiamata pagata.")
        return 0
    endpoint=os.getenv("VALE_CLAUDE_GATEWAY_URL","")
    token=os.getenv("PULSE_JOB_TOKEN","")
    if not endpoint.startswith("https://") or not token:
        print("Gateway o chiave job assenti: nessuna chiamata inviata.",file=sys.stderr)
        return 2
    report=publish(Path("data/news/articles.json"),Path("data/news/index.json"),endpoint,token)
    print(json.dumps(report,ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
