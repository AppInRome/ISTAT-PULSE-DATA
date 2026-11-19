#!/usr/bin/env python3
"""Generate one private, evidence-constrained PULSE draft without touching feeds.

Example (outside a public repository):
 PULSE_LLM_ENDPOINT=http://127.0.0.1:11434/v1/chat/completions \
 PULSE_LLM_MODEL=qwen3.5:9b python scripts/pulse_editorial_recovery_draft_cli.py \
 --article-id PULSE-XXXX --output ../PULSE_PRIVATE_DRAFTS/bozza.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.pulse_ai_newsroom import attempt_ai_edition
    from scripts.pulse_editorial_recovery_guard import stage_ai_draft
except ModuleNotFoundError:
    from pulse_ai_newsroom import attempt_ai_edition
    from pulse_editorial_recovery_guard import stage_ai_draft

ROOT = Path(__file__).resolve().parents[1]


def prepare_from_archive(archive: dict, article_id: str, writer=attempt_ai_edition) -> dict:
    articles = archive.get("articles")
    if not isinstance(articles, list):
        raise ValueError("invalid_article_archive")
    candidates = [a for a in articles if a.get("id") == article_id]
    if len(candidates) != 1:
        raise ValueError("article_id_not_unique_or_missing")
    original = candidates[0]
    edited = writer(original)
    if edited is original or edited == original:
        raise ValueError("model_unavailable_or_draft_failed_validation")
    return stage_ai_draft(original, edited)


def main() -> int:
    parser = argparse.ArgumentParser(description="PULSE: local/private editorial AI draft")
    parser.add_argument("--archive", type=Path, default=ROOT / "data/news/articles.json")
    parser.add_argument("--article-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.resolve()
    if target.is_relative_to(ROOT.resolve()):
        parser.error("Output must be OUTSIDE public PULSE DATA repository")
    if target.suffix.lower() != ".json":
        parser.error("Output must be a JSON file")
    archive = json.loads(args.archive.read_text(encoding="utf-8"))
    draft = prepare_from_archive(archive, args.article_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: do not overwrite a reviewer working copy.
    with target.open("x", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[OK] Bozza privata creata: {target}")
    print("[INFO] NON pubblicata. Restano obbligatori controlli e approvazione umana.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
