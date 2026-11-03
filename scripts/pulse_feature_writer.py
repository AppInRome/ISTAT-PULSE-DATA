#!/usr/bin/env python3
"""PULSE evidence-led numerical narratives, never newspaper copy.

Only writes statements deducible from one comparable primary-source series.
A source-backed explanation is not equivalent to a reported investigation.
"""
from __future__ import annotations
import math
import re
from urllib.parse import urlparse


def _n(value):
    s = f"{float(value):,.6f}".rstrip("0").rstrip(".")
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _section(s):
    return {"heading": "", "text": s}


def longform_sections(series, publisher):
    if not isinstance(series, dict):
        return []
    indicator = str(series.get("indicator") or "").strip()
    unit = str(series.get("unit") or "").strip()
    source = str(series.get("source_url") or "")
    observations = series.get("observations")
    url = urlparse(source)
    if (not indicator or not unit or url.scheme != "https" or not url.hostname
            or not isinstance(observations, list) or len(observations) < 2):
        return []
    entries = []
    for row in observations:
        try:
            period = str(row["period"]).strip()
            value = float(row["value"])
        except (KeyError, ValueError, TypeError):
            return []
        if (not math.isfinite(value) or
                not re.fullmatch(r"(?:19|20)\d{2}(?:-(?:Q[1-4]|\d{2}))?", period)):
            return []
        entries.append((period, value))
    entries.sort(key=lambda x: x[0])
    if len({period for period, _ in entries}) != len(entries):
        return []

    earliest, previous, latest = entries[0], entries[-2], entries[-1]
    delta = latest[1] - previous[1]
    movement = ("cresce" if delta > 0 else "diminuisce" if delta < 0 else "non cambia")
    absolute_unit = "punti percentuali" if unit == "%" else unit
    first_to_last = latest[1] - earliest[1]
    domain = str(publisher or url.hostname).strip()[:100]
    name = indicator[:1].lower() + indicator[1:]

    paragraphs = [
        _section(
            f"Nel periodo {latest[0]}, {name} raggiunge {_n(latest[1])} {unit}. "
            f"È l'ultima osservazione presente nella serie statistica di {domain} "
            f"collegata al documento originale. L'informazione principale riguarda "
            f"un fenomeno misurato in un periodo preciso, non il giorno in cui "
            f"la notizia viene ripresa dalla stampa."
        ),
        _section(
            f"Il termine di paragone più vicino è {previous[0]}, quando lo stesso "
            f"indicatore valeva {_n(previous[1])} {unit}. Tra i due periodi "
            f"la misura {movement}: lo scarto è di {_n(abs(delta))} {absolute_unit}. "
            "Il confronto avviene dentro una sola serie identificata, con la stessa "
            "unità di misura; non unisce numeri raccolti da tabelle differenti."
        ),
        _section(
            f"Guardando all'intervallo dal {earliest[0]} al {latest[0]}, "
            f"si passa da {_n(earliest[1])} {unit} a {_n(latest[1])} {unit}. "
            f"Rispetto al primo punto osservato, la differenza è "
            f"{_n(abs(first_to_last))} {absolute_unit}, "
            f"{'in aumento' if first_to_last > 0 else 'in diminuzione' if first_to_last < 0 else 'senza variazione'}. "
            "Il confronto tra estremi descrive il saldo del periodo: "
            "non dimostra che il percorso intermedio sia stato uniforme."
        ),
    ]
    if len(entries) >= 3:
        lowest = min(entries, key=lambda v: v[1])
        highest = max(entries, key=lambda v: v[1])
        changes = [entries[i][1] - entries[i-1][1] for i in range(1,len(entries))]
        direction_changes = sum(1 for i in range(1, len(changes)) if changes[i]*changes[i-1] < 0)
        path = (
            "presenta almeno un'inversione di direzione" if direction_changes
            else "non presenta inversioni tra incrementi e diminuzioni nei periodi successivi"
        )
        paragraphs.append(_section(
            f"Le {len(entries)} osservazioni permettono anche di leggere gli estremi "
            f"della distribuzione temporale: il minimo è {_n(lowest[1])} {unit} "
            f"nel {lowest[0]}, mentre il massimo è {_n(highest[1])} {unit} nel {highest[0]}. "
            f"Fra le misure disponibili, l'andamento {path}. "
            "Il numero dei periodi disponibili definisce la profondità del confronto; "
            "non autorizza a estendere una tendenza oltre l'ultimo anno osservato."
        ))
    else:
        paragraphs.append(_section(
            f"La fonte offre qui due punti confrontabili, {previous[0]} e {latest[0]}. "
            "Con due sole osservazioni si può quantificare una differenza ma non "
            "stabilire se essa rappresenti una tendenza duratura, un episodio "
            "isolato o una fluttuazione già avvenuta in passato. Per questa "
            "ragione il grafico confronta i valori senza suggerire proiezioni."
        ))

    if previous[1] != 0:
        relative = 100 * delta / abs(previous[1])
        paragraphs.append(_section(
            f"Rapportando la differenza al valore di {previous[0]}, "
            f"la variazione relativa è pari a {_n(abs(relative))}% "
            f"({'positiva' if relative > 0 else 'negativa' if relative < 0 else 'nulla'}). "
            + ("È distinta dalla differenza in punti percentuali tra "
               "le due quote: confonderle ingrandirebbe o ridurrebbe impropriamente "
               "il significato del cambiamento."
               if unit == "%" else
               "Questa percentuale descrive la variazione rispetto alla base precedente, "
               "non la quota della popolazione interessata dal fenomeno.")
        ))
    else:
        paragraphs.append(_section(
            f"Nel {previous[0]} il punto di partenza valeva zero. In questo caso "
            "una variazione percentuale relativa non è definibile: sarebbe "
            "ingannevole presentarla come una crescita percentuale finita. "
            f"Il confronto utilizzabile resta quindi lo scarto assoluto "
            f"di {_n(abs(delta))} {absolute_unit}."
        ))

    paragraphs.extend([
        _section(
            f"L'indicatore {name} descrive esattamente la grandezza riportata "
            f"nel documento e non misura, da solo, tutte le condizioni che "
            "possono influenzarla. Una differenza numerica non prova quali "
            "cause l'abbiano prodotta; per parlare di effetti, persone o "
            "territori diversi occorrerebbero definizioni e confronti "
            "ulteriori verificati sulle rispettive fonti."
        ),
        _section(
            f"Per controllare questa lettura, il grafico e la tabella riportano "
            f"gli stessi {len(entries)} valori, ciascuno con periodo e unità "
            f"di misura. Il riferimento primario è {domain}: {source}. "
            "La data di pubblicazione del documento e gli anni delle osservazioni "
            "sono informazioni distinte. Non sono stati interpolati valori, "
            "né aggiunte previsioni non contenute nella fonte."
        ),
    ])
    return paragraphs
