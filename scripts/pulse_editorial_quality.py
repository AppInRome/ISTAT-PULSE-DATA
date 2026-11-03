"""PULSE editorial quality: deterministic red flags, not a substitute for a human editor."""
from __future__ import annotations
import re
from difflib import SequenceMatcher

FORMULAIC = (
    "il dato più recente disponibile",
    "il grafico e la tabella associati",
    "non è una stima ricavata dal titolo",
    "per stabilire se il cambiamento sia rilevante",
    "non vengono aggiunte stime né valori estrapolati",
    "la serie qui utilizzata contiene",
)
WORDS = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
NUMBERS = re.compile(r"(?<!\w)\d+(?:[.,]\d+)?")
def _normalize(text):
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()

def assess_story(headline, lead, paragraphs, chart_data=None):
    """Returns structured signals. Never fabricates a quality score or verifies truth."""
    faults = []
    body = [_normalize(p) for p in paragraphs if isinstance(p, str)]
    if len(body) < 5:
        faults.append("few_paragraphs")
    if len(WORDS.findall(" ".join(body))) < 350:
        faults.append("insufficient_substantive_length")
    if len(WORDS.findall(lead or "")) < 15:
        faults.append("weak_lead")
    if len(WORDS.findall(headline or "")) < 5:
        faults.append("generic_headline")
    for phrase in FORMULAIC:
        if sum(phrase in p for p in body) >= 1:
            faults.append("boilerplate:" + phrase)
    for i, paragraph in enumerate(body):
        if len(WORDS.findall(paragraph)) < 40:
            faults.append("short_paragraph:" + str(i))
        for previous in body[:i]:
            if SequenceMatcher(None, paragraph, previous).ratio() > 0.78:
                faults.append("near_duplicate_paragraphs")
                break
    evidence = []
    for point in chart_data or []:
        try:
            n = float(point["value"])
            if n.is_integer():
                evidence.append(str(int(n)))
            evidence.append(("%g" % n).replace(".", ","))
        except (KeyError, TypeError, ValueError):
            continue
    # Require at least one of the actual published values in the text.
    # This is a cross-reference check, not independent primary verification.
    if evidence and not any(re.search(r"(?<![0-9])" + re.escape(n) + r"(?![0-9])", " ".join(body+[lead or ""])) for n in evidence):
        faults.append("text_omits_chart_values")
    return {"editorial_quality_version": 1, "passed": not faults, "issues": list(dict.fromkeys(faults))}
