#!/usr/bin/env python3
"""PULSE evidence-constrained AI copy editor (optional, never invent data).

Compatible with local Ollama/OpenAI-style chat completions and HTTPS providers.
Use only when explicit credentials/model endpoint are configured; otherwise
retain deterministic, source-grounded copy.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_MODEL_CALLS = 2
_used = 0
NUMBER = re.compile(r"(?<![\w])(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+|\.\d+)?(?![\w])")


def _supported_number_tokens(article):
    tokens = set()
    chart = article.get("chart_spec") or {}
    values = []
    for row in chart.get("data") or []:
        try:
            v = float(row["value"])
            period = str(row["period"])
        except (ValueError, TypeError, KeyError):
            continue
        if math.isfinite(v):
            values.append(v)
            tokens.update((str(v), str(v).replace(".", ","), str(int(v)) if v.is_integer() else ""))
        tokens.add(period)
    for x, y in zip(values, values[1:]):
        diff = abs(y-x)
        tokens.add(f"{diff:.2f}".rstrip("0").rstrip("."))
        tokens.add(f"{diff:.2f}".rstrip("0").rstrip(".").replace(".", ","))
        if x != 0:
            relative = abs(100*(y-x)/x)
            for digits in (0,1,2):
                tokens.add(f"{relative:.{digits}f}".replace(".", ","))
    return {x for x in tokens if x}


def validate_ai_copy(article, proposed):
    """Require source-backed numbers and substantial, individual prose."""
    if not isinstance(proposed, dict):
        return False
    title = str(proposed.get("title") or "")
    lead = str(proposed.get("lead") or "")
    paragraphs = proposed.get("paragraphs")
    if not (22 <= len(title) <= 190 and len(lead) >= 90
            and isinstance(paragraphs, list) and 5 <= len(paragraphs) <= 9):
        return False
    if any(not isinstance(p, str) or len(p.split()) < 48 for p in paragraphs):
        return False
    text = " ".join([title,lead]+paragraphs)
    if len(text.split()) < 370:
        return False
    allowed = _supported_number_tokens(article)
    for matched in NUMBER.findall(text):
        if matched not in allowed:
            # Never permit an undisclosed number, even when plausible.
            return False
    try:
        from scripts.pulse_editorial_quality import assess_story
    except ModuleNotFoundError:
        from pulse_editorial_quality import assess_story
    return assess_story(title, lead, paragraphs,
                        (article.get("chart_spec") or {}).get("data", []))["passed"]


def attempt_ai_edition(article):
    global _used
    endpoint = os.environ.get("PULSE_LLM_ENDPOINT", "").strip()
    model = os.environ.get("PULSE_LLM_MODEL", "").strip()
    key = os.environ.get("PULSE_LLM_API_KEY", "").strip()
    if not endpoint or not model or _used >= MAX_MODEL_CALLS:
        return article
    parsed = urlsplit(endpoint)
    # Non-HTTPS endpoints are allowed only for a local Ollama server.
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in ("localhost","127.0.0.1")
    ):
        return article
    if parsed.username or parsed.password or not parsed.hostname:
        return article
    primary = article.get("public_source") or {}
    if (primary.get("role") != "primary_statistical_source"
            or article.get("verification_tier") != "verified_comparable_series"):
        return article
    chart = article.get("chart_spec") or {}
    if chart.get("status") != "verified" or len(chart.get("data") or []) < 2:
        return article
    _used += 1
    facts = {
        "indicator": chart.get("title"), "unit": chart.get("unit"),
        "observations": chart["data"], "source_url": chart.get("source_url"),
        "topic": article.get("topic"), "territories": article.get("territories"),
        "discovery_headline": article.get("original_discovery_headline")
    }
    prompt = (
        "Scrivi in italiano un articolo giornalistico originale per PULSE. "
        "Hai ESCLUSIVAMENTE questi dati verificati: " +
        json.dumps(facts, ensure_ascii=False) +
        ". Ritorna SOLO JSON {title, lead, paragraphs}. "
        "Paragrafi: 5-9, almeno 48 parole ciascuno, totale almeno 370 parole. "
        "Racconta il fatto, il contesto verificabile, il confronto, limiti e "
        "significato del dato, con linguaggio vivo e non ripetitivo. "
        "Non aggiungere alcuna nuova cifra, anno, percentuale, citazione, "
        "causa o fonte non presente nelle osservazioni. Non copiare il testo "
        "di una testata e non inventare dichiarazioni. "
        "Le parole devono essere tue, le cifre ESCLUSIVAMENTE dai dati forniti."
    )
    body = {
        "model": model, "temperature": 0.35, "max_tokens": 2200,
        "messages": [{"role": "system", "content": "Sei un giornalista statistico che non inventa dati."},
                     {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        req = Request(endpoint, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urlopen(req, timeout=35) as response:
            if response.status != 200:
                return article
            payload = json.loads(response.read(220_000))
        text = payload["choices"][0]["message"]["content"]
        proposed = json.loads(text)
        if not validate_ai_copy(article, proposed):
            return article
        revised = dict(article)
        revised["headline"] = revised["pulse_title"] = proposed["title"]
        revised["summary"] = revised["pulse_summary"] = proposed["lead"]
        revised["pulse_article_body"] = [{"heading": "", "text": p} for p in proposed["paragraphs"]]
        revised["editorial_format"] = "ai_assisted_evidence_checked"
        revised["editorial_review"] = {"automatic_numeric_validation": True,
                                      "human_editorial_review": False}
        return revised
    except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError):
        return article
