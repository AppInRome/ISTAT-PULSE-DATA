#!/usr/bin/env python3
"""Source-locked regional comparison editor. Never changes original articles/graphs.

A 'national' card means a multi-region reading, NEVER an Italy total.
Only identical official dataset, SHA, measure, population, unit, period,
frequency and non-geographic classification are compared. No AI.
"""
from collections import defaultdict
from hashlib import sha256
import json
import math
import re

SCHEMA = "pulse-regional-comparisons-v1"
MONTHS = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
          "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
MEASURES = {"numero_lavoratori": "lavoratori rilevati",
            "numero_mensilita": "mensilità rilevate",
            "numero_domande": "domande rilevate"}
GEOGRAPHY = {"regione", "territorio", "area", "areageografica",
             "ripartizione", "refarea"}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def consecutive(before, after):
    if re.fullmatch(r"(?:19|20)\d{2}", after) and re.fullmatch(r"(?:19|20)\d{2}", before):
        return int(after) - int(before) == 1
    m = re.fullmatch(r"((?:19|20)\d{2})-(0[1-9]|1[0-2])", after)
    if m:
        y, n = map(int, m.groups())
        return before == (f"{y-1}-12" if n == 1 else f"{y}-{n-1:02d}")
    return False


def period_label(period):
    m = re.fullmatch(r"((?:19|20)\d{2})-(0[1-9]|1[0-2])", period)
    return f"{MONTHS[int(m[2])]} {m[1]}" if m else period


def candidate(item, evidence):
    if not isinstance(item, dict) or not isinstance(evidence, dict):
        return None
    s = evidence.get("series") or {}
    obs = s.get("observations") or []
    fixed = s.get("classification_values")
    if (item.get("editorial_format") != "deterministic_source_locked_auto_audited"
            or item.get("publication_status") != "published"
            or item.get("automatic_review", {}).get("passed") is not True
            or item.get("automatic_review", {}).get("model_used") is not False
            or evidence.get("verified") is not True or len(obs) < 2
            or not isinstance(fixed, dict) or not fixed):
        return None
    try:
        before, after = str(obs[-2]["period"]), str(obs[-1]["period"])
        if not consecutive(before, after):
            return None
        x, y = float(obs[-2]["value"]), float(obs[-1]["value"])
        if not all(math.isfinite(v) and v >= 0 for v in (x, y)):
            return None
        doc = item["source_documents"][0]
        v = item["verified_series_relevant"][0]
        if (doc["url"] != evidence["dataset_url"]
                or doc["sha256"] != evidence["source_sha256"]
                or item.get("period_reference") != after
                or item["public_source"]["role"] != "primary_statistical_source"
                or any(v.get(k) != s.get(k) for k in
                       ("indicator", "unit", "territory", "population"))
                or v["observations"][-1]["period"] != after
                or abs(float(v["observations"][-1]["value"]) - y) > 1e-7):
            return None
        label = str(s["indicator"])
        m = re.search(r"—\s*(Numero_lavoratori|Numero_mensilita|Numero_domande)\s*$", label, re.I)
        if not m or m[1].casefold() not in MEASURES:
            return None
        if str(s.get("unit", "")).casefold() not in {"numero", "n."}:
            return None
        region = str(s.get("territory") or "").strip()
        if not region or region.casefold() in {"italia", "nazionale", "totale italia", "it"}:
            return None
        categories = sorted((str(k).casefold(), str(val).casefold())
                            for k, val in fixed.items()
                            if re.sub(r"[^a-z]", "", str(k).casefold()) not in GEOGRAPHY)
        key = [evidence["dataset_url"], evidence["source_sha256"], label.casefold(),
               str(s.get("population", "")).casefold(), str(s["unit"]).casefold(),
               str(s.get("frequency", "")).casefold(), categories, after, before]
        return {"key": key, "id": item["id"], "territory": region, "latest": y,
                "previous": x, "difference": round(y-x, 6),
                "relative_percent": None if x == 0 else round((y-x)/x*100, 2),
                "period": after, "previous_period": before,
                "measure": m[1].casefold(), "unit": s["unit"],
                "publisher": evidence["publisher"], "source_url": evidence["source_url"],
                "published_at": item["published_at"]}
    except (KeyError, ValueError, TypeError, IndexError, ZeroDivisionError):
        return None


