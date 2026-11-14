#!/usr/bin/env python3
"""Discover *real* Italian primary statistical series without hand-authored manifests.

Supported discovery channels:
- ISTAT IstatData SDMX: rotating official dataflows already catalogued by PULSE.
- INPS Open Data CKAN: documented package_list / package_show and CSV resources.

Fail closed: ambiguous units, territories, population labels, comparisons,
redirects and unsupported formats are not published or attributed as verified.
No LLM and no publishing in this module.
"""
from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from scripts import pulse_editorial_engine_v1 as editorial
from scripts.pulse_italia_newsroom import italian_official_url

INPS_API = "https://opendata.inps.it/opendata/api/3/action/"
ISTAT_SDMX = "https://esploradati.istat.it/SDMXWS/rest/data/"
MAX_BYTES = 12_000_000
MAX_DISCOVERY_CALLS = 9
PERIOD = re.compile(r"(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]|Q[1-4]))?")
YEAR = re.compile(r"(?:19|20)\d{2}")
OFFICIAL_LATEST_YEAR = 2024  # conservative historical floor; not publication date
# Explicitly named percentages and rate indicators. Never infer monetary units
# from the magnitude of numbers or guess population denominators.
ISTAT_RATE_NAMES = frozenset({
    "Tasso di disoccupazione", "Tasso di disoccupazione giovanile",
    "Tasso di occupazione", "Tasso di inattività",
})
TOPIC_WORDS = {
    "pension": "LAVORO", "disoccup": "LAVORO", "occup": "LAVORO",
    "lavor": "LAVORO", "salari": "LAVORO", "reddito": "ECONOMIA",
    "inflaz": "ECONOMIA", "prezz": "ECONOMIA", "abit": "DEMOGRAFIA",
    "natali": "DEMOGRAFIA", "sanit": "SALUTE", "malat": "SALUTE",
    "scuol": "ISTRUZIONE", "univers": "ISTRUZIONE", "ambient": "AMBIENTE",
}


def official_topic(label):
    t = str(label).casefold()
    return next((topic for stem, topic in TOPIC_WORDS.items() if stem in t), "ALTRO")


def allow_data_url(url, domain):
    """Disallow private address aliases, http URLs and cross-domain exfiltration."""
    try:
        p = urllib.parse.urlsplit(str(url))
        h = (p.hostname or "").lower()
        return (p.scheme == "https" and p.port in (None, 443)
                and not p.username and not p.password
                and (h == domain or h.endswith("." + domain))
                and not p.fragment)
    except ValueError:
        return False


class SafeSameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlsplit(req.full_url)
        nxt = urllib.parse.urlsplit(newurl)
        if old.hostname != nxt.hostname or not allow_data_url(newurl, old.hostname):
            raise ValueError("official_source_redirect_disallowed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def get_bytes(url, domain, max_bytes=MAX_BYTES):
    if not allow_data_url(url, domain):
        raise ValueError("outside_official_domain")
    accept = ("application/vnd.sdmx.genericdata+xml;version=2.1"
              if domain == "esploradati.istat.it" else
              "application/json" if "/api/3/action/" in url else
              "text/csv,application/octet-stream;q=0.5")
    req = urllib.request.Request(url, headers={
        "User-Agent": "PULSE-Italia-Autoresearch/1.0",
        "Accept": accept,
    })
    opener = urllib.request.build_opener(SafeSameHostRedirect)
    with opener.open(req, timeout=27) as reply:
        if reply.status != 200:
            raise ValueError("official_http_status_not_200")
        blob = reply.read(max_bytes + 1)
        if len(blob) > max_bytes:
            raise ValueError("official_resource_above_limit")
        return blob


def get_ckan(url, fetch_fn=get_bytes):
    blob = fetch_fn(url, "opendata.inps.it")
    payload = json.loads(blob)
    if payload.get("success") is not True or "result" not in payload:
        raise ValueError("invalid_INPS_ckan_response")
    return payload["result"]


def latest_inps_package_ids(fetch_fn=get_bytes, catalog=None, limit=6):
    """Use the INPS documented package_list; choose current-looking dataset IDs.

    This is discovery of candidate IDs, not a claim they contain usable figures.
    """
    slugs = (catalog if catalog is not None
             else get_ckan(INPS_API + "package_list", fetch_fn))
    if not isinstance(slugs, list):
        raise ValueError("invalid_INPS_dataset_catalog")
    # Favor recent time-labelled datasets, then diverse topics. A CKAN dataset
    # slug can be old; package_show metadata is authoritative.
    def score(name):
        s = str(name).lower()
        years = [int(y) for y in re.findall(r"20\d{2}", s)]
        yr = max(years) if years else 0
        interest = any(word in s for word in TOPIC_WORDS)
        return (int(interest), min(yr, date.today().year), s)
    ranked = sorted({x for x in slugs if isinstance(x, str) and
                     re.fullmatch(r"[a-zA-Z0-9_-]{3,150}", x)},
                    key=score, reverse=True)
    # When dataset IDs exist but no topical search succeeds, use the freshest
    # identifiers rather than pretending there are no official datasets.
    return ranked[:max(0, min(int(limit), 6))]


def valid_raw_number(value):
    try:
        return editorial.parse_numeric(value)
    except (TypeError, ValueError):
        return None


def explicit_unit(row, value_column):
    """Require a unit explicitly present in a header or a source row."""
    for k, value in row.items():
        name = str(k or "").casefold()
        if any(s in name for s in ("unità", "unita_misura", "unità_di_misura", "unit_of_measure")):
            if str(value).strip() in {"%", "percentuale", "euro", "EUR", "numero", "n.", "persone"}:
                return k, str(value).strip()
    title = str(value_column).casefold()
    if "%" in title or "percentual" in title:
        return None, "%"
    if "numero" in title or " n." in title:
        return None, "numero"
    return None, None


def explicit_territory(row):
    """Return original geographical dimension column only when it says Italy."""
    for k, v in row.items():
        norm = re.sub(r"[^a-z]", "", str(k or "").casefold())
        if norm in ("territorio", "area", "areageografica", "ripartizione", "regione", "refarea"):
            if str(v or "").strip().casefold() in {"italia", "it", "nazionale", "totale italia"}:
                return k, str(v)
    return None, None


def explicit_population(row, package):
    for k, v in row.items():
        norm = re.sub(r"[^a-z]", "", str(k or "").casefold())
        if norm in ("popolazione", "classeeta", "fasciaeta", "fasciadieta",
                    "categoria", "tipologiaprestazione", "tipoprestazione"):
            if 2 <= len(str(v or "").strip()) <= 150:
                return k, str(v)
    # The official dataset title labels the population without inventing
    # a numerical denominator. This remains an explicitly labelled proxy.
    title = str(package.get("title") or "").strip()
    return (None, title[:180]) if title else (None, None)


def find_year_column(row):
    for k in row:
        norm = re.sub(r"[^a-z]", "", str(k or "").casefold())
        if norm in ("anno", "annoriferimento", "annocompetenza", "year",
                    "periodo", "periododiriferimento", "timeperiod"):
            return k
    return None


ITALIAN_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}

def find_month_column(row):
    for k in row:
        norm = re.sub(r"[^a-z]", "", str(k or "").casefold())
        if norm in ("mese", "meseriferimento", "mesedicompetenza", "month"):
            return k
    return None


def exact_period(row, year_key, month_key):
    year = str(row.get(year_key, "")).strip()
    if PERIOD.fullmatch(year) and len(year) > 4 and not month_key:
        return year
    if not YEAR.fullmatch(year) or int(year) < 2000:
        return None
    if not month_key:
        return year
    raw_month = str(row.get(month_key, "")).strip().casefold()
    if re.fullmatch(r"(?:0?[1-9]|1[0-2])", raw_month):
        month = int(raw_month)
    else:
        month = ITALIAN_MONTHS.get(raw_month)
    if not month:
        return None
    return year + "-" + str(month).zfill(2)


