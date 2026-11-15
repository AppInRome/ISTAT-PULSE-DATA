#!/usr/bin/env python3
"""PULSE Luna: source-locked AI editing, independent arithmetic gate, safe fallback.

Runs on GitHub Actions, never on Android. No daily article cap. All graphs/tables
remain sourced from the original audited deterministic PULSE feed.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo
import argparse
import json
import os
import re

MODEL = "gpt-6-luna"
BUDGET_USD = Decimal("4.00")
RESERVE_PER_CALL = Decimal("0.005")
PRICE_INPUT = Decimal("0.10") / Decimal("1000000")
PRICE_OUTPUT = Decimal("0.50") / Decimal("1000000")
SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"title": {"type": "string"}, "lead": {"type": "string"},
                         "paragraphs": {"type": "array", "items": {"type": "string"},
                                        "minItems": 4, "maxItems": 6}},
          "required": ["title", "lead", "paragraphs"]}
PROMPT = (
    "Sei il redattore PULSE. Scrivi un articolo statistico ORIGINALISSIMO, "
    "italiano naturale, completo, accurato: titolo, sommario e 4-6 paragrafi, "
    "250-450 parole totali. Usa SOLO il dossier, che contiene TUTTE le "
    "osservazioni disponibili. Non inventare fatti, cause, fonti, percentuali, "
    "citazioni o anni mancanti; non confondere anno di riferimento e data di "
    "pubblicazione. La quota 73,7% è INFERIORE a 73,9%, non superiore. "
    "Calcola con attenzione direzione e differenze; tra due percentuali le "
    "differenze sono punti percentuali. Non scrivere record/massimo se un anno "
    "diverso ha un valore maggiore nella serie completa. Se i dati sono "
    "un'analisi di contesto, non presentarla come nuova uscita dell'ente. "
    "Evita ripetizioni e linguaggio burocratico. Grafici e tabelle saranno "
    "generati dal sistema PULSE fuori dall'AI. Restituisci solo il JSON."
)

def load(path, default=None):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

def save(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(p)

def eligible(a):
    r = a.get("automatic_review") or {}
    docs = a.get("source_documents") or []
    series = a.get("verified_series_relevant") or []
    return (
        a.get("publication_status") == "published"
        and a.get("editorial_format") == "deterministic_source_locked_auto_audited"
        and a.get("publication_tier") in
            ("verified_official_deterministic", "verified_official_context_not_new_release")
        and (a.get("public_source") or {}).get("role") == "primary_statistical_source"
        and r.get("passed") is True and r.get("model_used") is False
        and re.fullmatch("[a-fA-F0-9]{64}", str(r.get("evidence_sha256", ""))) is not None
        and bool(docs) and r.get("original_source_sha256") == docs[0].get("sha256")
        and bool(series) and all(s.get("verified") and 2 <= len(s.get("observations") or []) <= 24
                                 for s in series)
    )

def dossier(a):
    return {
        "id": a["id"], "topic": a.get("topic"), "reference_period": a.get("period_reference"),
        "editorial_kind": a.get("editorial_kind"),
        "context_notice": a.get("editorial_context_notice"),
        "source_url": (a.get("public_source") or {}).get("url"),
        "full_verified_series": [
            {"indicator": s.get("indicator"), "population": s.get("population"),
             "territory": s.get("territory"), "unit": s.get("unit"),
             "observations": [{"period": o["period"], "value": o["value"]}
                              for o in s["observations"]]}
            for s in a["verified_series_relevant"]
        ]
    }

def allowed_numbers(a):
    periods, numbers = set(), set()
    for s in a["verified_series_relevant"]:
        values = []
        for o in s["observations"]:
            period = str(o["period"])
            periods.add(period)
            if "-" in period:
                periods.update(period.split("-"))
            values.append(Decimal(str(o["value"])))
        for v in values:
            numbers.add(v)
            for unit in ("1", "0.1", "0.01", "0.001"):
                numbers.add(v.quantize(Decimal(unit)))
        for x in values:
            for y in values:
                d = abs(x-y)
                numbers.add(d)
                for unit in ("1", "0.1", "0.01", "0.001"):
                    numbers.add(d.quantize(Decimal(unit)))
    return periods, numbers

NUMBER = re.compile(r"(?<!\w)(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+|\.\d+)?(?!\w)")
def validate(a, result):
    """Conservative numerical gate; failure always falls back to non-AI copy."""
    if not isinstance(result, dict):
        return ["invalid_json"]
    title, lead, paragraphs = result.get("title"), result.get("lead"), result.get("paragraphs")
    if not isinstance(title, str) or not 25 <= len(title.strip()) <= 180:
        return ["invalid_title"]
    if not isinstance(lead, str) or not 50 <= len(lead.strip()) <= 650:
        return ["invalid_lead"]
    if not isinstance(paragraphs, list) or not 4 <= len(paragraphs) <= 6:
        return ["invalid_paragraphs"]
    if any(not isinstance(p, str) or len(p.strip()) < 80 for p in paragraphs):
        return ["short_or_invalid_paragraph"]
    content = " ".join([title, lead, *paragraphs])
    issues = []
    if not 250 <= len(content.split()) <= 500:
        issues.append("invalid_length")
    periods, numbers = allowed_numbers(a)
    for token in NUMBER.findall(content):
        if token in periods:
            continue
        if re.fullmatch(r"(?:19|20)\d\d", token):
            issues.append("unknown_reference_year")
            continue
        try:
            value = Decimal(token.replace(".", "").replace(",", ".") if "," in token else token)
        except Exception:
            issues.append("bad_number")
            continue
        if value not in numbers:
            issues.append("unsupported_number")
    # Reject obvious reversed comparisons, including the error in the user's
    # 2025 self-rated-health test. Only evaluate unambiguous two-year assertions.
    for s in a["verified_series_relevant"]:
        obs = s["observations"]
        latest = str(obs[-1]["period"])
        vals = {str(o["period"]): Decimal(str(o["value"])) for o in obs}
        last = vals[latest]
        for sentence in re.split(r"(?<=[.!?])\s+", content):
            txt = sentence.casefold()
            present = [year for year in vals
                       if re.search(r"(?<!\d)" + re.escape(year) + r"(?!\d)", sentence)]
            if latest not in present:
                continue
            if last < max(vals.values()) and re.search(r"\b(record|massimo|picco)\b", txt):
                issues.append("latest_not_historical_max")
            for earlier in present:
                if earlier == latest:
                    continue
                explicit = re.search(
                    r"pi[uù]\s+(alt[oaie]|elevat[oaie]|bass[oaie])\s+"
                    r"(?:\w+\s+){0,3}(?:nel|in|al)\s+" + re.escape(latest), txt)
                if explicit:
                    higher = explicit.group(1).startswith(("alt", "elevat"))
                    if (last > vals[earlier]) != higher:
                        issues.append("reversed_comparison")
                # "nel 2025 è superiore rispetto al 2023"
                m = re.search(
                    r"(?:nel|in|al)\s+" + re.escape(latest)
                    + r".{0,150}?(superiore|inferiore)\s+(?:a|al|rispetto al|di)\s+"
                    + re.escape(earlier), txt)
                if m and (last > vals[earlier]) != (m.group(1) == "superiore"):
                    issues.append("reversed_comparison")
    return sorted(set(issues))

def generate(key, a):
    request = {
        "model": MODEL, "reasoning": {"effort": "none"}, "store": False,
        "instructions": PROMPT, "input": json.dumps(dossier(a), ensure_ascii=False),
        "text": {"format": {"type": "json_schema", "name": "pulse_luna_article",
                            "strict": True, "schema": SCHEMA}},
        "max_output_tokens": 3500
    }
    req = Request(
        "https://api.openai.com/v1/responses", method="POST",
        data=json.dumps(request).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urlopen(req, timeout=160) as resp:
        result = json.load(resp)
    usage = result.get("usage") or {}
    cost = (Decimal(str(usage.get("input_tokens", 0))) * PRICE_INPUT
            + Decimal(str(usage.get("output_tokens", 0))) * PRICE_OUTPUT)
    if result.get("status") != "completed":
        raise ValueError("incomplete_ai_response")
    body = "".join(part.get("text", "") for message in result.get("output", [])
                   if message.get("type") == "message"
                   for part in message.get("content", []) if part.get("type") == "output_text")
    if not body:
        raise ValueError("empty_ai_response")
    return json.loads(body), cost

def run(feed, ledger, status, key, budget=BUDGET_USD):
    root = load(feed)
    if not root or root.get("schema") != "pulse-automatic-official-features-v1":
        raise ValueError("unverified_official_feature_feed")
    month = datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m")
    state = load(ledger, {})
    if state.get("month") != month:
        state = {"schema": "pulse-luna-monthly-ledger-v1", "month": month,
                 "spent_usd": "0", "requests": 0, "accepted": 0}
    spent = Decimal(str(state["spent_usd"]))
    published = skipped = blocked = attempted = 0
    last_error = ""
    for a in root["articles"]:
        if not eligible(a):
            continue
        evidence = a["automatic_review"]["evidence_sha256"]
        old = a.get("luna_story") or {}
        if (old.get("schema") == "pulse-luna-story-v1" and old.get("passed")
                and old.get("source_evidence_sha256") == evidence):
            skipped += 1
            continue
        if not key:
            last_error = "missing_github_actions_secret_OPENAI_API_KEY"
            break
        if spent + RESERVE_PER_CALL > budget:
            last_error = "monthly_ai_budget_reached_original_articles_unaffected"
            break
        try:
            article, cost = generate(key, a)
            spent += cost
            attempted += 1
            state["requests"] += 1
            errors = validate(a, article)
            if errors:
                blocked += 1
                print("LUNA BLOCKED:", a["id"], ",".join(errors))
                continue
            a["luna_story"] = {
                "schema": "pulse-luna-story-v1", "model": MODEL,
                "passed": True,
                "source_evidence_sha256": evidence,
                "original_source_sha256": a["automatic_review"]["original_source_sha256"],
                "title": article["title"].strip(), "lead": article["lead"].strip(),
                "paragraphs": [p.strip() for p in article["paragraphs"]],
                "review_type": "automatic_numeric_and_provenance_audit_not_human",
                "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds")
                                .replace("+00:00", "Z")
            }
            published += 1
            state["accepted"] += 1
            print("LUNA PUBLISHED:", a["id"])
        except (HTTPError, URLError, ValueError, KeyError, TimeoutError) as exc:
            blocked += 1
            last_error = "api_or_validation_unavailable_original_unchanged"
            print("LUNA ERROR:", a["id"], type(exc).__name__)
            if isinstance(exc, HTTPError) and exc.code in (401, 402, 429):
                break
    state["spent_usd"] = str(spent)
    save(ledger, state)
    if published:
        save(feed, root)
    report = {
        "schema": "pulse-luna-status-v1", "model": MODEL,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")
                        .replace("+00:00", "Z"),
        "enabled": bool(key), "month": month,
        "month_budget_usd": float(budget), "month_spent_usd": round(float(spent), 6),
        "month_remaining_budget_usd": round(float(max(Decimal(0), budget - spent)), 6),
        "articles_ai_published_this_run": published,
        "articles_ai_skipped_unchanged": skipped,
        "articles_ai_blocked_this_run": blocked, "requests_this_run": attempted,
        "is_actual_openai_prepaid_balance": False,
        "billing_url": "https://platform.openai.com/settings/organization/billing/overview",
        "last_error": last_error
    }
    save(status, report)
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", default="data/news/automatic_features.json")
    parser.add_argument("--ledger", default="data/news/luna_ledger.json")
    parser.add_argument("--status", default="data/news/luna_status.json")
    parser.add_argument("--budget-usd", type=Decimal, default=BUDGET_USD)
    args = parser.parse_args()
    if args.budget_usd <= 0:
        parser.error("positive budget required")
    result = run(args.feed, args.ledger, args.status,
                 os.getenv("OPENAI_API_KEY", "").strip(), args.budget_usd)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
