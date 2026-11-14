#!/usr/bin/env python3
"""Journalistic *presentation* of already verified PULSE statistics (no AI).

Never replaces original deterministic drafts, statistical values, charts, tables,
source references, identities or publication timestamps. Rejects altered source
evidence, misleading non-adjacent comparisons and unsupported numeric claims.
The existing 250-500 word historical article remains the safe fallback.
"""
from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import re

from scripts import pulse_editorial_audit_v1 as audit
from scripts import pulse_editorial_selector as selector

SCHEMA = "pulse-journalistic-presentation-v1"
BODY_LIMIT = 7000
TITLE_MAX = 110

# Editorial labels are descriptive, NOT a change in the measured indicator.
LABELS = (
    ("abitazioni sovraffollate", "abitazioni sovraffollate"),
    ("sovraccarico dei costi abitativi", "spese per l'abitazione"),
    ("speranza di vita in buona salute", "speranza di vita in buona salute"),
    ("speranza di vita", "speranza di vita"),
    ("rifiuti urbani prodotti per abitante", "rifiuti urbani per abitante"),
    ("totale dei rifiuti urbani", "rifiuti urbani"),
    ("energia da fonti rinnovabili", "energia rinnovabile"),
    ("consumo finale di energia", "consumi finali di energia"),
    ("prodotto interno lordo per abitante", "PIL per abitante"),
    ("prodotto interno lordo", "prodotto interno lordo"),
    ("prezzi al consumo armonizzati", "prezzi al consumo"),
    ("popolazione al primo gennaio", "popolazione residente"),
    ("popolazione maschile", "popolazione maschile"),
    ("istruzione terziaria", "istruzione terziaria"),
    ("abbandonano precocemente", "abbandono precoce degli studi"),
    ("rischio di povertà", "rischio di povertà"),
    ("integrazioni salariali lavoratori", "integrazioni salariali: lavoratori"),
    ("integrazioni salariali mensilita", "integrazioni salariali: mensilità"),
    ("integrazioni salariali domande", "integrazioni salariali: domande"),
)


def _label(indicator):
    raw = str(indicator).strip()
    low = raw.casefold()
    for needle, replacement in LABELS:
        if needle in low:
            return replacement
    # Unrecognized indicators remain named as they are at the official source.
    return raw.split(" — ")[0].strip()[:65].lower()


def _fmt(value):
    v = audit.decimal_value(value)
    q = v.quantize(Decimal("0.01"))  # exactly the legacy auditor's ROUND_HALF_EVEN
    raw=format(q,"f").rstrip("0").rstrip(".") if "." in format(q,"f") else format(q,"f")
    integer,dot,decimal=raw.partition(".")
    # Italian editorial grouping without changing the numeric value.
    grouped=f"{int(integer):,}".replace(",",".")
    return grouped+(","+decimal if dot else "")


def _measure(v, unit):
    result = _fmt(v)
    if unit=="%":return result+"%"
    if str(unit).casefold() in ("numero","n."):return result
    return result+" "+unit


_MONTHS=("", "gennaio", "febbraio", "marzo", "aprile", "maggio",
         "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")
_QUARTERS=("", "primo", "secondo", "terzo", "quarto")


def _when(period):
    value=str(period)
    m=re.fullmatch(r"((?:19|20)\d{2})-(0[1-9]|1[0-2])",value)
    if m:
        return f"a {_MONTHS[int(m[2])]} {m[1]}"
    q=re.fullmatch(r"((?:19|20)\d{2})-Q([1-4])",value)
    if q:
        return f"nel {_QUARTERS[int(q[2])]} trimestre {q[1]}"
    return f"nel {value}"


