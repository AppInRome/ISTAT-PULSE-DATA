#!/usr/bin/env python3
"""PULSE — restored deterministic long-form articles, no language model.

Port of the source-locked approach from historical
PULSE-EDITORIAL-RECOVERY/01_MOTORE_EDITORIALE_STORICO/
scripts/pulse_editorial_publication.py (11 Oct 2026).
Only original VERIFIED statistical observations enter this writer.
The original publisher is always credited in source_url; the text is NOT
a paraphrase of a newspaper article. Publication still needs human review.
"""
from __future__ import annotations

from decimal import Decimal
from scripts import pulse_editorial_audit_v1 as audit
from scripts import pulse_italia_chart_analytics as chart


def fmt(value):
    """Rounded Italian decimal for journalism, not raw floating point."""
    number = audit.decimal_value(value).quantize(Decimal("0.01"))
    return audit.nfmt(number).replace(".", ",")


def write_verified_article(evidence):
    """Create a full 250-500 word draft from one exact official series.

    Return (draft, audit_report) or (None, reason). No invented dates, actors,
    statistical values, causes or forecasts. If a series is too thin or
    internally inconsistent, fail closed rather than filling prose.
    """
    if not isinstance(evidence, dict) or evidence.get("verified") is not True:
        return None, {"passed": False, "issues": ["primary_evidence_unverified"]}
    series = evidence.get("series") or {}
    obs = series.get("observations") or []
    if len(obs) < 2:
        return None, {"passed": False, "issues": ["not_enough_observations"]}
    try:
        analytic = chart.calculate(series)
        topic = str(series["indicator"]).strip()
        territory = str(series["territory"]).strip()
        population = str(series["population"]).strip()
        period = str(series["frequency"]).strip()
        unit = str(series["unit"]).strip()
        publisher = str(evidence["publisher"]).strip()
        first, previous, latest = obs[0], obs[-2], obs[-1]
        old = audit.decimal_value(previous["value"])
        new = audit.decimal_value(latest["value"])
        movement = ("superiore" if new > old else "inferiore" if new < old else "uguale")
        direction = ("aumenta" if new > old else "diminuisce" if new < old else "resta invariato")
        difference = abs(new-old)
        diff_unit = "punti percentuali" if unit == "%" else unit
        p0, p1 = str(previous["period"]), str(latest["period"])
        first_period = str(first["period"])
        original_view = next(v for v in analytic["views"] if v["id"] == "original")
        if original_view["usable_points"] < 2:
            raise ValueError("insufficient_verified_points")
        delta_view = next((v for v in analytic["views"] if v["id"] == "delta"), None)
        adjacent = bool(delta_view and delta_view["points"][-1]["available"])
    except (ValueError, TypeError, KeyError, IndexError, StopIteration, ArithmeticError) as exc:
        return None, {"passed": False, "issues": ["invalid_statistical_series_"+type(exc).__name__]}

    noun = topic[:1].lower() + topic[1:]
    level_before = fmt(old) + ("%" if unit == "%" else " " + unit)
    level_after = fmt(new) + ("%" if unit == "%" else " " + unit)
    comparator = (
        f"Lo scarto assoluto è di {fmt(difference)} {diff_unit}; "
        "la differenza è calcolata su osservazioni consecutive della medesima serie."
        if adjacent else
        "Le osservazioni riguardano periodi non consecutivi. La distanza tra i valori "
        "è descrittiva e non viene presentata come una variazione del periodo immediatamente precedente."
    )
    p = [
        (
            f"Il dato più recente disponibile per {noun} riguarda {territory} "
            f"e il periodo {p1}. La misura riportata nella serie originale di {publisher} "
            f"è {level_after}, riferita alla popolazione «{population}». "
            "Si tratta di un'osservazione statistica precisa, che non va confusa "
            "con la data in cui la notizia viene rilevata dal radar PULSE."
        ),
        (
            f"Il confronto utile è con {p0}, quando il valore osservato era {level_before}. "
            f"Nell'ultima osservazione la misura risulta {movement} rispetto a quel riferimento. "
            f"{comparator} "
            "I valori appartengono alla stessa serie e riportano la stessa unità, "
            "evitando di mettere insieme misure tratte da popolazioni differenti."
        ),
        (
            f"Il punto iniziale di questa serie è {first_period}; "
            f"il dato allora registrato era {fmt(first['value'])}"
            + ("%" if unit == "%" else f" {unit}") + ". "
            "Leggere anche l'inizio dell'intervallo aiuta a collocare l'ultima osservazione "
            "nell'insieme dei periodi effettivamente documentati. "
            "Non si ricostruiscono anni o mesi intermedi quando non compaiono "
            "nelle evidenze e non si prolunga automaticamente la tendenza nel futuro."
        ),
        (
            f"Il tema statistico descritto dal documento è {noun}; "
            f"il gruppo di riferimento è «{population}» e l'area misurata è {territory}. "
            f"La frequenza indicata dalla fonte è {period}, mentre l'unità di misura è «{unit}». "
            "Queste informazioni sono essenziali per leggere correttamente il confronto: "
            "due grandezze con etichette simili non sono intercambiabili se cambiano "
            "la definizione, il territorio oppure la popolazione considerata."
        ),
        (
            "Il risultato documenta una differenza fra osservazioni, non la spiegazione "
            "dei fattori che possono averla prodotta. "
            "Per attribuire cause, conseguenze o comportamenti alle persone servirebbero "
            "ulteriori informazioni, che questa singola serie non offre. "
            "L'interpretazione pubblicata rimane quindi proporzionata alla precisione dei dati "
            "e non presenta ipotesi, collegamenti presunti o scenari previsionali come fatti."
        ),
        (
            f"I valori provengono dalla fonte primaria {publisher}, identificata "
            "nel collegamento al documento originale disponibile insieme all'articolo. "
            "Grafico e tabella sono costruiti con le stesse osservazioni, "
            "senza modificare le misure per adattarle al racconto. "
            "Ogni confronto numerico può essere ricontrollato sulla serie acquisita; "
            "la redazione deve comunque valutare il significato giornalistico "
            "del testo prima di autorizzarne la pubblicazione."
        ),
    ]
    headline = f"{topic[:86].rstrip()}: i dati di {territory[:38]} nel {p1}"
    draft = {
        "title": headline,
        "lead": p[0],
        "paragraphs": p[1:],
        "source_url": evidence["source_url"],
        "dataset_url": evidence["dataset_url"],
        "evidence_sha256": audit.digest(evidence),
        "editorial_status": "deterministic_source_locked_draft",
        "publication_status": "draft",
        "writer": "historical_PULSE_deterministic_restored_v1",
        "requires_human_review": True,
        "independent_number_audit_required": True,
    }
    report = audit.audit(draft, evidence)
    draft["audit"] = report
    return (draft if report["passed"] else None), report