def csv_evidences(raw, package, resource_url, max_series=1):
    """Extract only a classified time-series from original INPS CSV rows.

    Every claim has a source row and original source SHA. Reject ambiguous
    series rather than sum categories or silently infer shared units.
    """
    if not allow_data_url(resource_url, "inps.it"):
        return []
    try:
        rows = editorial.decode_records(raw, "csv")
    except (UnicodeError, ValueError, csv.Error):
        return []
    if not rows or len(rows) > 150000:
        return []
    first = rows[0]
    period_key = find_year_column(first)
    month_key = find_month_column(first)
    geo_key, geo_value = explicit_territory(first)
    pop_key, pop_value = explicit_population(first, package)
    if not period_key or not geo_key or not pop_value:
        return []
    # Candidate measure needs an original column label declaring the unit.
    candidates = []
    for col in first:
        if col in {period_key, month_key, geo_key, pop_key} or not col:
            continue
        _, unit = explicit_unit(first, col)
        if unit:
            candidates.append((col, unit))
    if not candidates:
        return []
    result = []
    for value_key, unit in candidates[:5]:
        buckets = defaultdict(list)
        for i, row in enumerate(rows, start=2):
            if str(row.get(geo_key, "")).strip() != geo_value:
                continue
            period = exact_period(row, period_key, month_key)
            if period is None:
                continue
            val = valid_raw_number(row.get(value_key))
            if val is None:
                continue
            if unit == "%" and not (Decimal(0) <= Decimal(val) <= Decimal(100)):
                continue
            unit_k, current_unit = explicit_unit(row, value_key)
            if current_unit != unit:
                continue
            # Every classification other than time and the measure must match.
            fixed = tuple(sorted((str(k), str(v)) for k, v in row.items()
                                 if k not in {period_key, month_key, value_key} and k is not None))
            buckets[fixed].append((period, val, i, str(row[value_key])))
        # Keep only the most recent aggregate with unique comparable periods.
        options = []
        for fixed, obs in buckets.items():
            obs.sort()
            if len(obs) < 2 or len({x[0] for x in obs}) != len(obs):
                continue
            if int(obs[-1][0][:4]) < OFFICIAL_LATEST_YEAR:
                continue
            options.append((obs[-1][0], len(obs), fixed, obs))
        if not options:
            continue
        _, _, fixed, obs = max(options)
        obs = obs[-12:]
        series = {
            "indicator": str(package.get("title") or value_key)[:160] + " — " + str(value_key)[:90],
            "unit": unit, "territory": geo_value, "population": pop_value,
            "frequency": ("Mensile (anno e mese nelle righe)" if month_key
                          else "Annuale (colonna anno nella fonte)"),
            "classification_values": dict(fixed),
            "observations": [{"period": x[0], "value": x[1], "raw": x[3]} for x in obs],
        }
        evidence = {
            "schema_version": 1, "verified": True, "source_url": (
                INPS_API + "package_show?id=" + urllib.parse.quote(str(package["id"]), safe="")
            ),
            "dataset_url": resource_url, "publisher": "INPS",
            "source_sha256": sha256(raw).hexdigest(), "retrieval_mode": "https",
            "source_locations": [{"period": x[0], "source_row": x[2]} for x in obs],
            "extraction_method": "original_inps_csv_fixed_classification_rows",
            "series": series, "topic": official_topic(series["indicator"]),
            "methodology_url": package.get("url") or INPS_API + "package_show",
            "source_publication_date": package.get("metadata_modified"),
            "auto_discovered_from": INPS_API + "package_list",
            "editorial_status": "requires_human_semantic_review",
        }
        result.append(evidence)
        if len(result) >= max_series:
            break
    return result


