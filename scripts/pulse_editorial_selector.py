#!/usr/bin/env python3
"""PULSE newsroom selector: source versions, newsworthiness and editorial index.

Completely separate from deterministic prose and chart engines.
No AI, network, auto-approval or fabricated source dates. Scores are editorial
heuristics, NOT scientific statistical significance or verification confidence.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import math
import re

from scripts.pulse_topic_coverage import independent_metric_identity

SCHEMA = "pulse-editorial-frontpage-v1"
REGISTRY = "pulse-source-versions-v1"
MAX_STORIES_PER_TOPIC = 2
MAX_FEATURES_PER_DAY = 12
MAX_CONTEXT_ANALYSES_PER_DAY = 6
CONTEXT_TOPICS = frozenset(("DEMOGRAFIA", "SALUTE", "ISTRUZIONE",
                            "CASA", "AMBIENTE", "ENERGIA"))
MAX_BRIEFS_PER_DAY = 20
HISTORY_LIMIT = 8
REGISTRY_LIMIT = 4000
MONTH = re.compile(r"((?:19|20)\d\d)-(0[1-9]|1[0-2])$")
YEAR = re.compile(r"(?:19|20)\d\d$")
QUARTER = re.compile(r"((?:19|20)\d\d)-Q([1-4])$")

# Impact is the relevance of a documented subject, not a ranking of people.
TOPIC_IMPACT = {"SALUTE":19, "CASA":19, "DEMOGRAFIA":18, "ECONOMIA":17,
                "ISTRUZIONE":17, "AMBIENTE":17, "ENERGIA":17,
                "LAVORO":16, "SOCIETA":17, "ALTRO":11}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def observation_signature(evidence):
    s = evidence["series"]
    fields = [(str(o["period"]), str(o["value"])) for o in s["observations"]]
    return sha256(canonical(fields).encode()).hexdigest()


def series_key(evidence):
    s = evidence["series"]
    key = [evidence["dataset_url"], s["indicator"], s["territory"],
           s["population"], s["unit"], s.get("frequency"),
           s.get("classification_values") or {}]
    return sha256(canonical(key).encode()).hexdigest()[:32]


def consecutive(a, b):
    if YEAR.fullmatch(a) and YEAR.fullmatch(b):
        return int(b) == int(a) + 1
    m, n = MONTH.fullmatch(a), MONTH.fullmatch(b)
    if m and n:
        return int(n[1])*12+int(n[2]) == int(m[1])*12+int(m[2])+1
    m, n = QUARTER.fullmatch(a), QUARTER.fullmatch(b)
    if m and n:
        return int(n[1])*4+int(n[2]) == int(m[1])*4+int(m[2])+1
    return False


def parsed_time(text):
    if not text or not isinstance(text, str):
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z","+00:00"))
        if dt.tzinfo is None: return None
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def change_score(evidence):
    s=evidence["series"]
    rows=s["observations"]
    if len(rows)<2 or not consecutive(str(rows[-2]["period"]),str(rows[-1]["period"])):
        return 0, "confronto_non_consecutivo"
    try:
        a,b=float(rows[-2]["value"]),float(rows[-1]["value"])
        if not all(math.isfinite(v) for v in (a,b)):
            return 0,"valori_non_finiti"
    except (ValueError, TypeError, KeyError):
        return 0,"valori_non_validi"
    diff=abs(b-a)
    if s["unit"]=="%":
        # Absolute percentage-points, not conflated with a relative percent.
        if diff>=3: return 35, "variazione_di_almeno_3_punti_percentuali"
        if diff>=1: return 27, "variazione_di_almeno_1_punto_percentuale"
        if diff>=0.5: return 16, "variazione_di_almeno_mezzo_punto"
        return 0,"scarto_percentuale_piccolo"
    # Multiplicative growth from tiny bases is not automatically 'significant'.
    rel=diff/abs(a) if a else None
    if rel is not None and diff>=10 and rel>=0.25:
        return 35,"scarto_almeno_25pct_e_10_unita"
    if rel is not None and diff>=10 and rel>=0.10:
        return 25,"scarto_almeno_10pct_e_10_unita"
    if rel is not None and diff>=5 and rel>=0.05:
        return 15,"scarto_almeno_5pct_e_5_unita"
    return 0,"segnale_non_sufficiente_o_base_zero"



def editorial_family(evidence):
    """Suppress repeat national features from sex/age cuts of one measure.

    Never combine territorial stories, datasets or distinct Eurostat units.
    Stable for source revisions, independent of a changing reference year.
    """
    series = evidence["series"]
    topic = str(evidence.get("topic") or "ALTRO").upper()
    territory = str(series["territory"]).casefold()
    if evidence.get("publisher") == "EUROSTAT":
        family = independent_metric_identity(evidence["dataset_url"])
    else:
        family = (str(evidence["dataset_url"]), str(series["indicator"]).casefold())
    return sha256(canonical((topic, territory, family)).encode()).hexdigest()[:24]


def published_family(item):
    """Identify an existing official feature from its persisted source facts."""
    if not isinstance(item,dict) or item.get("publication_status")!="published":
        return None
    try:
        source=item["source_documents"][0]["url"]
        metric=item["verified_series_relevant"][0]
        publisher=item.get("public_source",{}).get("domain")
        return editorial_family({
            "topic":item["topic"],"dataset_url":source,"publisher":publisher,
            "series":{"indicator":metric["indicator"],
                      "territory":metric["territory"]}})
    except (KeyError, IndexError, TypeError):
        return None


def assess(item,evidence,known,now,topic_counts):
    """One checked dossier. A source updated timestamp alone NEVER means news."""
    now=now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    series=evidence["series"]
    latest=str(series["observations"][-1]["period"])
    digest=observation_signature(evidence)
    prior=known if isinstance(known,dict) else None
    same_period=bool(prior and prior.get("last_period")==latest)
    if prior and same_period and prior.get("observation_signature")==digest:
        novelty="unchanged"
    elif prior and same_period:
        novelty="revision"
    elif prior:
        novelty="new_reference_period"
    else:
        novelty="first_seen_by_pulse"
    released=parsed_time(evidence.get("source_publication_date"))
    release_recent=bool(released and timedelta(0)<=now-released<=timedelta(days=30))
    # 'First seen by PULSE' is NOT the source's publication date.
    freshness={
        "unchanged":0,"revision":20,"new_reference_period":30,
        "first_seen_by_pulse":16 if release_recent else 9,
    }[novelty]
    signal,reason=change_score(evidence)
    topic=str(item.get("topic") or evidence.get("topic") or "ALTRO").upper()
    impact=TOPIC_IMPACT.get(topic,TOPIC_IMPACT["ALTRO"])
    # Frequency-based bonus, only to break ties, cannot create "news".
    diversity=max(0,10-min(10,int(topic_counts.get(topic,0))*2))
    score=freshness+signal+impact+diversity
    # First discovery is NOT proof of a new official release. At most a
    # labelled short briefing; no long-form "new" article until a later
    # reference period arrives or an explicit human editor approves it.
    qualified=novelty=="new_reference_period"
    first_seen_brief=novelty=="first_seen_by_pulse" and release_recent
    if novelty=="revision":
        tier="review_revision"  # explicit review; never silently overwrite.
    elif qualified and signal>=15 and score>=65:
        tier="feature"
    elif (novelty in ("first_seen_by_pulse", "unchanged")
          and topic in CONTEXT_TOPICS
          and topic_counts.get(topic,0)<5 and signal>=27
          and latest[:4].isdigit() and int(latest[:4])>=now.year-3):
        # Background analysis, never a claim of a freshly released source.
        tier="context"
    elif (qualified or first_seen_brief) and (score>=45 or signal>=15):
        tier="brief"
    else:
        tier="catalogue"
    return {
        "article_id":item["id"],"topic":topic,"score":score,
        "headline":str(item.get("headline") or ""),
        "source_url":str(evidence.get("source_url") or ""),
        "parts":{"newness":freshness,"signal":signal,"impact":impact,"diversity":diversity},
        "reason":reason, "novelty":novelty,"tier":tier,
        "period_reference":latest,
        "source_release_date":released.isoformat() if released else None,
        "source_release_recent":release_recent,
        "source_release_proven":False, # Eurostat dataset update can be structural.
        "series_key":series_key(evidence),
        "editorial_family":editorial_family(evidence),
        "observations_sha256":digest,
    }


def _updated_state(evidence,current,now):
    s=evidence["series"]
    latest=str(s["observations"][-1]["period"])
    signature=observation_signature(evidence)
    prior=current if isinstance(current,dict) else {}
    history=list(prior.get("history") or [])[-HISTORY_LIMIT:]
    if (not history or history[-1].get("period") != latest
            or history[-1].get("sha256") != signature):
        history.append({"period":latest,"sha256":signature,"first_seen_at":now})
    return {
        "dataset_url":evidence["dataset_url"], "indicator":s["indicator"],
        "territory":s["territory"],"topic":str(evidence.get("topic") or "").upper(),
        "last_period":latest,
        "observation_signature":signature,"source_bytes_sha256":evidence["source_sha256"],
        "source_updated_at":evidence.get("source_publication_date"),
        "last_checked_at":now,"history":history[-HISTORY_LIMIT:],
    }


def evaluate(verified_pairs,previous_articles,previous_versions,previous_frontpage,now):
    """Return frontpage & version ledger and deterministic publication decisions."""
    now_dt=parsed_time(now) or datetime.now(timezone.utc)
    old_versions=dict((previous_versions or {}).get("series") or {})
    counts=Counter(a.get("topic") for a in previous_articles
                   if isinstance(a,dict) and a.get("topic"))
    published_families={key for a in previous_articles
                        if (key:=published_family(a)) is not None}
    assessments=[]
    for item,evidence in verified_pairs:
        key=series_key(evidence)
        result=assess(item,evidence,old_versions.get(key),now_dt,counts)
        assessments.append(result)
        # An unchanged official series is not a new source version and should
        # never create a daily Git commit by updating last_checked_at.
        if result["novelty"] != "unchanged":
            old_versions[key]=_updated_state(evidence,old_versions.get(key),now)
    # Never privilege input order/INPS position: highest verified signal first.
    assessments.sort(key=lambda x:(-x["score"],x["topic"],x["article_id"]))
    selected=[];briefs=[];catalogue=[];revisions=[];chosen_topic=Counter()
    context_candidates=[];context_analyses=[];context_topics=set()
    chosen_families=set()
    for a in assessments:
        if a["tier"]=="review_revision":
            revisions.append(a)
        elif a["tier"]=="feature":
            if a["editorial_family"] in chosen_families:
                catalogue.append({**a,"tier":"catalogue",
                                  "reason":"same_independent_indicator_family"})
            elif (len(selected)<MAX_FEATURES_PER_DAY
                    and chosen_topic[a["topic"]]<MAX_STORIES_PER_TOPIC):
                selected.append(a);chosen_topic[a["topic"]]+=1
                chosen_families.add(a["editorial_family"])
            else:
                catalogue.append({**a,"tier":"catalogue",
                                  "reason":"editorial_capacity_or_topic_balance"})
        elif a["tier"]=="context":
            if a["editorial_family"] in published_families:
                catalogue.append({**a,"tier":"catalogue",
                                  "reason":"already_published_independent_family"})
            else:
                context_candidates.append(a)
        elif a["tier"]=="brief":
            if len(briefs)<MAX_BRIEFS_PER_DAY: briefs.append(a)
            else: catalogue.append({**a,"tier":"catalogue"})
        else:
            catalogue.append(a)
    # New official reference periods always take precedence over archives.
    # Context dossiers are published separately and explicitly labelled.
    for a in context_candidates:
        if (len(context_analyses)<MAX_CONTEXT_ANALYSES_PER_DAY
                and len(selected)+len(context_analyses)<MAX_FEATURES_PER_DAY
                and a["topic"] not in context_topics
                and chosen_topic[a["topic"]]==0
                and a["editorial_family"] not in chosen_families):
            context_analyses.append(a)
            context_topics.add(a["topic"])
            chosen_families.add(a["editorial_family"])
        else:
            catalogue.append({**a,"tier":"catalogue",
                              "reason":"context_capacity_or_family_balance"})
    # Keep today's previously featured IDs while checking again the same day.
    last=previous_frontpage if isinstance(previous_frontpage,dict) else {}
    recent_same_day=str(last.get("generated_at",""))[:10]==now[:10]
    old_selected=last.get("featured_article_ids",[]) if recent_same_day else []
    featured=list(dict.fromkeys(old_selected+[a["article_id"] for a in selected]))
    digest={
        "schema":SCHEMA,"generated_at":now,
        "editorial_method":"source_versions_and_verified_material_change_no_ai",
        "featured_article_ids":featured[:MAX_FEATURES_PER_DAY],
        "features_new":[a["article_id"] for a in selected],
        "context_analyses_new":[a["article_id"] for a in context_analyses],
        "context_analyses_not_source_news":True,
        "context_topics":sorted(context_topics),
        "briefs":[{"article_id":a["article_id"],"topic":a["topic"],
                   "headline":a["headline"],"source_url":a["source_url"],
                   "score":a["score"],"reason":a["reason"],
                   "period_reference":a["period_reference"],
                   "source_release_recent":a["source_release_recent"]}
                  for a in briefs],
        "revision_review":[{"article_id":a["article_id"],
                            "period_reference":a["period_reference"],
                            "reason":"same_period_observations_changed_human_review"}
                           for a in revisions],
        "catalogue_updates_count":len(catalogue),
        "new_feature_topics": dict(sorted(chosen_topic.items())),
        "independent_feature_families_selected": len(chosen_families),
        "unpublished_eligible_features_by_topic": dict(sorted(
            Counter(a["topic"] for a in catalogue
                    if a["reason"] in ("same_independent_indicator_family",
                                      "editorial_capacity_or_topic_balance")).items())),
        "all_existing_articles_remain_in_archive":True,
        "no_automatic_publication_from_revision":True,
        "source_date_not_inferred_from_observation_period":True,
        "thresholds":{"feature":65,"brief":45,"max_features_per_day":MAX_FEATURES_PER_DAY,
                      "max_features_per_topic":MAX_STORIES_PER_TOPIC,
                      "max_context_analyses_per_day":MAX_CONTEXT_ANALYSES_PER_DAY,
                      "context_min_signal":27},
        "assessments":assessments[:200],
    }
    ledger={"schema":REGISTRY,"generated_at":now,"series":dict(
        list(sorted(old_versions.items()))[-REGISTRY_LIMIT:])}
    return digest,ledger,{a["article_id"]:a for a in assessments}
