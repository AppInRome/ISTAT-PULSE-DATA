"""Offline regression: publishing news must include its quality audit atomically."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"refresh_daily_safe.py"
spec=importlib.util.spec_from_file_location("refresh_daily_safe",SCRIPT)
safe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(safe)

class NewsPromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.data=self.base/"data"
        self.data.mkdir()
        self.old=safe.DATA
        safe.DATA=self.data
        safe.write_json(self.data/"news_radar_sources.json", {
            "feeds":[{"name":"A","url":"https://a.example/rss"},
                     {"name":"B","url":"https://b.example/rss"}]})
        rows=[{"id":f"PULSE-{i:02}", "published_at":"2026-10-22T07:00:00Z"} for i in range(16)]
        safe.write_json(self.data/"news"/"articles.json",{"generated_at":"2026-10-23T07:00:00Z","articles":rows})
        safe.write_json(self.data/"news"/"index.json",{"generated_at":"2026-10-23T07:00:00Z","oggi":[],"ieri":[],"archivio":[]})
        safe.write_json(self.data/"news"/"candidates.json",{"generated_at":"2026-10-23T07:00:00Z","candidates":[]})

    def tearDown(self):
        safe.DATA=self.old
        self.temp.cleanup()

    def generate(self,path,valid=True):
        work=path/"data"/"news"
        work.mkdir(parents=True,exist_ok=True)
        original=safe.read_json(self.data/"news"/"articles.json")
        safe.write_json(work/"articles.json",original)
        safe.write_json(work/"index.json",{"generated_at":"2026-10-27T09:00:00Z",
                                         "oggi":[],"ieri":[],"archivio":[]})
        safe.write_json(work/"candidates.json",{"generated_at":"2026-10-27T09:00:00Z",
                                               "candidates":[{"status":"radar_fetched","radar":"A"},
                                                             {"status":"radar_error","radar":"B"}]})
        from scripts.pulse_sectional_news import save_indices
        save_indices(original["articles"],safe.read_json(work/"index.json"),work)
        if valid:
            safe.write_json(work/"editorial_quality_status.json",{
                "generated_at":"2026-10-27T09:00:00Z",
                "discovery_feeds_reached":1,
                "daily":{"oggi":{"published":0},"ieri":{"published":0},
                         "archivio":{"published":0}}})
        else:
            safe.write_json(work/"editorial_quality_status.json",{
                "discovery_feeds_reached":99,
                "daily":{"oggi":{},"ieri":{},"archivio":{}}})

    def test_success_promotes_report_and_index_together(self):
        with patch.object(safe,"run_original",side_effect=lambda _s,w,seconds:self.generate(w)):
            result=safe.news_refresh(self.base/"stage")
        self.assertEqual(1,result["feeds_reached"])
        self.assertEqual(1,result["feeds_failed"])
        self.assertEqual(1,safe.read_json(
            self.data/"news"/"editorial_quality_status.json")["discovery_feeds_reached"])

    def test_bad_report_does_not_replace_previous_news(self):
        original=(self.data/"news"/"index.json").read_bytes()
        with patch.object(safe,"run_original",
                          side_effect=lambda _s,w,seconds:self.generate(w,valid=False)):
            with self.assertRaisesRegex(ValueError,"Diagnostica editoriale"):
                safe.news_refresh(self.base/"stage")
        self.assertEqual(original,(self.data/"news"/"index.json").read_bytes())
        self.assertFalse((self.data/"news"/"editorial_quality_status.json").exists())

if __name__=="__main__":
    unittest.main()
