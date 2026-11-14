"""PULSE Italia — deterministic statistical elaborations and traceable chart variants.

All output uses only original observations. Transformations are NOT new official
measurements; never interpolate, extrapolate or join incompatible time series.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

PERIOD_RE = re.compile(r"(?P<year>(?:19|20)\d{2})(?:-(?:(?P<month>0[1-9]|1[0-2])|Q(?P<quarter>[1-4])))?$")


def _period(s):
    m = PERIOD_RE.fullmatch(str(s))
    if m is None:
        raise ValueError("unsupported_period")
    year = int(m.group("year"))
    if m.group("month"):
        return "M", year * 12 + int(m.group("month")) - 1
    if m.group("quarter"):
        return "Q", year * 4 + int(m.group("quarter")) - 1
    return "A", year


def _number(raw):
    try:
        n = Decimal(str(raw))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("invalid_observation") from exc
    if not n.is_finite():
        raise ValueError("non_finite_observation")
    return n


def _plain(n):
    if n is None:
        return None
    n = n.quantize(Decimal("0.000001"))
    return float(n)


def calculate(series):
    """Five independent original/derived views with exact period provenance.

    All rates use the observation at the *stated* reference period. A monthly
    year-over-year comparison uses the same month of the prior year. Percentage
    point differences and relative-percent changes are different calculations.
    """
    obs = list(series.get("observations") or [])
    if not 2 <= len(obs) <= 120:
        raise ValueError("at_least_two_at_most_120_observations_required")
    periods, values, indexes = [], [], []
    kind = None
    for o in obs:
        period = str(o["period"])
        group, index = _period(period)
        if kind is not None and kind != group:
            raise ValueError("mixed_calendar_frequency")
        kind = group
        periods.append(period)
        values.append(_number(o["value"]))
        indexes.append(index)
    if len(set(indexes)) != len(indexes) or indexes != sorted(indexes):
        raise ValueError("duplicate_or_unsorted_periods")

    unit = str(series.get("unit") or "").strip()
    if not unit:
        raise ValueError("unlabelled_unit")
    if unit == "%" and any(not Decimal(0) <= v <= Decimal(100) for v in values):
        raise ValueError("percentage_out_of_range")
    base = values[0]
    tick = {"M": 12, "Q": 4, "A": 1}[kind]
    looked_up = dict(zip(indexes, values))
    views = {
        "original": [],
        "delta": [],
        "relative_change": [],
        "index_100": [],
        "rolling_mean_3": [],
        "year_over_year": [],
    }

    def append(name, period, result, used, math, output_unit, warning=None):
        views[name].append({
            "period": period,
            "value": _plain(result),
            "unit": output_unit,
            "kind": "observed" if name == "original" else "calculated",
            "based_on": used,
            "calculation": math,
            "available": result is not None,
            "unavailable_reason": warning if result is None else None,
        })

    for i, (p, value, index) in enumerate(zip(periods, values, indexes)):
        append("original", p, value, [p], "source_value", unit)
        if i > 0 and indexes[i] - indexes[i-1] == 1:
            before = values[i-1]
            diff = value - before
            append("delta", p, diff, [periods[i-1], p],
                   "value(t)-value(t-1)", "punti percentuali" if unit == "%" else unit)
            append("relative_change", p,
                   (diff / abs(before) * 100) if before != 0 else None,
                   [periods[i-1], p],
                   "(value(t)-value(t-1))/abs(value(t-1))*100", "%",
                   "previous_period_zero" if before == 0 else None)
        else:
            why = "first_period" if i == 0 else "non_consecutive_periods"
            append("delta", p, None, [], "value(t)-value(t-1)",
                   "punti percentuali" if unit == "%" else unit, why)
            append("relative_change", p, None, [],
                   "(value(t)-value(t-1))/abs(value(t-1))*100", "%", why)

        append("index_100", p, (value / base * 100) if base != 0 else None,
               [periods[0], p], "value(t)/value(base)*100", "indice (base 100)",
               "base_is_zero" if base == 0 else None)

        if i >= 2 and indexes[i] - indexes[i-1] == 1 and indexes[i-1] - indexes[i-2] == 1:
            mean = sum(values[i-2:i+1], Decimal(0)) / Decimal(3)
            append("rolling_mean_3", p, mean, periods[i-2:i+1],
                   "(value(t)+value(t-1)+value(t-2))/3", unit)
        else:
            append("rolling_mean_3", p, None, [],
                   "(value(t)+value(t-1)+value(t-2))/3", unit,
                   "three_consecutive_periods_required")

        prior = looked_up.get(index-tick)
        ref_label = next((pp for pp, ix in zip(periods, indexes) if ix == index-tick), None)
        append("year_over_year", p, value-prior if prior is not None else None,
               [ref_label, p] if ref_label else [],
               "value(t)-value(same_period_previous_year)",
               "punti percentuali" if unit == "%" else unit,
               "no_same_period_previous_year")

    metadata = {
        "original": ("Serie osservata", "Valori originali, non trasformati."),
        "delta": ("Differenza dal periodo precedente",
                  "Differenza assoluta; per un tasso in % si misura in punti percentuali."),
        "relative_change": ("Variazione relativa (%)",
                            "Percentuale calcolata rispetto al modulo del valore precedente."),
        "index_100": ("Indice base 100",
                      "Primo periodo disponibile = 100; non valido se la base è zero."),
        "rolling_mean_3": ("Media mobile di 3 periodi",
                           "Solo finestre di tre periodi consecutivi, senza interpolazioni."),
        "year_over_year": ("Variazione rispetto a un anno prima",
                           "Stesso mese/trimestre dell'anno precedente, oppure anno precedente."),
    }
    return {
        "schema_version": 1,
        "type": "deterministic_statistical_elaborations",
        "indicator": series.get("indicator", ""),
        "frequency": kind,
        "source_unit": unit,
        "method": "exact_original_observations_only",
        "no_imputation_or_forecasting": True,
        "primary_source_remains_original": True,
        "views": [
            {
                "id": name,
                "label": metadata[name][0],
                "explanation": metadata[name][1],
                "points": points,
                "usable_points": sum(p["available"] for p in points),
                "graph_types": ["line", "bar"],
            }
            for name, points in views.items()
            if sum(p["available"] for p in points) >= (2 if name not in {"delta","year_over_year"} else 1)
        ],
    }
