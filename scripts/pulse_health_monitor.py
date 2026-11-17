#!/usr/bin/env python3
"""Read-only PULSE operational monitor: no update is NOT a stale backend."""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path

def utc(value):
    if not value:return None
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (TypeError,ValueError):return None

def inspect(root:Path,now=None):
    now=now or datetime.now(timezone.utc)
    errors=[];warnings=[];checks={}
    def read(name):
        try:return json.loads((root/name).read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            errors.append("file_missing_or_invalid:"+name+":"+str(exc)[:80]);return {}
    report=read("refresh_status.json")
    observers=read("observer_refresh_status.json")
    index=read("news/index.json")
    articles=read("news/articles.json")
    def age(label,raw,limit):
        dt=utc(raw)
        if not dt:
            errors.append("missing_utc_date:"+label)
            return
        hours=round((now-dt).total_seconds()/3600,2)
        checks[label]={"checked_at":dt.isoformat(),"age_hours":hours,"maximum_hours":limit}
        if hours < -2:errors.append("clock_in_future:"+label)
        elif hours > limit:errors.append("backend_stale:"+label+":"+str(hours)+"h")
    age("backend_check",report.get("last_check_at"),12)
    age("news_generation",index.get("generated_at"),12)
    age("observer_check",observers.get("checked_at"),72)
    news=report.get("sections",{}).get("notizie",{})
    age("news_last_success",news.get("last_success_at"),12)
    if news.get("status")!="ok":errors.append("news_backend_not_ok")
    reached=news.get("feeds_reached",-1)
    configured=news.get("feeds_configured",-1)
    if not isinstance(reached,int) or not isinstance(configured,int) or reached<1 or configured<1:
        errors.append("news_feeds_unavailable")
    elif reached<configured:
        warnings.append(f"news_feed_partial:{reached}/{configured}")
    if articles.get("generated_at")!=index.get("generated_at"):
        errors.append("news_generation_mismatch")
    rows=articles.get("articles") or []
    if not isinstance(rows,list) or len(rows)<50:
        errors.append("news_archive_incomplete")
    for bucket in ("oggi","ieri","archivio"):
        values=index.get(bucket)
        if not isinstance(values,list):errors.append("news_bucket_missing:"+bucket)
        elif len(values)!=(index.get("counts") or {}).get(bucket,-1):
            errors.append("news_bucket_wrong_count:"+bucket)
    obs_reached=observers.get("feeds_reached",-1)
    obs_configured=observers.get("feeds_configured",-1)
    if not isinstance(obs_reached,int) or obs_reached<1:
        errors.append("all_observer_feeds_unavailable")
    elif isinstance(obs_configured,int) and obs_reached<obs_configured:
        failed={name:v.get("error","unknown") for name,v in
                observers.get("sources",{}).items() if v.get("status")!="ok"}
        warnings.append("observer_feed_partial:"+json.dumps(failed,ensure_ascii=False))
    # An unchanged official publication is normal. Do NOT require articles_new>0.
    return {"healthy":not errors,"checked_at":now.isoformat(),
        "checks":checks,"news_feed_reached":reached,"news_feed_total":configured,
        "observer_feed_reached":obs_reached,"observer_feed_total":obs_configured,
        "observer_new_publications":observers.get("articles_new"),
        "errors":errors,"warnings":warnings,
        "explanation":"A check succeeding is not a new statistical publication. No new data is not a failure."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-root",type=Path,default=Path("data"))
    p.add_argument("--report",default="PULSE_HEALTH_REPORT.json")
    p.add_argument("--summary",default="PULSE_HEALTH_SUMMARY.md")
    args=p.parse_args()
    report=inspect(args.data_root)
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    lines=["# PULSE automatic publishing — health", "",
           "**Health:** "+("OK" if report["healthy"] else "ALERT"),
           "**Check:** "+report["checked_at"],"","## Feed","",
           f"- News reached: {report['news_feed_reached']}/{report['news_feed_total']}",
           f"- Official observers reached: {report['observer_feed_reached']}/{report['observer_feed_total']}",
           f"- New official publications since last check: {report['observer_new_publications']}",
           "","## Errors", *(["- "+x for x in report["errors"]] or ["- None"]),
           "","## Partial sources", *(["- "+x for x in report["warnings"]] or ["- None"]),
           "","A healthy check does not mean the institution published new data."]
    Path(args.summary).write_text("\n".join(lines)+"\n")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report["healthy"] else 2

if __name__=="__main__":raise SystemExit(main())
