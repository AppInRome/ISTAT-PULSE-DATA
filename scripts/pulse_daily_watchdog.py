#!/usr/bin/env python3
"""Independent daily freshness/coverage checks for VALE PULSE, without changing data."""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

def at(raw):
    if not isinstance(raw, str) or not raw: return None
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except ValueError:
        return None

def age_check(problems, label, value, now, max_hours):
    d = at(value)
    if d is None:
        problems.append(f"{label}: data di verifica assente o non valida")
    elif d > now:
        problems.append(f"{label}: data di verifica nel futuro")
    elif (now-d).total_seconds() > 3600*max_hours:
        problems.append(f"{label}: verifica obsoleta ({round((now-d).total_seconds()/3600)} ore)")

def assess(data: Path, now: datetime):
    problems, notes = [], []
    def read(rel):
        try: return json.loads((data / rel).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError) as exc:
            problems.append(f"{rel}: lettura/JSON non valido ({type(exc).__name__})")
            return {}
    refresh = read("refresh_status.json")
    age_check(problems, "PULSE generale", refresh.get("last_check_at"), now, 36)
    if refresh.get("latest_check_errors", 0):
        problems.append(f"PULSE: {refresh['latest_check_errors']} errori acquisizione")
    sections = refresh.get("sections", {})
    for section, max_hours in (("notizie", 36), ("territori", 42), ("green", 42)):
        entry = sections.get(section, {})
        age_check(problems, section, entry.get("last_success_at"), now, max_hours)
        if entry.get("status") != "ok":
            problems.append(f"{section}: stato {entry.get('status', 'assente')}")
        elif entry.get("last_attempt_at"):
            notes.append(f"{section}: controllo OK {entry['last_attempt_at']}")
    if sections.get("notizie", {}).get("feeds_failed", 0):
        problems.append("notizie: feed non raggiunti " + str(sections["notizie"]["feeds_failed"]))
    observer = read("observer_refresh_status.json")
    age_check(problems, "Pubblicazioni", observer.get("checked_at"), now, 36)
    if observer.get("articles_total", 0) < 4000:
        problems.append("Pubblicazioni: archivio troppo piccolo o inesistente")
    if observer.get("failed_source_count", 0):
        failed = [k for k, v in observer.get("sources", {}).items() if v.get("status") != "ok"]
        problems.append("Pubblicazioni: fonti non raggiunte " + ", ".join(failed))
    if observer.get("feeds_reached", 0) < 1:
        problems.append("Pubblicazioni: nessuna fonte raggiunta")
    catalog = read("news/observer_articles.json")
    age_check(problems, "Archivio Pubblicazioni", catalog.get("generated_at"), now, 36)
    if len(catalog.get("articles", [])) < 4000:
        problems.append("Archivio Pubblicazioni: numero articoli insufficiente")
    notes.append(f"Pubblicazioni: {len(catalog.get('articles', []))} voci, "
                 f"{observer.get('articles_new', '—')} nuove nell'ultimo controllo")
    editorial = read("news/editorial_refresh_status.json")
    age_check(problems, "Redazione articoli originali", editorial.get("last_editorial_check_at"), now, 42)
    notes.append("Articoli originali: " + str(editorial.get("published_articles_total", 0)))
    return problems, notes

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--now", type=str, default=None)
    args = parser.parse_args(argv)
    now = at(args.now) if args.now else datetime.now(timezone.utc)
    if now is None: parser.error("--now richiede una data UTC valida")
    problems, notes = assess(args.data, now)
    if os.environ.get("PULSE_WATCHDOG_REPORT"):
        Path(os.environ["PULSE_WATCHDOG_REPORT"]).write_text(
            json.dumps({"checked_at": now.isoformat(), "ok": not problems,
                        "problems": problems, "notes": notes},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in notes: print("OK ·", item)
    for item in problems: print("::error::" + item.replace("\n", " "))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as out:
            out.write("## PULSE · Controllo giornaliero\n\n")
            out.write("\n".join("- ✅ " + x for x in notes) + "\n")
            out.write("\n".join("- ⚠️ " + x for x in problems) + "\n")
    print(f"PULSE WATCHDOG: {'DEGRADED' if problems else 'OK'} · {len(problems)} problemi")
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