def _subject(indicator, fallback):
    """Grammatically sound singular subject; never invents an explanation."""
    key=str(indicator).casefold()
    if "abitazioni sovraffollate" in key or "sovraffollamento abitativo" in key:
        return "la quota di persone in abitazioni sovraffollate"
    if "speranza di vita" in key or "anni in buona salute" in key:
        return "la speranza di vita in buona salute" if ("buona" in key or "healthy" in key) else "la speranza di vita"
    if "rifiuti urbani prodotti per abitante" in key:
        return "la produzione di rifiuti urbani per abitante"
    if "totale dei rifiuti urbani" in key:
        return "la produzione complessiva di rifiuti urbani"
    if "energia da fonti rinnovabili" in key or "energia rinnovabile" in key:
        return "la quota di energia da fonti rinnovabili"
    if "produttività energetica" in key:
        return "la produttività energetica"
    if "dipendenza dalle importazioni di energia" in key:
        return "la dipendenza dalle importazioni energetiche"
    if "buona salute percepita" in key:
        return "la quota di persone che dichiarano una buona salute"
    if "tasso di riciclo dei rifiuti" in key:
        return "il tasso di riciclo dei rifiuti urbani"
    if "prodotto interno lordo" in key:
        return "il prodotto interno lordo per abitante" if "per abitante" in key else "il prodotto interno lordo"
    if "popolazione al primo gennaio" in key:
        return "la popolazione residente"
    if "popolazione femminile" in key:
        return "la popolazione femminile"
    if "popolazione maschile" in key:
        return "la popolazione maschile"
    if "integrazioni salariali" in key:
        if "lavoratori" in key: return "il numero di lavoratori rilevati per le integrazioni salariali"
        if "mensilita" in key or "mensilità" in key: return "il numero di mensilità rilevate per le integrazioni salariali"
        if "domande" in key:return "il numero di domande rilevate per le integrazioni salariali"
    if "istruzione terziaria" in key: return "la quota di giovani adulti con istruzione terziaria"
    if "abbandonano precocemente" in key or "abbandono precoce" in key:
        return "la quota di giovani che abbandonano precocemente gli studi"
    if "povertà" in key: return "la quota di persone a rischio di povertà o esclusione"
    if "prezzi al consumo" in key or "inflazione" in key:
        return "il tasso di variazione dei prezzi al consumo"
    if "disoccupazione" in key: return "il tasso di disoccupazione"
    return "l'indicatore «"+fallback+"»"


def _percent_preposition(value):
    """Italian euphony for official percentage observations."""
    numeric = str(value).split("%", 1)[0].split(",", 1)[0].replace(".", "")
    try:
        n = int(numeric)
    except ValueError:
        return "al "
    return "all'" if n in (1, 8, 11) or 80 <= n <= 89 or 800 <= n <= 899 else "al "


def _title_metric(indicator,unit,value):
    if unit!="%": return value
    key=str(indicator).casefold()
    if any(w in key for w in ("inflazione","prezzi al consumo","disoccupazione",
                             "tasso di riciclo")):
        return "tasso "+_percent_preposition(value)+value
    if any(w in key for w in ("quota","popolazione","sovraffoll","energia da fonti",
                             "salute percepita","dipendenza dalle importazioni",
                             "istruzione","rifiut","povertà","abbandon")):
        return "quota "+_percent_preposition(value)+value
    return value


def _region(raw):
    area = str(raw or "").strip()
    if area.casefold()=="italia":
        return "In Italia", "Italia"
    if not re.fullmatch(r"[\wÀ-ÿ'’ .-]{2,60}",area):
        raise ValueError("bad_territory")
    return "In " + area.lower().title(), area.lower().title()


def _verified_source(item):
    context=(item.get("publication_tier")=="verified_official_context_not_new_release")
    if (item.get("editorial_format")!="deterministic_source_locked_auto_audited"
            or item.get("publication_status")!="published"
            or item.get("publication_tier") not in (
                "verified_official_deterministic",
                "verified_official_context_not_new_release")):
        return None
    # Contextual analyses must carry the original publisher's reference period
    # and a visible non-news disclosure even when Android shows editorial_story.
    if context and (item.get("editorial_kind")!="verified_context_analysis"
                    or not str(item.get("editorial_context_notice") or "")
                            .startswith("Analisi di contesto PULSE")):
        return None
    att=item.get("automatic_review") or {}
    if att.get("passed") is not True or att.get("model_used") is not False:
        return None
    originals=item.get("verified_series_relevant") or []
    docs=item.get("source_documents") or []
    if len(originals)!=1 or len(docs)!=1:
        return None
    s=originals[0]
    fingerprint=docs[0].get("sha256")
    if (not s.get("verified") or not isinstance(fingerprint,str)
            or not re.fullmatch("[0-9a-fA-F]{64}",fingerprint)
            or att.get("original_source_sha256")!=fingerprint):
        return None
    points=s.get("observations") or []
    chart=(item.get("chart_spec") or {}).get("data") or []
    table=(item.get("table_spec") or {}).get("rows") or []
    if not (2<=len(points)<=24 and len(points)==len(chart)==len(table)):
        return None
    for p,c,t in zip(points,chart,table):
        if not isinstance(t,list) or len(t)!=2:
            return None
        if not (str(p["period"])==str(c["period"])==str(t[0])
                and audit.decimal_value(p["value"])==audit.decimal_value(c["value"])
                ==audit.decimal_value(t[1])):
            return None
    if str(points[-1]["period"])!=str(item.get("period_reference")):
        return None
    if not str(s.get("unit") or "") or not s.get("indicator") or not s.get("territory"):
        return None
    return s


