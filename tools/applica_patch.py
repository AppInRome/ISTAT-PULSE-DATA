#!/usr/bin/env python3
"""Apply non-destructive editorial-only changes to CURRENT PULSE DATA sources.

No network, Git operations, workflow edits, or publication. Refuses unknown
sources and missing anchors instead of silently producing a broken result.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil

PACKAGE = Path(__file__).resolve().parents[1]
FILES_TO_ADD = (
    "tools/applica_patch.py",
    "scripts/pulse_editorial_recovery_guard.py",
    "scripts/pulse_editorial_recovery_draft_cli.py",
    "scripts/pulse_editorial_recovery_audit_cli.py",
    "tests/test_editorial_recovery_guard.py",
    "tests/test_install_patcher.py",
    "tests/fixtures/three_historical_samples.json",
    "docs/RECUPERO_EDITORIALE_IMPLEMENTAZIONE.md",
)


def replace_once(content: str, old: str, new: str, name: str) -> str:
    if new in content:
        return content
    times = content.count(old)
    if times != 1:
        raise RuntimeError(f"{name}: expected one insertion point, found {times}")
    return content.replace(old, new, 1)


def patched_radar(s: str) -> str:
    # This signature belongs to the modern AppInRome pipeline, NOT the Oct
    # 2026 backup. We must never overwrite a more recent Android app/backend.
    if "pulse_ai_newsroom" not in s or "pulse_original_editorial" not in s:
        raise RuntimeError("This is not the current editorial DATA radar")
    s = replace_once(s,
        '            if article.get("verification_tier")=="verified_comparable_series":\n'
        '                try:\n'
        '                    from scripts.pulse_ai_newsroom import attempt_ai_edition\n'
        '                except ModuleNotFoundError:\n'
        '                    from pulse_ai_newsroom import attempt_ai_edition\n'
        '                article=attempt_ai_edition(article)',
        '            # AI model output is never inserted into the public feed here.\n'
        '            # Generate evidence-linked, private drafts with\n'
        '            # pulse_editorial_recovery_draft_cli.py; publish only after review.',
        "radar AI publication gate")
    s = replace_once(s,
        '    arts=sorted(by_id.values(),key=lambda x:x.get("published_at",""),reverse=True)',
        '    try:\n'
        '        from scripts.pulse_editorial_recovery_guard import audit_news_archive\n'
        '    except ModuleNotFoundError:\n'
        '        from pulse_editorial_recovery_guard import audit_news_archive\n'
        '    guarded, recovery_report = audit_news_archive(list(by_id.values()))\n'
        '    by_id = {item["id"]: item for item in guarded}\n'
        '    arts=sorted(by_id.values(),key=lambda x:x.get("published_at",""),reverse=True)',
        "radar historical source card guard")
    s = replace_once(s,
        '    (ROOT/"editorial_quality_status.json").write_text(',
        '    quality["editorial_recovery"] = recovery_report\n'
        '    (ROOT/"editorial_quality_status.json").write_text(',
        "radar quality metadata")
    return s


def patched_observer(s: str) -> str:
    if 'def update(archive: Path = ARCHIVE' not in s or 'official_rss_link_and_publication_date' not in s:
        raise RuntimeError("This is not the current official RSS observer updater")
    s = replace_once(s,
        '    by_id = {x["id"]: x for x in original if isinstance(x, dict) and x.get("id")}',
        '    try:\n'
        '        from scripts.pulse_editorial_recovery_guard import repair_observer_archive\n'
        '    except ModuleNotFoundError:\n'
        '        from pulse_editorial_recovery_guard import repair_observer_archive\n'
        '    original, repair_status = repair_observer_archive(original)\n'
        '    by_id = {x["id"]: x for x in original if isinstance(x, dict) and x.get("id")}',
        "observer archived contamination")
    s = replace_once(s,
        '                    "article_type": "DOCUMENTO_SENZA_DATI_NUMERICI",',
        '                    "article_type": "DOCUMENTO_SENZA_DATI_NUMERICI",\n'
        '                    "editorial_format": "source_card",',
        "observer source cards")
    s = replace_once(s,
        '        "sources": stats, "other_institutions": "not_yet_connected"',
        '        "sources": stats, "other_institutions": "not_yet_connected",\n'
        '        "editorial_recovery": repair_status',
        "observer audit status")
    s = replace_once(s,
        '    if additions:\n        obj["articles"] = sorted(by_id.values()',
        '    if additions or repair_status["changed"]:\n        obj["articles"] = sorted(by_id.values()',
        "observer save repaired records")
    return s


def apply(repo: Path) -> None:
    repo = repo.resolve()
    if not (repo / '.git').is_dir():
        raise RuntimeError("Target must be a Git checkout: no edits applied")
    radar = repo / 'scripts/update_news_radar.py'
    observer = repo / 'scripts/update_observer_daily.py'
    if not radar.is_file() or not observer.is_file():
        raise RuntimeError("Target lacks current DATA scripts; no edits applied")
    originals = {radar: radar.read_text(encoding='utf-8'),
                 observer: observer.read_text(encoding='utf-8')}
    updated = {radar: patched_radar(originals[radar]),
               observer: patched_observer(originals[observer])}
    # Validate no accidental overwrite before writing any file.
    for relative in FILES_TO_ADD:
        source = PACKAGE / relative
        target = repo / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        if target.exists() and source.read_bytes() != target.read_bytes():
            raise RuntimeError(f"Refusing to overwrite a customized file: {relative}")
    for target, content in updated.items():
        if content != originals[target]:
            target.write_text(content, encoding='utf-8', newline='\n')
            print(f"[OK] Updated: {target.relative_to(repo)}")
    for relative in FILES_TO_ADD:
        source, target = PACKAGE / relative, repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"[OK] Installed: {relative}")
    print('[OK] Only DATA editorial scripts changed; no APK, feeds or workflows touched.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    apply(args.repo)


if __name__ == '__main__':
    main()