def scan_inps(fetch_fn=get_bytes, catalog=None, limit=4):
    ids = latest_inps_package_ids(fetch_fn, catalog=catalog, limit=limit)
    found, checks = [], []
    for id_ in ids:
        try:
            pkg = get_ckan(INPS_API + "package_show?id=" +
                           urllib.parse.quote(id_, safe=""), fetch_fn)
            if not isinstance(pkg, dict) or not isinstance(pkg.get("resources"), list):
                checks.append({"provider": "INPS", "dataset": id_, "status": "invalid_metadata"})
                continue
            if "id" not in pkg:
                pkg["id"] = id_
            candidates = [r for r in pkg["resources"] if isinstance(r, dict)
                          and str(r.get("format", "")).casefold() in {"csv", "text/csv", "tsv"}
                          and allow_data_url(r.get("url"), "inps.it")]
            found_before = len(found)
            sample_columns = []
            for resource in candidates[:1]:
                url = resource["url"]
                raw = fetch_fn(url, "inps.it")
                try:
                    preview = editorial.decode_records(raw, "csv")
                    sample_columns = list(preview[0])[:12] if preview else []
                except (UnicodeError, ValueError, csv.Error):
                    sample_columns = []
                found.extend(csv_evidences(raw, pkg, url, max_series=1))
            checks.append({"provider": "INPS", "dataset": id_,
                           "csv_columns": sample_columns,
                           "csv_resources_found": len(candidates),
                           "status": "source_series_found" if len(found) > found_before
                                     else "no_safe_comparable_series"})
            if len(found) >= 2:
                break
        except (OSError, TimeoutError, ValueError, KeyError, TypeError,
                urllib.error.URLError) as exc:
            checks.append({"provider": "INPS", "dataset": id_, "status": "inaccessible_or_unsupported",
                           "error_type": type(exc).__name__})
    return found[:2], checks


def parse_sdmx(raw):
    root = ET.fromstring(raw)
    series = []
    for node in root.iter():
        if node.tag.split("}")[-1] != "Series":
            continue
        key, obs = {}, []
        for child in node:
            tag = child.tag.split("}")[-1]
            if tag == "SeriesKey":
                key = {c.attrib.get("id", ""): c.attrib.get("value", "") for c in child}
            if tag == "Obs":
                period = value = None
                for c in child:
                    k = c.tag.split("}")[-1]
                    if k == "ObsDimension":
                        period = c.attrib.get("value")
                    elif k == "ObsValue":
                        value = c.attrib.get("value")
                if period and PERIOD.fullmatch(period):
                    v = valid_raw_number(value)
                    if v is not None:
                        obs.append((period, v))
        if len(obs) >= 2:
            obs.sort()
            if len({x[0] for x in obs}) == len(obs):
                series.append({"key": key, "observations": obs})
    return series


def istat_evidence(raw, dataset, url):
    """Verify matched official SDMX series with full dimensional provenance."""
    if not allow_data_url(url, "esploradati.istat.it"):
        return None
    unit = "%" if dataset["name"] in ISTAT_RATE_NAMES else None
    if not unit:
        return None  # No unit inference from raw magnitudes.
    required = dataset.get("required") or {}
    options = [s for s in parse_sdmx(raw)
               if all(s["key"].get(k) == v for k, v in required.items())]
    if not options:
        return None
    preferred = dataset.get("preferred") or {}
    # Keep deterministic and explicit selection of one source series.
    options.sort(key=lambda s: (
        sum(s["key"].get(k) == v for k, v in preferred.items()),
        s["observations"][-1][0], len(s["observations"])
    ), reverse=True)
    chosen = options[0]
    obs = chosen["observations"][-12:]
    if int(obs[-1][0][:4]) < OFFICIAL_LATEST_YEAR:
        return None
    if any(Decimal(v) < 0 or Decimal(v) > 100 for _, v in obs):
        return None
    note = str(dataset.get("note") or "").strip()
    if not note:
        return None
    return {
        "schema_version": 1, "verified": True, "source_url": url,
        "dataset_url": url, "publisher": "ISTAT",
        "source_sha256": sha256(raw).hexdigest(), "retrieval_mode": "https",
        "source_locations": [
            {"period": p, "source_row": None,
             "sdmx_series_key": chosen["key"], "sdmx_obs_dimension": p}
            for p, _ in obs
        ],
        "extraction_method": "sdmx_original_XML_series_key_and_observation",
        "series": {
            "indicator": dataset["name"], "unit": unit, "territory": "Italia",
            "population": note, "frequency": {"M": "Mensile", "A": "Annuale",
                "Q": "Trimestrale"}.get(chosen["key"].get("FREQ"), "Frequenza dichiarata da ISTAT"),
            "classification_values": chosen["key"],
            "observations": [{"period": p, "value": v, "raw": v} for p, v in obs],
        },
        "topic": official_topic(dataset["name"]),
        "methodology_url": "https://www.istat.it/classificazioni-e-strumenti/web-services-sdmx/",
        "auto_discovered_from": "PULSE_curated_ISTATData_dataflows",
        "editorial_status": "requires_human_semantic_review",
    }


