#!/usr/bin/env python3
"""Bounded live reachability probe of the 27 curated PULSE source links.

This DOES NOT certify correctness of article-level links or statistical data.
A 403/429/timeout is inconclusive, not a confirmed broken URL.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime,timezone
import json
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urlsplit

UA="Mozilla/5.0 (compatible; PULSE-SourceLinkAudit/1.0; +https://github.com/AppInRome/ISTAT-PULSE-DATA)"

def probe(item):
    url=item["url"]
    if urlsplit(url).scheme!="https" or not urlsplit(url).hostname:
        return {"name":item["name"],"url":url,"status":"invalid_url"}
    reason=""
    for method in ("HEAD","GET"):
        try:
            headers={"User-Agent":UA,"Accept":"text/html,application/json,*/*"}
            if method=="GET":headers["Range"]="bytes=0-1024"
            request=urllib.request.Request(url,headers=headers,method=method)
            with urllib.request.urlopen(request,timeout=11) as response:
                status=response.status
                final=response.geturl()
                if status in (200,206):
                    return {"name":item["name"],"url":url,"status":"reachable",
                            "http":status,"final_url":final}
                reason="HTTP "+str(status)
        except urllib.error.HTTPError as e:
            reason="HTTP "+str(e.code)
            if e.code in (404,410):
                return {"name":item["name"],"url":url,"status":"broken",
                        "http":e.code}
            if e.code in (401,403,429,451):
                # HEAD is often disallowed; retry GET once.
                if method=="HEAD":continue
                return {"name":item["name"],"url":url,"status":"inconclusive",
                        "reason":reason}
            if method=="HEAD":continue
        except (OSError,ValueError) as e:
            reason=type(e).__name__+":"+str(e)[:110]
            if method=="HEAD":continue
    return {"name":item["name"],"url":url,"status":"inconclusive","reason":reason}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--catalog",type=Path,default=Path("data/sources_catalog_full.json"))
    p.add_argument("--output",type=Path,default=Path("PULSE_SOURCE_LINKS_REPORT.json"))
    args=p.parse_args()
    sources=json.loads(args.catalog.read_text(encoding="utf8"))["sources"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows=[f.result() for f in as_completed([pool.submit(probe,s) for s in sources])]
    rows.sort(key=lambda x:x["name"].casefold())
    totals={kind:sum(x["status"]==kind for x in rows)
            for kind in ("reachable","broken","inconclusive","invalid_url")}
    report={"checked_at":datetime.now(timezone.utc).isoformat(),
            "scope":"curated source links, not every article URL",
            "total":len(rows),"totals":totals,"results":rows}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    # Historical externally broken pages are actionable warnings; they are not
    # a reason to erase the last-good app content or block the entire data feed.
    return 0

if __name__=="__main__":raise SystemExit(main())
