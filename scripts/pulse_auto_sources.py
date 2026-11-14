#!/usr/bin/env python3
"""PULSE automatic Italy-only official-dataset discovery.

Finds official primary documents from existing PULSE leads, follows bounded
same-host attachment links and infers an exact-classification dataset manifest
when the *source file itself* provides indicator, geography, population, unit,
frequency, period and numeric observations. Never infers omitted metadata.
No LLM, no auto-publishing, no manual manifest authoring.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO, StringIO
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit, urlunsplit
from scripts import pulse_editorial_engine_v1 as engine
from scripts.pulse_italia_newsroom import italy_relevant, italian_official_url

MAX_CANDIDATES = 12
MAX_LINKS = 8
MAX_GROUPS_PER_FILE = 3
MAX_ROWS = 18000
NAMES = {
    "indicator": {"indicatore", "indicator", "indicator_name", "nome_indicatore", "misura", "variabile"},
    "territory": {"territorio", "territory", "area", "ripartizione", "regione"},
    "population": {"popolazione", "population", "universo", "popolazione_riferimento"},
    "unit": {"unita", "unita_misura", "unit", "unità", "unità_di_misura", "misura_unita"},
    "frequency": {"frequenza", "frequency", "periodicita", "periodicità"},
    "period": {"periodo", "period", "anno", "year", "time_period", "mese"},
    "value": {"valore", "value", "obs_value", "osservazione", "valore_osservato"},
}
ALLOWED_UNITS = {"%", "percentuale", "punti percentuali", "persone",
                 "numero", "n.", "euro", "migliaia di persone", "milioni di euro",
                 "mila euro", "m²/abitante", "km per 100 km²", "kg/abitante",
                 "tonnellate per abitante", "per 1.000 abitanti", "per 100.000 abitanti"}
FREQUENCIES = {"annuale", "mensile", "trimestrale", "yearly", "monthly", "quarterly"}


def norm(text):
    return re.sub(r"[^a-z0-9à-ÿ]+", "_", str(text or "").strip().casefold()).strip("_")


def canonical_map(fields):
    names = {norm(f): f for f in fields if isinstance(f, str)}
    chosen = {}
    for role, aliases in NAMES.items():
        found = [names[norm(x)] for x in aliases if norm(x) in names]
        if len(set(found)) != 1:
            return None
        chosen[role] = found[0]
    if len(set(chosen.values())) != 7:
        return None
    return chosen


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(str(href))


def valid_file_url(url):
    p = urlsplit(str(url or ""))
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
        return False
    return italian_official_url(url) and p.path.casefold().endswith((".csv", ".json", ".xlsx"))


def attachments(html, page):
    parser = LinkParser()
    parser.feed(html.decode("utf-8", errors="replace")[:750_000])
    origin = (urlsplit(page).hostname or "").lower()
    results = []
    for path in parser.links:
        url = urljoin(page, path).split("#")[0]
        if (urlsplit(url).hostname or "").lower() != origin:
            continue
        if valid_file_url(url) and url not in results:
            results.append(url)
        if len(results) >= MAX_LINKS:
            break
    return results


def rows_from_bytes(data, url):
    path = urlsplit(url).path.lower()
    if path.endswith(".json"):
        payload = json.loads(data)
        records = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("json_data_must_be_list")
        return records[:MAX_ROWS], "json"
    if path.endswith(".csv"):
        raw = data.decode("utf-8-sig")
        dialect = csv.Sniffer().sniff(raw[:8192], delimiters=";,\t")
        records = csv.DictReader(StringIO(raw), dialect=dialect)
        return list(r for _, r in zip(range(MAX_ROWS), records)), "csv"
    if path.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ValueError("openpyxl_required_for_xlsx") from exc
        book = load_workbook(BytesIO(data), read_only=True, data_only=True)
        if len(book.sheetnames) != 1:
            raise ValueError("multiple_sheets_ambiguous")
        try:
            ws = book.active
            rows = ws.iter_rows(values_only=True)
            header = next(rows, None)
            if not header or not all(x is not None for x in header):
                raise ValueError("missing_xlsx_header")
            fields = [str(x).strip() for x in header]
            return [dict(zip(fields, row)) for _, row in zip(range(MAX_ROWS), rows)], "xlsx"
        finally:
            book.close()
    raise ValueError("unsupported_dataset_format")


def classify(row, columns):
    vals = {role: str(row.get(field) or "").strip() for role, field in columns.items()
            if role not in {"period", "value"}}
    if not all(vals.values()):
        return None
    if vals["territory"].casefold() not in {"italia", *[x.casefold() for x in __import__(
            "scripts.pulse_italia_newsroom", fromlist=["REGIONS"]).REGIONS]}:
        return None
    if vals["unit"].casefold() not in ALLOWED_UNITS:
        return None
    if vals["frequency"].casefold() not in FREQUENCIES:
        return None
    period = str(row.get(columns["period"]) or "").strip()
    if not engine.PERIOD.fullmatch(period):
        return None
    try:
        engine.parse_numeric(row.get(columns["value"]))
    except ValueError:
        return None
    return vals


def detect_manifests(source_url, dataset_url, data, *, max_groups=MAX_GROUPS_PER_FILE):
    """Source-led grouping only. Preserve original source row, period and byte hash."""
    if not valid_file_url(dataset_url):
        return []
    if not italian_official_url(source_url):
        return []
    records, fmt = rows_from_bytes(data, dataset_url)
    if not records or not isinstance(records[0], dict):
        return []
    columns = canonical_map(list(records[0]))
    if not columns:
        return []
    groups = {}
    for row in records:
        if not isinstance(row, dict):
            continue
        vals = classify(row, columns)
        if not vals:
            continue
        grouping = tuple(vals[k] for k in ("indicator", "territory", "population", "unit", "frequency"))
        groups.setdefault(grouping, []).append(row)
    out = []
    for group, matching in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(out) >= max_groups:
            break
        if len({str(row.get(columns["period"])) for row in matching}) < 2:
            continue
        semantic = {"indicator": columns["indicator"], "territory": columns["territory"],
                    "population": columns["population"], "unit": columns["unit"],
                    "frequency": columns["frequency"]}
        dims = dict(zip((columns[r] for r in ("indicator","territory","population","unit","frequency")), group))
        manifest = {"source_url": source_url, "dataset_url": dataset_url,
                    "publisher": (urlsplit(source_url).hostname or "").removeprefix("www."),
                    "topic": "ALTRO",
                    "schema": {"format": "csv" if fmt == "xlsx" else fmt,
                               "period_column": columns["period"], "value_column": columns["value"],
                               "semantic_columns": semantic, "dimensions": dims}}
        try:
            # XLSX is converted to a deterministic CSV with original row values;
            # BOTH hashes and the conversion method are retained. This is never
            # presented as the original XLSX hash.
            if fmt == "xlsx":
                file_like = StringIO()
                writer = csv.DictWriter(file_like, fieldnames=list(columns.values()))
                writer.writeheader()
                writer.writerows({col: row.get(col) for col in columns.values()} for row in records)
                converted = file_like.getvalue().encode("utf-8")
            else:
                converted = data
            evidence = engine.extract(manifest, converted)
            if fmt == "xlsx":
                evidence["source_original_sha256"] = sha256(data).hexdigest()
                evidence["extraction_method"] = "xlsx_single_sheet_exact_cells_converted_csv"
                evidence["source_sha256"] = sha256(converted).hexdigest()
            evidence["auto_discovered"] = True
            evidence["dataset_format_original"] = fmt
            evidence["dataset_bytes_sha256"] = sha256(data).hexdigest()
            evidence["source_row_count"] = len(records)
            out.append({"manifest": manifest, "evidence": evidence})
        except (ValueError, TypeError, KeyError, csv.Error):
            continue
    return out


def discover_primary_sources(articles, *, max_stories=MAX_CANDIDATES,
                             fetch=None, search=None):
    """Auto-discover candidate official datasets; fail closed on unverifiable files."""
    if fetch is None:
        fetch = engine.fetch
    out = []
    seen = set()
    for article in articles:
        if len(out) >= max_stories:
            break
        if not italy_relevant(article):
            continue
        src = article.get("public_source") or {}
        page = src.get("url") if src.get("role") == "primary_statistical_source" else None
        urls = []
        if page and italian_official_url(page):
            urls.append(page)
        if search and not urls:
            urls.extend(search(article))
        for url in urls[:2]:
            if not italian_official_url(url):
                continue
            if url in seen:
                continue
            seen.add(url)
            try:
                if valid_file_url(url):
                    targets = [url]
                else:
                    page_bytes = fetch(url)
                    targets = attachments(page_bytes, url)
                for dataset_url in targets[:MAX_LINKS]:
                    data = fetch(dataset_url)
                    for item in detect_manifests(url, dataset_url, data):
                        id_value = sha256((dataset_url + json.dumps(item["manifest"]["schema"],
                                      sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:18]
                        out.append({"source_article_id": article.get("id"),
                                    "candidate_id": id_value, **item})
                        if len(out) >= max_stories:
                            break
                    if len(out) >= max_stories:
                        break
            except (ValueError, TypeError, KeyError, OSError, TimeoutError,
                    UnicodeError, csv.Error):
                continue
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Find official Italian datasets automatically")
    p.add_argument("--news", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--limit", type=int, default=12)
    a = p.parse_args(argv)
    articles = json.loads(Path(a.news).read_text(encoding="utf-8"))["articles"]
    articles.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)
    out_dir = Path(a.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    found = discover_primary_sources(articles, max_stories=max(1, min(a.limit, 20)))
    manifest_dir = out_dir / "manifests"
    evidence_dir = out_dir / "evidence"
    manifest_dir.mkdir(exist_ok=True)
    evidence_dir.mkdir(exist_ok=True)
    for item in found:
        id_value = item["candidate_id"]
        (manifest_dir / (id_value + ".json")).write_text(json.dumps(
            item["manifest"], indent=2, ensure_ascii=False), encoding="utf-8")
        (evidence_dir / (id_value + ".json")).write_text(json.dumps(
            item["evidence"], indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {"status": "official_datasets_only", "timestamp": datetime.now(timezone.utc).isoformat(),
               "found": len(found), "articles_reviewed": min(len(articles), max(1, min(a.limit, 20))),
               "manifest_dir": str(manifest_dir), "evidence_dir": str(evidence_dir),
               "automatic_publication": False}
    (out_dir / "discovery_status.json").write_text(json.dumps(
        summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
