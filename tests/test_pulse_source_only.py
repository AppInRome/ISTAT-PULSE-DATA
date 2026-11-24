"""Offline regression for PULSE source-only publication. No API, no AI."""
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scripts import update_news_radar as radar


class SourceOnlyTests(TestCase):
    def test_preserve_press_history_and_publish_true_official_rss_headline(self):
        now=datetime(2026,11,24,10,0,tzinfo=timezone.utc)
        old={
            "id":"PULSE-MEDIA-OLD1","headline":"ISTAT: un rapporto statistico sul lavoro",
            "published_at":"2026-11-23T09:00:00+00:00",
            "publication_status":"published","origin_kind":"pulse_media_radar",
            "editorial_status":"journalistic_sourced",
            "publication_tier":"reported_by_media_pending_primary_verification",
            "topic":"LAVORO","territories":["italia"],
            "public_source":{"url":"https://news.google.com/rss/articles/valid",
                             "domain":"Testata","role":"journalistic_source"},
            "pulse_article_body":[{"text":"Testo inventato PULSE"}],
            "summary":"Riassunto PULSE",
            "chart_spec":{"status":"requires_primary_source"},
        }
        fabricated=dict(old,id="PULSE-DATA-FAKE",origin_kind="generated")
        feed=[({"primary_source":True,"name":"ISTAT"},
               [{"title":"Pubblicazione ufficiale ISTAT sul mercato del lavoro",
                 "url":"https://www.istat.it/comunicato-stampa/mercato-del-lavoro/",
                 "summary":"","published_raw":"Tue, 24 Nov 2026 09:00:00 +0000"}])]
        with TemporaryDirectory() as temp:
            root=Path(temp)/"news"
            with patch.object(radar,"ROOT",root), patch.object(radar,"ARTICLES",root/"articles.json"), \
                 patch.object(radar,"INDEX",root/"index.json"), patch.object(radar,"CANDIDATES",root/"candidates.json"):
                radar.publish_source_only({old["id"]:old,fabricated["id"]:fabricated},
                                          feed, [], now)
                payload=json.loads((root/"articles.json").read_text())
                index=json.loads((root/"index.json").read_text())
                headlines=payload["articles"]
                self.assertEqual(len(headlines),2)
                self.assertEqual({x["id"] for x in headlines},
                                 set(index["oggi"]+index["ieri"]+index["archivio"]))
                official=next(x for x in headlines if x["id"].startswith("PULSE-OFFICIAL-"))
                self.assertEqual(official["headline"],feed[0][1][0]["title"])
                self.assertEqual(official["published_at"],"2026-11-24T09:00:00+00:00")
                self.assertEqual(official["public_source"]["url"],feed[0][1][0]["url"])
                self.assertFalse(any(x.get("pulse_article_body") for x in headlines))
                self.assertFalse(any(x.get("summary") for x in headlines))
                self.assertFalse(any(x.get("chart_spec",{}).get("status")=="verified" for x in headlines))
                self.assertEqual(next(x for x in headlines if x["id"]==old["id"])["published_at"],old["published_at"])

    def test_missing_feed_does_not_erase_existing_press(self):
        now=datetime(2026,11,24,10,0,tzinfo=timezone.utc)
        old={"id":"PULSE-MEDIA-EXISTING","origin_kind":"pulse_media_radar",
             "published_at":"2026-11-22T10:00:00+00:00","headline":"Notizia ufficiale statistica di archivio",
             "publication_status":"published","topic":"ECONOMIA",
             "public_source":{"role":"journalistic_source","url":"https://news.google.com/rss/articles/valid"}}
        with TemporaryDirectory() as temp:
            root=Path(temp)/"news"
            with patch.object(radar,"ROOT",root),patch.object(radar,"ARTICLES",root/"articles.json"), \
                 patch.object(radar,"INDEX",root/"index.json"),patch.object(radar,"CANDIDATES",root/"candidates.json"):
                radar.publish_source_only({old["id"]:old},[],[{"status":"radar_error"}],now)
                self.assertEqual(json.loads((root/"index.json").read_text())["counts"]["archivio"],1)
