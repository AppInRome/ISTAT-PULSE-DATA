#!/usr/bin/env python3
"""Proof-oriented public subject coverage report for PULSE.

'catalogue candidates' are NOT verified; gender splits do not inflate the
number of independent indicators; publication count is separate from verified
series count. No fabricated quotas, no AI, no article/graph modifications.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit,parse_qsl,urlencode

TOPIC_TARGETS={"ECONOMIA":5,"DEMOGRAFIA":5,"SALUTE":5,"ISTRUZIONE":5,
               "CASA":5,"AMBIENTE":5,"ENERGIA":5,"LAVORO":5}
SCHEMA="pulse-topic-coverage-v1"


def independent_metric_identity(dataset_url):
    p=urlsplit(str(dataset_url))
    # Population and sex slices are legitimate editorial contexts, but are
    # NOT independent statistical subject families.
    ignored={"geo","sex","age","lang","lastTimePeriod","sinceTimePeriod",
             "untilTimePeriod","time","startPeriod","endPeriod"}
    keep=sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)
                if k not in ignored)
    return (p.hostname,p.path,urlencode(keep))



def _historical_topics(entries, articles):
    """Recover labels ONLY for previously verified registry series.

    A bounded daily candidate scan must not un-count already verified work.
    The mere existence of a catalogue candidate is NEVER a verification.
    """
    from scripts import pulse_eurostat_topics as eurostat
    catalogue = {(eurostat.request_url(c), c["indicator"]): c["topic"]
                 for c in eurostat.CATALOG}
    published = {}
    for a in articles:
        if not isinstance(a,dict) or a.get("publication_status")!="published":
            continue
        docs=a.get("source_documents") or []
        metrics=a.get("verified_series_relevant") or []
        if not docs or not metrics or not isinstance(docs[0],dict) or not isinstance(metrics[0],dict):
            continue
        k=(docs[0].get("url"), metrics[0].get("indicator"),
           metrics[0].get("territory"))
        published.setdefault(k,set()).add(str(a.get("topic") or "").upper())
    recovered={}
    for key,entry in entries.items():
        if not isinstance(entry,dict):
            continue
        if (not re.fullmatch(r"[0-9a-f]{64}",str(entry.get("source_bytes_sha256","")))
                or not re.fullmatch(r"[0-9a-f]{64}",str(entry.get("observation_signature","")))
                or not entry.get("last_period")):
            continue
        topic=str(entry.get("topic") or "").upper()
        if topic not in TOPIC_TARGETS:
            k=(entry.get("dataset_url"),entry.get("indicator"),entry.get("territory"))
            from_archive=published.get(k,set()) & set(TOPIC_TARGETS)
            if len(from_archive)==1:
                topic=next(iter(from_archive))
            else:
                topic=catalogue.get((entry.get("dataset_url"),entry.get("indicator")),"")
        if topic in TOPIC_TARGETS:
            recovered[key]=topic
    return recovered


def build(versions,frontpage,feed):
    entries=(versions or {}).get("series") or {}
    assessments=(frontpage or {}).get("assessments") or []
    articles=(feed or {}).get("articles") or []
    topics_by_key={x.get("series_key"):str(x.get("topic") or "").upper()
                   for x in assessments if isinstance(x,dict)}
    recovered=_historical_topics(entries,articles)
    recovered_only={key:topic for key,topic in recovered.items()
                    if key not in topics_by_key}
    for key,topic in recovered.items():
        topics_by_key.setdefault(key,topic)
    result={}
    for topic,target in TOPIC_TARGETS.items():
        matched=[e for k,e in entries.items() if isinstance(e,dict)
                 and topics_by_key.get(k)==topic]
        families={}
        for e in matched:
            family=independent_metric_identity(e.get("dataset_url"))
            families.setdefault(family,set()).add(str(e.get("indicator") or ""))
        published=sum(1 for a in articles
                      if isinstance(a,dict) and str(a.get("topic","")).upper()==topic
                      and a.get("publication_status")=="published")
        result[topic]={
            "target_independent_indicator_families":target,
            "independent_indicator_families_verified":len(families),
            "verified_series_or_subgroups":len(matched),
            "published_articles_in_archive":published,
            "missing_to_target":max(0,target-len(families)),
            "independent_measure_examples":sorted(
                {sorted(names)[0] for names in families.values() if names})[:20]
        }
    return {
        "schema":SCHEMA,
        "measured_from":"historically_verified_source_versions_and_current_editorial_assessments",
        "previously_verified_series_classified_from_audited_history":len(recovered_only),
        "not_a_claim_of_complete_subject_coverage":True,
        "source_checked_at":frontpage.get("generated_at"),
        "target_total":sum(TOPIC_TARGETS.values()),
        "verified_independent_families_total":sum(
            x["independent_indicator_families_verified"] for x in result.values()),
        "all_targets_met":all(x["missing_to_target"]==0 for x in result.values()),
        "topics":result
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--versions",default="data/news/source_versions.json")
    p.add_argument("--frontpage",default="data/news/editorial_frontpage.json")
    p.add_argument("--feed",default="data/news/automatic_features.json")
    p.add_argument("--output",default="data/news/topic_coverage.json")
    args=p.parse_args(argv)
    def data(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    report=build(data(args.versions),data(args.frontpage),data(args.feed))
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    contents=json.dumps(report,ensure_ascii=False,indent=2)+"\n"
    if output.exists() and output.read_text(encoding="utf-8")==contents:
        print(json.dumps({"changed":False,"verified_families":
            report["verified_independent_families_total"]}));return
    stage=output.with_suffix(".tmp")
    stage.write_text(contents,encoding="utf-8")
    stage.replace(output)
    print(json.dumps({"changed":True,"verified_families":
        report["verified_independent_families_total"],
        "all_targets_met":report["all_targets_met"]}))

if __name__=="__main__":
    main()
