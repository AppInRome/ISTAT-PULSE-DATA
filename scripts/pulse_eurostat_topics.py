#!/usr/bin/env python3
"""Eurostat JSON-stat 2.0 official-data discovery for diversified Italian news.

Only narrow, documented datasets and Italy IT are eligible. Source bytes SHA256,
original multidimensional cell coordinates, exact unit/period/category and
observation-status flags are retained. Never fabricates values, Italy totals
from regions, comparisons, or journalistic release timestamps.

Official documentation: https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
from urllib.parse import urlencode, urlsplit

from scripts import pulse_editorial_engine_v1 as engine

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
METHOD = "eurostat_jsonstat2_exact_multidimensional_cell"
LAST_PERIODS = 12
MAX_RESP_BYTES = 12_000_000

# Codes and indicator meanings checked against official Eurostat catalogue.
# A query/metric is NOT accepted unless the JSON-stat dimensions resolve to
# exactly one explicit classification per dimension and a truthful unit.
CATALOG = (
    {
        "id": "nama_10_gdp", "topic": "ECONOMIA",
        "indicator": "Prodotto interno lordo a prezzi correnti",
        "unit": "milioni di euro", "unit_code": "CP_MEUR",
        "population": "Economia italiana; prodotto interno lordo a prezzi di mercato",
        "filters": {"freq": "A", "na_item": "B1G", "unit": "CP_MEUR"},
    },
    {
        "id": "demo_pjan", "topic": "DEMOGRAFIA",
        "indicator": "Popolazione al primo gennaio",
        "unit": "persone", "unit_code": "NR",
        "population": "Residenti al primo gennaio, tutte le età e i sessi",
        "filters": {"sex": "T", "age": "TOTAL"},
    },
    {
        "id": "sdg_04_20", "topic": "ISTRUZIONE",
        "indicator": "Quota di giovani adulti con istruzione terziaria",
        "unit": "%", "unit_code": "PC",
        "population": "Giovani adulti, entrambi i sessi",
        "filters": {"sex": "T"},
    },
    {
        "id": "tps00208", "topic": "SALUTE",
        "indicator": "Speranza di vita alla nascita",
        "unit": "anni", "unit_code": "YR",
        "population": "Speranza di vita alla nascita, entrambi i sessi",
        "filters": {"sex": "T"},
    },
    {
        "id": "tessi171", "topic": "CASA",
        "indicator": "Popolazione che vive in abitazioni sovraffollate",
        "unit": "%", "unit_code": "PC",
        "population": "Totale popolazione, entrambi i sessi, indagine EU-SILC",
        "filters": {"sex": "T", "age": "TOTAL", "incgrp": "TOTAL"},
    },
    {
        "id": "env_wasmun", "topic": "AMBIENTE",
        "indicator": "Rifiuti urbani prodotti per abitante",
        "unit": "kg per abitante", "unit_code": "KG_HAB",
        "population": "Rifiuti urbani generati in Italia",
        "filters": {"freq": "A", "unit": "KG_HAB", "wst_oper": "GEN"},
    },
    {
        "id": "sdg_07_40", "topic": "ENERGIA",
        "indicator": "Quota di energia da fonti rinnovabili",
        "unit": "%", "unit_code": "PC",
        "population": "Consumo finale lordo di energia: quota rinnovabile",
        "filters": {"nrg_bal": "REN"},
    },
)


def request_url(config):
    name = config["id"]
    if not re.fullmatch(r"[a-z][a-z0-9_]{3,32}", name):
        raise ValueError("not_curated_dataset_code")
    filters = config["filters"]
    params = {"lang":"EN", "geo":"IT", "lastTimePeriod":LAST_PERIODS, **filters}
    return API + name + "?" + urlencode(params)


def _category_code(dimension, length):
    category = dimension.get("category")
    if not isinstance(category, dict):
        raise ValueError("missing_category")
    idx = category.get("index")
    if isinstance(idx, dict):
        mapping = idx
    elif isinstance(idx, list):
        mapping = {v:i for i,v in enumerate(idx)}
    else:
        raise ValueError("invalid_category_index")
    if len(mapping) != length or set(mapping.values()) != set(range(length)):
        raise ValueError("ambiguous_category_indices")
    return {i:code for code,i in mapping.items()}


def verified_jsonstat_evidence(raw, config, url):
    """Return a source-locked evidence or fail closed, NEVER infer categories."""
    if url != request_url(config) or urlsplit(url).hostname != "ec.europa.eu":
        raise ValueError("untrusted_eurostat_url")
    if not isinstance(raw, bytes) or len(raw) > MAX_RESP_BYTES:
        raise ValueError("bad_api_response_size")
    obj = json.loads(raw)
    if not isinstance(obj, dict) or obj.get("class") not in {"dataset", None}:
        raise ValueError("not_jsonstat_dataset")
    order, sizes, dimensions = obj.get("id"), obj.get("size"), obj.get("dimension")
    values = obj.get("value")
    if (not isinstance(order, list) or not isinstance(sizes, list)
            or not isinstance(dimensions, dict) or len(order) != len(sizes)
            or len(set(order)) != len(order) or not all(isinstance(v,int) and v>0 for v in sizes)):
        raise ValueError("invalid_jsonstat_dimensions")
    if "time" not in order or "geo" not in order:
        raise ValueError("missing_country_or_period")
    if order.count("time") != 1 or order.count("geo") != 1:
        raise ValueError("ambiguous_time_geo")
    if (not isinstance(values, (dict,list)) or math.prod(sizes)>5000
            or len(raw)>MAX_RESP_BYTES):
        raise ValueError("too_many_jsonstat_cells")
    resolved, labels = {}, {}
    for dim,size in zip(order,sizes):
        member = dimensions.get(dim)
        if not isinstance(member,dict):
            raise ValueError("missing_dimension_"+dim)
        codes = _category_code(member, size)
        member_labels = (member.get("category") or {}).get("label") or {}
        if dim == "time":
            resolved[dim] = codes
            continue
        required = "IT" if dim=="geo" else config["filters"].get(dim)
        if required is not None:
            positions = [i for i,c in codes.items() if str(c)==str(required)]
            if len(positions)!=1:
                raise ValueError("requested_category_not_in_response_"+dim)
            position=positions[0]
        elif size == 1:
            position=0
        else:
            raise ValueError("unfiltered_multi_category_"+dim)
        resolved[dim] = position
        key = codes[position]
        labels[dim] = {"code":key,
                       "label":str(member_labels.get(key, key))[:130]}
    if labels["geo"]["code"] != "IT":
        raise ValueError("non_italian_observations")
    if "unit" in labels and labels["unit"]["code"] != config["unit_code"]:
        raise ValueError("unit_metadata_mismatch")
    if "unit" not in labels and config["unit_code"] not in {"PC","NR","YR"}:
        raise ValueError("original_unit_not_exposed")
    periods = resolved["time"]
    by_period = []
    observed_status = obj.get("status")
    if observed_status is not None and not isinstance(observed_status,(dict,list)):
        raise ValueError("invalid_status_metadata")
    def at(container,index):
        return container.get(str(index)) if isinstance(container,dict) else (
            container[index] if isinstance(container,list) and index<len(container) else None)
    for position,period in periods.items():
        text = str(period)
        if not re.fullmatch(r"(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]|Q[1-4]))?", text):
            raise ValueError("non_calendar_period")
        cell = 0
        for i,dim in enumerate(order):
            selected = position if dim == "time" else resolved[dim]
            cell += selected * math.prod(sizes[i+1:])
        value = at(values,cell)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value)):
            continue
        status=at(observed_status,cell) if observed_status is not None else None
        if status is not None:
            # A break, low reliability or confidential/suppressed cell cannot
            # safely be compared, however valid the neighbouring numbers look.
            flags = str(status).casefold()
            if any(flag in flags for flag in ("b","c","u","d","n","s","z")):
                continue
        if config["unit"]=="%" and not 0 <= float(value) <= 100:
            raise ValueError("impossible_percentage")
        by_period.append((text,float(value),cell,str(status or "")))
    by_period.sort(key=lambda x:x[0])
    if len(by_period)<2 or len({a[0] for a in by_period})!=len(by_period):
        raise ValueError("not_enough_usable_official_periods")
    from scripts.pulse_italia_chart_analytics import calculate
    observations = [{"period":p,"value":v,"raw":str(v)}
                    for p,v,_,_ in by_period][-24:]
    calculate({"unit":config["unit"],"observations":observations})
    return {
        "schema_version":1,"verified":True,
        "publisher":"EUROSTAT",
        "source_url":"https://ec.europa.eu/eurostat/databrowser/view/"
                      + config["id"] + "/default/table?lang=en",
        "dataset_url":url,
        "source_sha256":sha256(raw).hexdigest(),
        "retrieval_mode":"https",
        "source_locations":[
            {"period":p,"jsonstat_cell_index":index,
             "dimensions":{k:v["code"] for k,v in labels.items()},
             "official_flags":flag}
            for p,_,index,flag in by_period[-24:]],
        "extraction_method":METHOD,
        "series":{
            "indicator":config["indicator"], "unit":config["unit"],
            "territory":"Italia","population":config["population"],
            "frequency":"Annuale (Eurostat)"
                        if re.fullmatch(r"(?:19|20)\d{2}",observations[-1]["period"])
                        else "Frequenza esplicita Eurostat",
            "classification_values":{k:v["code"] for k,v in labels.items()},
            "classification_labels":{k:v["label"] for k,v in labels.items()},
            "observations":observations
        },
        "topic":config["topic"],
        "methodology_url":"https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access",
        "auto_discovered_from":"EUROSTAT_statistics_JSONstat_API_official_curated",
        "eurostat_dataset_code":config["id"],
        "source_publication_date":obj.get("updated"),
        "editorial_status":"requires_human_semantic_review",
    }


def discover(fetch_fn=engine.fetch, limit=None):
    """Return only validated official series and an honest per-theme report."""
    results, checks = [], []
    configs = CATALOG if limit is None else CATALOG[:max(0,min(int(limit),len(CATALOG)))]
    for spec in configs:
        url=request_url(spec)
        report = {"source":"EUROSTAT","topic":spec["topic"],"dataset":spec["id"]}
        try:
            raw=fetch_fn(url)
            evidence=verified_jsonstat_evidence(raw,spec,url)
            results.append(evidence)
            report["status"]="source_series_found"
            report["observations"]=len(evidence["series"]["observations"])
        except (OSError, ValueError, TypeError, KeyError, IndexError,
                OverflowError, UnicodeError, json.JSONDecodeError) as e:
            report["status"]="inaccessible_or_not_comparable"
            report["error_type"]=type(e).__name__
            report["reason"]=str(e)[:110]
        checks.append(report)
    return results,checks
