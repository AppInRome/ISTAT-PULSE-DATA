#!/usr/bin/env python3
"""Offline safety preview; does not alter the public feed without --apply."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

try:
    from scripts.pulse_editorial_recovery_guard import audit_news_archive, repair_observer_archive
except ModuleNotFoundError:
    from pulse_editorial_recovery_guard import audit_news_archive, repair_observer_archive


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--news", type=Path, default=Path("data/news/articles.json"))
    p.add_argument("--observers", type=Path, default=Path("data/news/observer_articles.json"))
    p.add_argument("--apply", action="store_true", help="Back up and rewrite both JSON snapshots")
    a = p.parse_args()
    results = {}
    updates = []
    for kind, path, fn in [("radar", a.news, audit_news_archive),
                            ("osservatori", a.observers, repair_observer_archive)]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        revised, report = fn(payload.get("articles") or [])
        results[kind] = report
        if a.apply and revised != payload.get("articles"):
            updates.append((path, payload, revised))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    if a.apply:
        for path, payload, revised in updates:
            backup = path.with_name(path.name + ".before_editorial_recovery.bak")
            if backup.exists():
                raise RuntimeError(f"Backup already exists; refusing overwrite: {backup}")
            backup.write_bytes(path.read_bytes())
            payload["articles"] = revised
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            print(f"[OK] {path} (backup: {backup})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
