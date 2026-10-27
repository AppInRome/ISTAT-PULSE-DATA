"""Offline regression: newspaper and institutional RSS are all scanned before research."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

from scripts import update_news_radar as radar

class NewsRadarCoverageTests(unittest.TestCase):
    def test_scans_all_available_sources(self):
        when=format_datetime(datetime.now(timezone.utc)-timedelta(hours=2))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cfg=root/"sources.json"
            art=root/"articles.json"
            idx=root/"index.json"
            cand=root/"candidates.json"
            cfg.write_text(json.dumps({
                "feeds":[{"name":n,"url":f"https://rss.example.org/{i}"}
                         for i,n in enumerate(("Stampa nazionale","Stampa regionale",
                                               "Centro ricerche", "Fonti pubbliche"))],
                "official_domains":[],
                "entity_domain_hints":{},
                "institutional_producers":[]
            }), encoding="utf8")
            def feed(url):
                name=url.rsplit("/",1)[-1]
                return [{"title":f"Rapporto statistico {name}: lavoro +3,5% nel 2026",
                         "url":f"https://newspaper.example.org/article/{name}",
                         "summary":"Dati di occupazione Italia: 3,5% nel 2026",
                         "published_raw":when}]
            old=(radar.ROOT,radar.CFG,radar.ARTICLES,radar.CANDIDATES,radar.INDEX)
            try:
                radar.ROOT=root
                radar.CFG=cfg
                radar.ARTICLES=art
                radar.CANDIDATES=cand
                radar.INDEX=idx
                with patch.object(radar,"rss_items",side_effect=feed), \
                     patch.object(radar,"article_probe",return_value={}), \
                     patch.object(radar,"resolve_primary",return_value=None), \
                     patch.object(radar,"curated_story_for",return_value=None):
                    radar.main()
                found=json.loads(cand.read_text())["candidates"]
                scanned=[x["radar"] for x in found if x.get("status")=="radar_fetched"]
                self.assertEqual(4,len(scanned),found)
                self.assertEqual(set(scanned),{
                    "Stampa nazionale","Stampa regionale","Centro ricerche","Fonti pubbliche"})
                audit=json.loads((root/"editorial_quality_status.json").read_text())
                self.assertEqual(4,audit["discovery_feeds_reached"])
                self.assertEqual(0,audit["discovery_feeds_failed"])
                published=json.loads(idx.read_text())["counts"]["oggi"]
                self.assertEqual(4,published)
                self.assertEqual(4,audit["daily"]["oggi"]["media_reports_not_primary_verified"])
                self.assertEqual(0,audit["daily"]["oggi"]["with_verified_chart"])
            finally:
                radar.ROOT,radar.CFG,radar.ARTICLES,radar.CANDIDATES,radar.INDEX=old

if __name__ == "__main__":
    unittest.main()
