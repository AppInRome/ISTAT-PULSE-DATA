"""Synthetic regression tests for the live PULSE DATA publication gate."""
import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from scripts.pulse_data_integrity import inspect

NOW = datetime(2026,11,10,17,0,tzinfo=timezone.utc)
URL = "https://www.istat.it/comunicato-stampa/test-statistico/"

class FeedIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data=Path(self.temp.name)
        (self.data/"news").mkdir()
        self.article={"id":"PULSE-EX","headline":"Dato della fonte ufficiale",
            "published_at":"2026-11-10T10:00:00+00:00",
            "publication_status":"published",
            "public_source":{"url":URL,"role":"primary_statistical_source"}}
        self.write("news/articles.json",{"generated_at":NOW.isoformat(),"articles":[self.article]})
        self.idx={"generated_at":NOW.isoformat(),"counts":{"oggi":1,"ieri":0,"archivio":0},
                  "oggi":["PULSE-EX"],"ieri":[],"archivio":[]}
        self.write("news/index.json",self.idx)
        for section in ("green","territori"):
            self.write(f"news/{section}_index.json",
                {"generated_at":NOW.isoformat(),"counts":{"oggi":1,"ieri":0,"archivio":0},
                 "oggi":["PULSE-EX"],"ieri":[],"archivio":[]})
        self.write("news/observer_articles.json",{"articles":[{
            "id":"OBS-X","observer":"ISTAT","headline":"Rapporto","published_at":NOW.isoformat(),
            "pulse_article_body":["Riepilogo con fonte"],"public_source":{"url":URL}}]})
        with (self.data/"pulse_events.tsv").open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["id","source_family","source_url","indicator","period","scope"],
                                  delimiter="\t",lineterminator="\n")
            writer.writeheader()
            writer.writerow({"id":"E1","source_family":"ISTAT","source_url":URL,
                             "indicator":"Tasso","period":"2026-Q2","scope":"GREEN"})
        hash_value=hashlib.sha256((self.data/"pulse_events.tsv").read_bytes()).hexdigest()
        self.write("pulse_manifest.json",{"feed_sha256":hash_value,"feed_events":1})
        self.write("pulse_observations_manifest.json",{})
        self.write("sources_catalog.json",{"sources":[{"name":"ISTAT","url":URL}]})
    def write(self,path,obj):
        p=self.data/path;p.parent.mkdir(exist_ok=True,parents=True)
        p.write_text(json.dumps(obj),encoding="utf-8")
    def result(self):return inspect(self.data,now=NOW)
    def test_consistent_feed(self):
        self.assertTrue(self.result()["passed"])
    def test_reject_missing_article(self):
        self.idx["oggi"]=["UNKNOWN"];self.write("news/index.json",self.idx)
        self.assertFalse(self.result()["passed"])
    def test_reject_draft_in_public_index(self):
        self.article["publication_status"]="draft"
        self.write("news/articles.json",{"generated_at":NOW.isoformat(),"articles":[self.article]})
        self.assertFalse(self.result()["passed"])
    def test_reject_mismatched_generation(self):
        self.idx["generated_at"]="2026-11-09T01:00:00+00:00"
        self.write("news/index.json",self.idx)
        self.assertFalse(self.result()["passed"])
    def test_reject_green_cross_bucket(self):
        self.write("news/green_index.json",{"generated_at":NOW.isoformat(),
            "counts":{"oggi":0,"ieri":1,"archivio":0},
            "oggi":[],"ieri":["PULSE-EX"],"archivio":[]})
        self.assertFalse(self.result()["passed"])
    def test_reject_manifest_hash_mismatch(self):
        self.write("pulse_manifest.json",{"feed_sha256":"0"*64,"feed_events":1})
        self.assertFalse(self.result()["passed"])
    def test_reject_http_source_link(self):
        self.article["public_source"]["url"]="http://example.com/"
        self.write("news/articles.json",{"generated_at":NOW.isoformat(),"articles":[self.article]})
        self.assertFalse(self.result()["passed"])
    def test_rome_date(self):
        self.article["published_at"]="2026-11-09T23:50:00+00:00"
        self.write("news/articles.json",{"generated_at":NOW.isoformat(),"articles":[self.article]})
        self.assertTrue(self.result()["passed"])

if __name__=="__main__":unittest.main()
