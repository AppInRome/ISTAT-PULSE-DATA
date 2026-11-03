#!/usr/bin/env python3
"""Evidence-only, original PULSE long-form prose for validated time series.

Never use unverified press numbers for an original quantitative article.
Narrative paragraphs are computed from the same observations as graph/table.
"""
from __future__ import annotations
import math

def _n(x):
    s = f"{float(x):,.2f}".rstrip("0").rstrip(".")
    return s.replace(",", "_").replace(".", ",").replace("_", ".")

def longform_sections(series, publisher):
    """Return reader-ready paragraphs, or [] if comparable evidence is absent."""
    if not series or not isinstance(series, dict):
        return []
    points = series.get("observations") or []
    unit = str(series.get("unit") or "").strip()
    indicator = str(series.get("indicator") or "").strip()
    source = str(series.get("source_url") or "").strip()
    if not unit or not indicator or len(points) < 2 or not source.startswith("https://"):
        return []
    try:
        values = [(str(p["period"]), float(p["value"])) for p in points]
        if any(not math.isfinite(v) for _, v in values):
            return []
        if len({d for d, _ in values}) != len(values):
            return []
    except (ValueError, TypeError, KeyError):
        return []
    values.sort(key=lambda p: p[0])
    first, prev, last = values[0], values[-2], values[-1]
    diff = last[1] - prev[1]
    opening_diff = last[1] - first[1]
    direction = ("è aumentato" if diff > 0 else "è diminuito" if diff < 0 else "è rimasto invariato")
    sign = "più" if diff > 0 else "meno" if diff < 0 else "lo stesso valore di"
    base = f"{indicator[:1].upper() + indicator[1:]}"
    latest = f"{_n(last[1])} {unit}"
    previous = f"{_n(prev[1])} {unit}"
    period_start, period_end = first[0], last[0]
    sections = [
        {"heading": "", "text":
         f"Il dato più recente disponibile per {indicator.lower()} è {latest}, riferito al periodo {period_end}. "
         f"È il valore riportato nella serie di {publisher} collegata alla pubblicazione originale. "
         f"Per comprenderne la portata bisogna confrontarlo con i periodi precedenti, "
         f"non con il giorno in cui la notizia è stata pubblicata."},
        {"heading": "", "text":
         f"Rispetto a {prev[0]}, quando lo stesso indicatore era pari a {previous}, "
         f"il valore {direction}. La differenza assoluta è {_n(abs(diff))} {unit} "
         f"({'in aumento' if diff > 0 else 'in diminuzione' if diff < 0 else 'nessuna variazione'}). "
         "Si tratta del confronto tra due osservazioni della stessa serie, "
         "con l'identica unità di misura. Non è una stima ricavata dal titolo di un giornale."},
        {"heading": "", "text":
         f"Lo sguardo sul periodo più lungo restituisce un'altra informazione: "
         f"tra {period_start} e {period_end}, {indicator.lower()} passa da "
         f"{_n(first[1])} {unit} a {latest}. La differenza tra i due estremi "
         f"è {_n(abs(opening_diff))} {unit} "
         f"({'positiva' if opening_diff > 0 else 'negativa' if opening_diff < 0 else 'nulla'}). "
         "Questo confronto descrive gli estremi osservati; non significa che "
         "il percorso sia stato regolare in tutti i periodi intermedi."},
    ]
    if len(values) >= 3:
        low = min(values, key=lambda p: p[1])
        high = max(values, key=lambda p: p[1])
        sections.append({"heading": "", "text":
            f"La serie qui utilizzata contiene {len(values)} osservazioni, "
            f"dal {period_start} al {period_end}. Il valore più basso è "
            f"{_n(low[1])} {unit} ({low[0]}); quello più alto è "
            f"{_n(high[1])} {unit} ({high[0]}). "
            "Questi estremi aiutano a collocare l'ultimo dato nel suo contesto, "
            "ma non bastano da soli a identificare le cause delle oscillazioni."})
    if prev[1] != 0:
        relative = diff / abs(prev[1]) * 100
        sections.append({"heading": "", "text":
            f"Misurando la differenza in rapporto al livello del periodo precedente, "
            f"la variazione è pari a {_n(abs(relative))}% "
            f"({'in più' if relative > 0 else 'in meno' if relative < 0 else 'senza variazione'}). "
            + ("Attenzione: per un indicatore espresso in percentuale, la differenza assoluta "
               "fra due valori è misurata in punti percentuali, mentre questa è una "
               "variazione percentuale relativa. Le due misure non sono intercambiabili."
               if unit == "%" else
               "La percentuale relativa misura il cambiamento rispetto al valore di partenza; "
               "non è una percentuale di popolazione, a meno che la definizione dell'indicatore lo stabilisca.")})
    sections.extend([
        {"heading": "", "text":
         f"Che cosa racconta allora questa statistica? Descrive l'andamento di "
         f"{indicator.lower()} nei periodi per i quali esistono osservazioni confrontabili. "
         "Per stabilire se il cambiamento sia rilevante sul piano economico, sociale o territoriale "
         "servono inoltre le definizioni ufficiali dell'indicatore, la sua copertura e, "
         "quando pertinenti, confronti con altri territori e variabili. "
         "Non attribuiamo automaticamente una causa a una variazione numerica."},
        {"heading": "", "text":
         f"Il grafico e la tabella associati a questo articolo riportano i medesimi "
         f"{len(values)} valori controllati, con il periodo e l'unità di misura. "
         f"La fonte primaria è {publisher}, disponibile al collegamento originale "
         f"({source}). Il periodo dei dati non deve essere confuso con la data di "
         "pubblicazione dell'articolo. Non vengono aggiunte stime né valori estrapolati."}
    ])
    return sections