def scan_istat(fetch_fn=get_bytes, today=None, datasets=None, limit=1):
    # Reuse the current repository's official dataflow registry. The existing
    # PULSE daily update already probes these same flows with a rate limiter.
    if datasets is None:
        from scripts.generate_sdmx_events import DATASETS as datasets
    eligible = [x for x in datasets if x.get("name") in ISTAT_RATE_NAMES and
                x.get("required", {}).get("REF_AREA") == "IT"]
    if not eligible:
        return [], []
    day = today or date.today()
    idx = day.toordinal() % len(eligible)
    selected = [eligible[(idx + offset) % len(eligible)]
                for offset in range(max(0, min(limit, 1)))]
    found, checks = [], []
    for d in selected:
        url = (ISTAT_SDMX + "IT1," + urllib.parse.quote(d["flow"], safe="_") +
               "/all?startPeriod=" + urllib.parse.quote(d.get("start", "2024"), safe=""))
        try:
            raw = fetch_fn(url, "esploradati.istat.it")
            e = istat_evidence(raw, d, url)
            if e:
                found.append(e)
            checks.append({"provider": "ISTAT", "dataset": d["name"],
                           "status": "source_series_found" if e else "not_comparable_or_not_available"})
        except (OSError, TimeoutError, ValueError, ET.ParseError,
                urllib.error.URLError) as exc:
            checks.append({"provider": "ISTAT", "dataset": d["name"],
                           "status": "inaccessible_or_unsupported", "error_type": type(exc).__name__})
    return found, checks


def discover(fetch_fn=get_bytes, inps_catalog=None, istat_datasets=None, today=None,
             max_sources=3):
    """One bounded pass; returns evidence and audit report, never fake articles."""
    sources, checks = [], []
    try:
        new, report = scan_istat(fetch_fn=fetch_fn, today=today,
                                 datasets=istat_datasets, limit=1)
        sources.extend(new); checks.extend(report)
    except (ImportError, OSError, ValueError, TypeError) as exc:
        checks.append({"provider": "ISTAT", "status": "unavailable",
                       "error_type": type(exc).__name__})
    try:
        new, report = scan_inps(fetch_fn=fetch_fn, catalog=inps_catalog, limit=3)
        sources.extend(new); checks.extend(report)
    except (OSError, ValueError, TypeError, KeyError, urllib.error.URLError) as exc:
        checks.append({"provider": "INPS", "status": "unavailable",
                       "error_type": type(exc).__name__})
    # avoid producing identical stories each run for an unchanged observation
    unique = {}
    for ev in sources:
        s = ev["series"]
        identity = (ev["dataset_url"], s["indicator"], s["territory"],
                    s["observations"][-1]["period"], ev["source_sha256"])
        unique[identity] = ev
    return list(unique.values())[:max_sources], {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "italian_primary_sources_only": True,
        "sources_considered": checks, "verified_series_found": len(unique),
        "note": "A valid series is a data candidate, NOT an approved article.",
    }


def save_evidences(items, root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for ev in items:
        key = (ev["dataset_url"] + "|" + ev["series"]["indicator"] + "|" +
               ev["series"]["observations"][-1]["period"] +
               ev["source_sha256"]).encode()
        slug = sha256(key).hexdigest()[:16]
        dest = root / (slug + ".evidence.json")
        editorial.write_json(dest, ev)
        paths.append(str(dest))
    return paths
