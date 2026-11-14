#!/usr/bin/env python3
"""Display-only Italian news headlines for VERIFIED deterministic PULSE features.

No AI, scraping or rewriting the original article. This adapter changes only
'headline' and 'pulse_title' on copies of ALREADY audited published records.
Everything else (text, summary, source, timestamps, numeric evidence, graphs
and table) is left byte-for-byte equivalent as JSON values.
Editorial guidance: Google Search title-link advice and Google News <=110 chars.
"""
from __future__ import annotations

from datetime import date
import math
import re

MONTHS_IT = (
    "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)
MAX_HEADLINE_CHARS = 110
MONTHLY = re.compile(r"^((?:19|20)\d{2})-(0[1-9]|1[0-2])$")
ANNUAL = re.compile(r"^(?:19|20)\d{2}$")
ALLOWED_MEASURES = {
    "numero_lavoratori": ("i lavoratori rilevati", "aumentano i lavoratori rilevati",
                           "calano i lavoratori rilevati", "lavoratori rilevati stabili"),
    "numero_domande": ("le domande rilevate", "aumentano le domande rilevate",
                       "calano le domande rilevate", "domande rilevate stabili"),
    "numero_mensilita": ("le mensilità rilevate", "aumentano le mensilità rilevate",
                         "calano le mensilità rilevate", "mensilità rilevate stabili"),
}


def clean_human_territory(value):
    """Do not invent an area from the body, links, user address, or publication date."""
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not re.fullmatch(r"[\w\sÀ-ÿ'’.-]{2,55}", raw, flags=re.UNICODE):
        return ""
    return raw.lower().title().replace(" D'", " d'").replace(" D’", " d’")


def _verified_measure(article):
    if not isinstance(article, dict):
        return None
    if article.get("editorial_format") != "deterministic_source_locked_auto_audited":
        return None
    if article.get("publication_status") != "published":
        return None
    verification = article.get("automatic_review")
    if not isinstance(verification, dict) or verification.get("passed") is not True:
        return None
    if verification.get("model_used") is not False:
        return None
    source = article.get("public_source") or {}
    if source.get("role") != "primary_statistical_source":
        return None
    if str(source.get("domain", "")).upper() != "INPS":
        return None
    records = article.get("verified_series_relevant") or []
    if len(records) != 1 or not isinstance(records[0], dict):
        return None
    s = records[0]
    indicator = re.sub(r"\s+", " ", str(s.get("indicator", ""))).strip()
    if not indicator.casefold().startswith("integrazioni salariali "):
        return None
    # Require an explicit column name; do not confuse workers, applications,
    # months, or hypothetical benefits.
    m = re.search(r"—\s*(Numero_lavoratori|Numero_domande|Numero_mensilita)\s*$",
                  indicator, re.I)
    if not m:
        return None
    measure = m.group(1).casefold()
    if measure not in ALLOWED_MEASURES:
        return None
    if str(s.get("unit", "")).casefold() not in ("numero", "n."):
        return None
    if s.get("extraction_method") != "original_inps_csv_fixed_classification_rows":
        return None
    territory = clean_human_territory(s.get("territory"))
    if not territory:
        return None
    obs = s.get("observations")
    if not isinstance(obs, list) or len(obs) < 2:
        return None
    latest_period = str(obs[-1].get("period") or "")
    if article.get("period_reference") != latest_period:
        return None
    values = []
    for row in obs[-2:]:
        try:
            f = float(row["value"])
        except (KeyError, ValueError, TypeError):
            return None
        if not math.isfinite(f) or f < 0:
            return None
        values.append(f)
    return territory, latest_period, str(obs[-2].get("period") or ""), values, measure


def journalistic_headline(article):
    info = _verified_measure(article)
    if info is None:
        return None
    territory, current, previous, (last_before, last), measure = info
    neutral, rising, falling, stable = ALLOWED_MEASURES[measure]
    match = MONTHLY.fullmatch(current)
    if match:
        yr, mn = int(match.group(1)), int(match.group(2))
        date_label = f"a {MONTHS_IT[mn]} {yr}"
        prior = date(yr-1, 12) if mn == 1 else date(yr, mn-1)
        # Only claim a direction with a real immediately preceding month.
        adjacent = previous == f"{prior.year:04d}-{prior.month:02d}"
    elif ANNUAL.fullmatch(current):
        date_label = f"nel {current}"
        adjacent = previous == str(int(current)-1)
    else:
        return None
    subject = (rising if last > last_before else
               falling if last < last_before else stable) if adjacent else neutral
    title = f"{territory}, integrazioni salariali: {subject} {date_label}"
    if len(title) > MAX_HEADLINE_CHARS or len(title) < 35:
        return None
    return title


def with_editorial_headline(article):
    """Return only a two-field title adaptation, leaving source record intact."""
    title = journalistic_headline(article)
    if title is None or (title == article.get("headline")
                         and title == article.get("pulse_title")):
        return article
    out = dict(article)
    out["headline"] = title
    out["pulse_title"] = title
    return out