def build_digest(verified_pairs, old_digest=None, published_at=None):
    groups = defaultdict(list)
    for item, evidence in verified_pairs:
        found = candidate(item, evidence)
        if found:
            groups[canonical(found["key"])].append(found)
    earlier = {g.get("id"): g for g in (old_digest or {}).get("groups", [])
               if isinstance(g, dict) and str(g.get("id", "")).startswith("PULSE-CMP-")}
    updated = dict(earlier)
    for group_key, records in groups.items():
        unique = {}
        for r in records:
            region = r["territory"].casefold()
            unique[region] = None if region in unique else r
        rows = sorted((r for r in unique.values() if r is not None),
                      key=lambda r: r["territory"].casefold())
        if len(rows) < 3:
            continue
        first = rows[0]
        # Two different official classifications may share the same indicator.
        # Their groups must remain distinct AND explain the distinction.
        category_labels = json.loads(group_key)[6]
        classification_note = "; ".join(
            str(k).replace("_", " ").capitalize() + ": " + str(v)
            for k, v in category_labels)[:180]
        gid = "PULSE-CMP-" + sha256(group_key.encode()).hexdigest()[:22].upper()
        old = earlier.get(gid) or {}
        label = period_label(first["period"])
        subject = MEASURES[first["measure"]]
        title = f"Integrazioni salariali: {subject} in {len(rows)} regioni, {label}"
        if len(title) > 110:
            continue
        rises = sum(r["difference"] > 0 for r in rows)
        falls = sum(r["difference"] < 0 for r in rows)
        same = len(rows) - rises - falls
        salient = [r for r in rows
                   if r["relative_percent"] is not None
                   and abs(r["relative_percent"]) >= 25
                   and abs(r["difference"]) >= 10]
        salient.sort(key=lambda r: (-abs(r["relative_percent"]),
                                   -abs(r["difference"]), r["territory"].casefold()))
        spotlight = {r["id"] for r in salient[:2]}
        desc = (f"I dati INPS consentono di confrontare {len(rows)} regioni per "
                f"{subject} ({label}). In {rises} i valori crescono, "
                f"in {falls} diminuiscono e in {same} restano invariati.")
        caution = ("Non è un totale Italia né una classifica corretta per popolazione. "
                   "Il grafico confronta le variazioni entro ciascuna regione "
                   "fra due periodi omogenei; nessuna causa è dedotta dai numeri.")
        result = {
            "id": gid, "published_at": old.get("published_at") or published_at or first["published_at"],
            "title": title, "summary": desc, "caution": caution,
            "heading": "ITALIA · CONFRONTO FRA REGIONI",
            "period_reference": first["period"],
            "previous_period": first["previous_period"], "period_display": label,
            "publisher": first["publisher"], "source_url": first["source_url"],
            "measure": first["measure"], "unit": first["unit"],
            "classification_note": classification_note,
            "coverage": len(rows), "country_total_available": False,
            "regional_selection_rule": "relative_change_at_least_25pct_and_difference_at_least_10_max_2",
            "paragraphs": [
                f"L'INPS rileva {subject} in {len(rows)} regioni confrontabili a {label}. "
                "Le serie derivano dallo stesso dataset e hanno classificazioni, periodi e unità omogenee.",
                f"Fra le regioni disponibili i valori crescono in {rises}, "
                f"diminuiscono in {falls} e rimangono invariati in {same}. "
                "Il dato aggregato nazionale non è disponibile da questa selezione.",
                "Il confronto grafico riguarda le variazioni percentuali interne alle regioni, "
                "non una graduatoria del numero di beneficiari per residente.",
                "La selezione dei territori in evidenza identifica scarti marcati osservati: "
                "non è un test di significatività statistica e non dimostra relazioni causali.",
            ],
            "regions": [{"article_id": r["id"], "territory": r["territory"],
                         "latest": r["latest"], "previous": r["previous"],
                         "difference": r["difference"], "relative_percent": r["relative_percent"]}
                        for r in rows],
            "related_article_ids": [r["id"] for r in rows],
            "spotlight_article_ids": [r["id"] for r in rows if r["id"] in spotlight],
        }
        if gid not in updated or len(result["regions"]) >= len(updated[gid].get("regions", [])):
            updated[gid] = result
    return {"schema": SCHEMA, "groups": sorted(
        updated.values(), key=lambda x: (x["published_at"], x["id"]), reverse=True)[:100]}
