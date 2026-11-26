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

    def test_topic_selection_without_numbers(self):
        for title in ("Il mercato del lavoro cambia", "Famiglie e welfare: nuove prospettive",
                      "Economia italiana: le imprese guardano al futuro",
                      "Istat: nuova indagine sulla popolazione",
                      "Le statistiche del calciomercato secondo Istat"):
            self.assertTrue(radar.source_relevance(title),title)
        for title in ("Calciomercato, arriva il nuovo attaccante",
                      "Gossip, il nuovo amore della star",
                      "Arrestato dopo una rapina",
                      "Nuovo trailer del film", "Il nuovo look della cantante"):
            self.assertFalse(radar.source_relevance(title),title)

    def test_google_search_is_not_automatic_approval(self):
        now=datetime(2026,11,26,15,0,tzinfo=timezone.utc)
        def item(title,url,publisher):
            return {"title":title,"url":url,"publisher":publisher,
                    "published_raw":format_datetime(now-timedelta(minutes=1)),"summary":""}
        feed={"name":"Google News","url":"https://news.google.com/rss/search?q=dati"}
        records=[item("Nuove prospettive per le famiglie","https://example.org/a","Testata A"),
                 item("Nuove prospettive per le famiglie","https://example.net/b","Testata B"),
                 item("Gossip: nuovo amore","https://example.org/c","Testata A")]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.multiple(radar,ROOT=root,ARTICLES=root/"articles.json",
                                INDEX=root/"index.json",CANDIDATES=root/"candidates.json"):
                idx=radar.publish_source_only({},[(feed,records)],[],now)
                self.assertEqual(len(idx["oggi"]),2)
                self.assertEqual(idx["counts"]["rejected_new"],1)
                self.assertEqual(idx["source_topic_policy"],"v2")
                articles=json.loads((root/"articles.json").read_text())["articles"]
                self.assertEqual({a["public_source"]["domain"] for a in articles},{"Testata A","Testata B"})

    def test_licensed_preview_only(self):
        entry={"title":"Titolo statistico","url":"https://www.istat.it/comunicato-stampa/esempio/",
               "summary":"Un testo originale di prova che contiene informazioni statistiche di pubblico interesse."}
        feed={"url":"https://www.istat.it/feed","primary_source":True}
        preview=radar.licensed_source_preview(feed,entry)
        self.assertEqual(preview["source_excerpt_license"],"CC BY 4.0")
        self.assertEqual(preview["source_excerpt"],entry["summary"])
        self.assertEqual(radar.licensed_source_preview(feed,{**entry,"source_rights":"Tutti i diritti riservati"}),{})
        press={**entry,"url":"https://example.org/news/1"}
        self.assertEqual(radar.licensed_source_preview({"url":"https://example.org/feed"},press),{})
        self.assertEqual(radar.licensed_source_preview({"url":"https://news.google.com/rss/search?q=istat"},entry),{})
        self.assertEqual(radar.licensed_source_preview({"url":"https://example.org/feed"},{**press,"source_rights":"https://creativecommons.org/licenses/by/4.0/"})["source_excerpt_license"],"CC BY 4.0")
