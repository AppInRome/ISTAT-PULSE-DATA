import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch
from scripts import update_news_radar as radar

class SourceStreamTest(unittest.TestCase):
    def test_titles_without_numbers_and_archive(self):
        now=datetime(2026,11,26,15,0,tzinfo=timezone.utc)
        def entry(n,days=0):
            return {"title":f"Lavoro e famiglie: nuove prospettive {chr(65+n)}",
                    "url":f"https://example.org/article/{n}",
                    "published_raw":format_datetime(now-timedelta(days=days,minutes=1)),
                    "summary":"","publisher":"Testata"}
        feed={"name":"Ricerca tematica","url":"https://news.google.com/rss/search?q=lavoro"}
        records=[entry(n) for n in range(24)]
        records += [entry(24,1),entry(25,2),entry(0)]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.multiple(radar,ROOT=root,ARTICLES=root/"articles.json",
                                INDEX=root/"index.json",CANDIDATES=root/"candidates.json"):
                idx=radar.publish_source_only({},[(feed,records)],[],now)
                self.assertEqual(len(idx["oggi"]),24)
                self.assertEqual(len(idx["ieri"]),1)
                self.assertEqual(len(idx["archivio"]),1)
                articles=json.loads((root/"articles.json").read_text())["articles"]
                self.assertEqual(len(articles),26)
                self.assertTrue(all(not a.get("pulse_article_body") and not a.get("ai_article") for a in articles))
                self.assertTrue(all(a["headline"]==a["reported_headline"] for a in articles))
                # Empty refresh preserves the archive rather than erasing it.
                retained=radar.publish_source_only({a["id"]:a for a in articles},[],[],now)
                self.assertEqual(retained["oggi"],idx["oggi"])
