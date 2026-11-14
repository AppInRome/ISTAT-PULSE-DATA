"""Independent PULSE editorial arithmetic and publication gate (stdlib only).

Rechecks numerical claims from evidence snapshots, not from model-supplied
'approved' claims. Semantic truth still requires a human editorial review.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

NUMBER = re.compile(r"(?<![\w])(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?![\w])")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý«\"])" )
BANNED = ("pulse analizza il dato", "perché è su pulse", "dati quantitativi citati",
          "analisi statistica pulse", "non sono disponibili", "come intelligenza artificiale")


def canonical(payload):
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(payload):
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def decimal_value(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid_numeric_value") from exc
    if not number.is_finite():
        raise ValueError("non_finite_value")
    return number


def nfmt(value):
    return format(decimal_value(value).normalize(), "f")


def variations(evidence):
    """Recompute independent facts; percent levels and relative changes differ."""
    entries = evidence["series"]["observations"]
    output = [{"kind": "observed", "period": str(row["period"]),
               "value": nfmt(row["value"]), "unit": evidence["series"]["unit"]}
              for row in entries]
    for a, b in zip(entries, entries[1:]):
        x, y = decimal_value(a["value"]), decimal_value(b["value"])
        difference = y - x
        output.append({"kind":"absolute_difference", "from":a["period"],
                       "to":b["period"], "value":nfmt(difference),
                       "unit":"punti percentuali" if evidence["series"]["unit"] == "%"
                       else evidence["series"]["unit"]})
        if x != 0:
            output.append({"kind":"relative_change", "from":a["period"],
                           "to":b["period"], "value":nfmt((difference / abs(x) * 100).quantize(Decimal("0.01"))),
                           "unit":"%"})
    return output


def normalized_number(raw):
    raw = raw.strip().replace("\u00a0", "")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", raw):
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        return nfmt(raw)
    except ValueError:
        return None


def supported_numbers(evidence):
    allowed = set()
    for row in variations(evidence):
        val = decimal_value(row["value"])
        allowed.add(nfmt(val))
        allowed.add(nfmt(abs(val)))
        # Published figures may be rounded to 0, 1, or 2 decimals.
        for digits in (0, 1, 2):
            quantum = Decimal("1").scaleb(-digits)
            for x in (val, abs(val)):
                allowed.add(nfmt(x.quantize(quantum)))
        for period_key in ("period", "from", "to"):
            if period_key in row:
                for found in NUMBER.findall(str(row[period_key])):
                    normalized = normalized_number(found)
                    if normalized is not None:
                        allowed.add(normalized)
    return allowed


def audit(draft, evidence):
    issues = []
    if not isinstance(draft, dict) or not isinstance(evidence, dict):
        return {"passed": False, "issues": ["invalid_payload"]}
    if draft.get("evidence_sha256") != digest(evidence):
        issues.append("evidence_hash_mismatch")
    if evidence.get("verified") is not True or len(evidence.get("series",{}).get("observations", [])) < 2:
        issues.append("no_verified_series")
    title = draft.get("title", "")
    lead = draft.get("lead", "")
    paragraphs = draft.get("paragraphs", [])
    if not isinstance(title, str) or not 20 <= len(title) <= 160:
        issues.append("headline_invalid")
    if not isinstance(lead, str) or len(lead.split()) < 20:
        issues.append("lead_too_short")
    if not isinstance(paragraphs, list) or not (4 <= len(paragraphs) <= 6) or not all(isinstance(p, str) for p in paragraphs):
        issues.append("paragraph_structure")
        paragraphs = []
    combined = " ".join([title, lead, *paragraphs])
    sentences = [s.strip() for s in SENTENCE.split(" ".join([lead, *paragraphs])) if s.strip()]
    # Simple Italian sentence count; ellipses and abbreviations can be reviewed manually.
    if not 15 <= len(sentences) <= 25:
        issues.append(f"sentence_count_{len(sentences)}")
    words = len(re.findall(r"\b[\wÀ-ÿ]+\b", " ".join([lead, *paragraphs])))
    if not 250 <= words <= 500:
        issues.append(f"word_count_{words}")
    if any(bad in combined.casefold() for bad in BANNED):
        issues.append("template_or_boilerplate")
    if len({re.sub(r"\s+", " ", p.casefold()).strip() for p in paragraphs}) != len(paragraphs):
        issues.append("duplicate_paragraphs")
    try:
        allowed = supported_numbers(evidence)
    except (KeyError, TypeError, ValueError):
        allowed = set()
        issues.append("invalid_evidence")
    unsupported = sorted(set(x for token in NUMBER.findall(combined)
                             if (x := normalized_number(token)) not in allowed))
    if unsupported:
        issues.append("unsupported_numeric_tokens:" + ",".join(unsupported[:20]))
    # When an AI writes 'X punti percentuali', the number must be a verified
    # absolute percentage-point change, not merely an observed percentage.
    pp_values = set()
    percent_values = set()
    relative_values = set()
    for fact in variations(evidence):
        v = decimal_value(fact["value"])
        candidates = set()
        for precision in (0, 1, 2):
            q = Decimal("1").scaleb(-precision)
            candidates.add(nfmt(abs(v).quantize(q)))
        if fact["kind"] == "absolute_difference" and fact["unit"] == "punti percentuali":
            pp_values.update(candidates)
        if fact["kind"] == "observed" and fact["unit"] == "%":
            percent_values.update(candidates)
        if fact["kind"] == "relative_change":
            relative_values.update(candidates)
    for m in NUMBER.finditer(combined):
        number = normalized_number(m.group())
        following = combined[m.end():m.end()+40].casefold().lstrip()
        preceding = combined[max(0,m.start()-35):m.start()].casefold()
        if following.startswith("punti percentuali") or following.startswith("punto percentuale"):
            if number not in pp_values:
                issues.append("unverified_percentage_point_change:"+str(number))
        elif following.startswith("%") and ("aument" in preceding or "diminui" in preceding or "variazion" in preceding or "crescit" in preceding):
            if number not in relative_values:
                issues.append("unverified_relative_percentage_change:"+str(number))
        elif following.startswith("%") and number not in percent_values | relative_values:
            issues.append("percentage_without_observation_or_relative_change:"+str(number))
    if not draft.get("source_url") == evidence.get("source_url"):
        issues.append("primary_source_changed")
    if not draft.get("dataset_url") == evidence.get("dataset_url"):
        issues.append("dataset_source_changed")
    return {"passed": not issues, "issues": issues, "sentence_count":len(sentences),
            "word_count":words, "facts_checked": len(variations(evidence)) if allowed else 0,
            "warning":"Numeric token verification is necessary but does not prove causal or semantic accuracy; human approval required."}