def _numeric_guard(story,s,item):
    # The only numbers used must be observed source values, their independently
    # recomputed differences, or the verified observation periods.
    evidence={"verified":True,"series":{"unit":s["unit"],"observations":s["observations"]}}
    allowed=audit.supported_numbers(evidence)
    prose=" ".join([story["headline"],story["lead"],*[
        v["text"] for v in story["sections"]]])
    for raw in audit.NUMBER.findall(prose):
        if audit.normalized_number(raw) not in allowed:
            return False
    if "punti percentuali" in prose and s["unit"]!="%":
        return False
    if any(t in prose.casefold() for t in ("senz'altro causato", "dimostra che la causa",
                                           "prova che la causa", "certamente dovuto a")):
        return False
    return len(prose) <= BODY_LIMIT


def compose(item):
    """A safe, compact, genuinely news-led variant. Return None on ambiguity."""
    try:
        s=_verified_source(item)
        if s is None:
            return None
        obs=s["observations"]
        last, before, initial=obs[-1],obs[-2],obs[0]
        y,x,z=[audit.decimal_value(row["value"]) for row in (last,before,initial)]
        if not all(v.is_finite() for v in (x,y,z)):
            return None
        period=str(last["period"])
        previous=str(before["period"])
        region,where=_region(s["territory"])
        topic=_label(s["indicator"])
        unit=s["unit"]
        source=str((item.get("public_source") or {}).get("domain") or "").strip()
        if not source:
            return None
        recent=selector.consecutive(previous,period)
        value=_measure(y,unit)
        base=_measure(x,unit)
        trend="stabile" if y==x else "in aumento" if y>x else "in calo"
        subject=_subject(s["indicator"],topic)
        display_metric=_title_metric(s["indicator"],unit,value)
        title=f"{where}, {topic}{' —' if ':' in topic else ':'} {display_metric} {_when(period)}"
        if len(title)>TITLE_MAX:
            title=f"{topic.capitalize()}: {value} {_when(period)}"
        if len(title)>TITLE_MAX or len(title)<25:
            return None
        is_context=(item.get("editorial_kind")=="verified_context_analysis"
                    and item.get("publication_tier")
                        =="verified_official_context_not_new_release")
        if is_context:
            title="Contesto — "+title
            if len(title)>TITLE_MAX:
                title=f"Contesto — {topic.capitalize()}: {value} {_when(period)}"
            if len(title)>TITLE_MAX:
                return None
        if recent:
            movement=("sale" if y>x else "scende" if y<x else "rimane")
            distance=abs(y-x)
            gap=f"{_fmt(distance)} punti percentuali" if unit=="%" else _measure(distance,unit)
            # We never describe a change in percentage points as percentage growth.
            lead=(f"{region}, {subject} {movement} " +
                  (_percent_preposition(value) if unit=="%" else "a ") + f"{value} {_when(period)}, "
                  f"rispetto a {base} {_when(previous)}. "
                  f"Lo scarto è di {gap}, secondo la serie ufficiale {source}.")
        else:
            lead=(f"{region}, {subject}: l'ultima osservazione disponibile è "
                  f"{value} {_when(period)}. La rilevazione precedente disponibile "
                  f"riguarda {_when(previous)} ({base}); i periodi non sono consecutivi. "
                  f"Fonte: {source}.")
        if is_context:
            lead=("Approfondimento su dati ufficiali già disponibili, "
                  "non una nuova pubblicazione dell'ente. "+lead)
        sections=[]
        if recent and y!=x:
            sections.append({"heading":"Che cosa cambia",
                "text":(f"Il segnale principale è un valore {trend} rispetto al "
                        f"periodo precedente: {base} {_when(previous)} e {value} {_when(period)}. "
                        "Il confronto riguarda la stessa definizione statistica nei "
                        "due periodi: il dato, da solo, non chiarisce le cause.")})
        elif recent:
            sections.append({"heading":"Il dato da osservare",
                "text":(f"Il livello rimane {value} sia {_when(previous)} sia {_when(period)}. "
                        "L'assenza di variazione fra queste due osservazioni non significa "
                        "che la serie sia stata invariata in tutti i periodi.")})
        else:
            sections.append({"heading":"Il confronto possibile",
                "text":(f"La serie riporta {base} {_when(previous)} e {value} {_when(period)}. "
                        "L'intervallo disponibile non permette di chiamare questa "
                        "differenza una variazione rispetto al periodo immediatamente precedente.")})
        initial_word="più alta" if y>z else "più bassa" if y<z else "uguale"
        sections.append({"heading":"Nel contesto della serie",
            "text":(f"All'inizio dell'intervallo documentato, {_when(initial['period'])}, "
                    f"il valore era {_measure(z,unit)}. L'osservazione più recente "
                    f"è {initial_word} rispetto a quel riferimento. "
                    "Il confronto documenta la distanza dall'inizio della serie, "
                     "senza trasformarla in una spiegazione causale.")})
        # Lead with the main fact instead of boilerplate; use a second data-led
        # angle only if the source provides three adjacent observations.
        if len(obs)>=3:
            prior=obs[-3]
            p0=str(prior["period"])
            v0=audit.decimal_value(prior["value"])
            if recent and selector.consecutive(p0,previous):
                d0=x-v0
                d1=y-x
                if d0!=0 and d1!=0 and (d0>0)!=(d1>0):
                    sections.append({"heading":"Un'inversione nella sequenza",
                        "text":(f"{_when(p0).capitalize()} il valore era {_measure(v0,unit)}; "
                                f"{_when(previous)} era {base}. Con l'ultima osservazione "
                                f"({value}), la direzione del cambiamento rispetto al "
                                "periodo precedente si è invertita. La sequenza, da sola, "
                                "non consente una previsione.")})
                elif d0!=0 and d1!=0 and (d0>0)==(d1>0):
                    sections.append({"heading":"La sequenza recente",
                        "text":(f"Le osservazioni successive sono {_measure(v0,unit)} {_when(p0)}, "
                                f"{base} {_when(previous)} e {value} {_when(period)}; "
                                "indicano la stessa direzione. Non basta a stabilire "
                                "che la tendenza proseguirà.")})
        if len(sections)<3:
            sections.append({"heading":"Il perimetro dell'indicatore",
                "text":(f"La misura descrive «{s['indicator']}» per il territorio "
                        f"{where}. È espressa in {unit}; per comprenderne il "
                        "significato bisogna mantenere la definizione e la popolazione "
                        "di riferimento della serie ufficiale.")})
        sections.append({"heading":"Fonte e limiti",
            "text":(f"I valori sono quelli pubblicati da {source}, per il periodo "
                    f"statistico {period}. Il periodo a cui si riferiscono i numeri "
                    "non coincide necessariamente con il giorno di pubblicazione "
                    "di PULSE. Questi dati non permettono di attribuire automaticamente "
                    "cause, effetti o responsabilità.")})
        story={"schema":SCHEMA,"headline":title,"lead":lead,
               "sections":sections,
               "period_reference":period,"source_sha256":item["source_documents"][0]["sha256"],
               "source_locked":True,"original_text_preserved":True,
               "editorial_kind":("verified_context_analysis" if is_context
                                 else "verified_official_news"),
               "not_a_new_source_release":is_context,
               "method":"deterministic_verified_observations_no_ai"}
        if not _numeric_guard(story,s,item):
            return None
        return story
    except (ValueError,TypeError,KeyError,IndexError,ArithmeticError,OverflowError):
        return None


def attach(item):
    """Return a shallow copy with OPTIONAL editorial presentation metadata."""
    new=compose(item)
    if new is None or item.get("editorial_story")==new:
        return item
    return {**item,"editorial_story":new}
