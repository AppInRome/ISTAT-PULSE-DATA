#!/usr/bin/env python3
"""Optional open-source reading / dataset / document adapters for PULSE.

Trafilatura (Apache-2.0) runs for public HTML extraction.
Docling (MIT) runs only when explicitly enabled in resource-rich environments.
opensdmx (MIT) is query-only with explicit dataset and filters; no guessed IDs.
The default job stays lightweight and uses the existing checked table extractors.
"""
from __future__ import annotations
import json
import os
from urllib.parse import urlsplit


def read_news_html(html, source_url):
    """Only return a short internal research context, never republication copy."""
    text = ""
    title = ""
    try:
        import trafilatura
        extracted = trafilatura.bare_extraction(
            html.decode("utf-8", "replace") if isinstance(html, bytes) else str(html),
            url=source_url, include_comments=False, include_tables=False)
        if extracted:
            obj = extracted.as_dict() if hasattr(extracted, "as_dict") else extracted
            if isinstance(obj, dict):
                text = str(obj.get("text") or "")
                title = str(obj.get("title") or "")
    except (ImportError, ValueError, TypeError, AttributeError):
        pass
    return {"title": title[:250], "research_context": text[:16000],
            "source_url": source_url, "republish_allowed": False}


def docling_research_text(path):
    """Document understanding needs optional CPU-intensive models."""
    if os.environ.get("PULSE_DOCLING_ENABLED") != "1":
        return {"status": "disabled", "text": ""}
    try:
        from docling.document_converter import DocumentConverter
        result = DocumentConverter().convert(str(path))
        return {"status": "parsed", "text": result.document.export_to_markdown()[:32000]}
    except ImportError:
        return {"status": "dependency_unavailable", "text": ""}
    except (RuntimeError, ValueError, OSError):
        return {"status": "parse_failed", "text": ""}


def opensdmx_exact_query(provider, dataset, filters, *, last_n=8):
    """Explicit dimensions only; never request unfiltered national datasets."""
    if provider not in ("istat", "eurostat"):
        raise ValueError("provider_not_allowed")
    if not dataset or len(dataset) > 100 or not isinstance(filters, dict) or not filters:
        raise ValueError("exact_dataset_filters_required")
    if len(filters) > 12 or any(not isinstance(k, str) or not isinstance(v, str)
                               or not k or not v or v in (".", "*")
                               for k, v in filters.items()):
        raise ValueError("ambiguous_or_unbounded_filters")
    if not 2 <= last_n <= 12:
        raise ValueError("invalid_observation_limit")
    try:
        import opensdmx
    except ImportError:
        return {"status": "dependency_unavailable", "rows": []}
    opensdmx.set_provider(provider)
    try:
        rows = opensdmx.fetch(dataset, last_n_observations=last_n, **filters)
        material = rows.to_dicts() if hasattr(rows, "to_dicts") else rows.to_dict("records")
        return {"status": "raw_unverified", "provider": provider, "dataset": dataset,
                "filters": filters, "rows": material[:last_n]}
    except Exception as exc:
        return {"status": "provider_failed", "reason": type(exc).__name__, "rows": []}


def vega_lite_from_verified_spec(chart):
    """Portable declarative visualization based only on the published chart_spec."""
    if not isinstance(chart, dict) or chart.get("status") != "verified":
        return None
    unit = chart.get("unit")
    url = chart.get("source_url")
    points = chart.get("data") or []
    if not unit or not isinstance(url, str) or not url.startswith("https://") or not points:
        return None
    values = []
    for point in points[:30]:
        try:
            label = str(point["period"])[:64]
            value = float(point["value"])
            if value != value or abs(value) == float("inf"):
                return None
        except (ValueError, TypeError, KeyError):
            return None
        values.append({"period": label, "value": value})
    mark = "line" if chart.get("type") == "line" and len(values) >= 3 else "bar"
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "PULSE - grafico da fonte primaria verificata",
        "title": str(chart.get("title") or "Indicatore")[:140],
        "width": "container", "height": 240,
        "data": {"values": values},
        "mark": {"type": mark, "point": mark == "line", "tooltip": True, "color": "#BD1731"},
        "encoding": {
            "x": {"field": "period", "type": "ordinal", "title": "Periodo"},
            "y": {"field": "value", "type": "quantitative", "title": str(unit)[:40],
                  "scale": {"zero": True} if mark == "bar" else {"zero": False}}
        },
        "usermeta": {"source_url": url, "status": "verified"}
    }
