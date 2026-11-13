from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / 'tools/applica_patch.py'
spec = importlib.util.spec_from_file_location('pulse_recovery_patcher', TOOL)
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

RADAR = '''from pathlib import Path
ROOT=Path('data/news')
def main():
    by_id={}
    article={'verification_tier':'verified_comparable_series'}
    if True:
        if True:
            if article.get("verification_tier")=="verified_comparable_series":
                try:
                    from scripts.pulse_ai_newsroom import attempt_ai_edition
                except ModuleNotFoundError:
                    from pulse_ai_newsroom import attempt_ai_edition
                article=attempt_ai_edition(article)
            pass  # other article logic
    arts=sorted(by_id.values(),key=lambda x:x.get("published_at",""),reverse=True)
    quality={}
    (ROOT/"editorial_quality_status.json").write_text('test')
# imports pulse_ai_newsroom and pulse_original_editorial
'''
OBSERVER = '''from pathlib import Path
ARCHIVE=Path('archive')
def update(archive: Path = ARCHIVE):
    original=[]
    by_id = {x["id"]: x for x in original if isinstance(x, dict) and x.get("id")}
    item = {
                    "article_type": "DOCUMENTO_SENZA_DATI_NUMERICI",
                    "verification_method":"official_rss_link_and_publication_date"}
    stats={}
    new=0
    status={
        "sources": stats, "other_institutions": "not_yet_connected"
    }
    additions=0
    obj={}
    if additions:
        obj["articles"] = sorted(by_id.values(),key=lambda x:x.get('id',''))
'''


class PatcherTests(unittest.TestCase):
    def test_patches_modern_anchors_and_remains_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'.git').mkdir()
            (root/'scripts').mkdir()
            (root/'scripts/update_news_radar.py').write_text(RADAR,encoding='utf-8')
            (root/'scripts/update_observer_daily.py').write_text(OBSERVER,encoding='utf-8')
            patcher.apply(root)
            actual=(root/'scripts/update_news_radar.py').read_text()
            self.assertNotIn('article=attempt_ai_edition(article)',actual)
            self.assertIn('audit_news_archive',actual)
            self.assertIn('editorial_recovery',actual)
            ast.parse(actual)
            actual_observer=(root/'scripts/update_observer_daily.py').read_text()
            self.assertIn('repair_observer_archive',actual_observer)
            self.assertIn('"editorial_format": "source_card"',actual_observer)
            ast.parse(actual_observer)
            before=(actual,actual_observer)
            patcher.apply(root)
            self.assertEqual(before,((root/'scripts/update_news_radar.py').read_text(),
                                     (root/'scripts/update_observer_daily.py').read_text()))

    def test_unknown_sources_refused_without_touching_any_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'.git').mkdir()
            (root/'scripts').mkdir()
            (root/'scripts/update_news_radar.py').write_text('old code')
            (root/'scripts/update_observer_daily.py').write_text(OBSERVER)
            with self.assertRaises(RuntimeError):
                patcher.apply(root)
            self.assertEqual((root/'scripts/update_news_radar.py').read_text(),'old code')
            self.assertFalse((root/'scripts/pulse_editorial_recovery_guard.py').exists())


if __name__=='__main__':
    unittest.main()
