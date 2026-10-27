"""Offline editorial tests: data period must never be mistaken for news date."""
import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from scripts.pulse_verified_event_news import augment_with_verified_events

class VerifiedEventEditorialTests(unittest.TestCase):
    def test_independent_verified_article_is_stable_and_honest(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"pulse_events.tsv"
            with path.open("w",encoding="utf8",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=[
                    "id","municipality","scope","validation_status","period",
                    "indicator","analysis","annual","source_url","source_family",
                    "score","patterns"
                ],delimiter="\t")
                writer.writeheader()
                writer.writerow({
                    "id":"clima-test","municipality":"Italia","scope":"GREEN",
                    "validation_status":"SEGNALE PULSE — GREEN",
                    "period":"2025",
                    "indicator":"GREEN · Mobilità sostenibile · Auto elettriche",
                    "analysis":"Unità di misura dichiarata: Valori percentuali.",
                    "annual":"2|5|9.3","source_url":"https://www.istat.it/dati/mobilita.xlsx",
                    "source_family":"ISTAT - Indicatori SDGs","score":"91",
                    "patterns":"RECORD_MAX"
                })
            now=datetime(2026,10,27,13,15,tzinfo=timezone.utc)
            articles={}
            self.assertEqual(1,augment_with_verified_events(articles,path,now))
            self.assertEqual(1,len(articles))
            item=list(articles.values())[0]
            self.assertEqual("2025",item["period_reference"])
            self.assertTrue(item["published_at"].startswith("2026-10-27"))
            self.assertIn("non la data di pubblicazione della fonte",item["summary"])
            self.assertEqual("verified",item["chart_spec"]["status"])
            self.assertEqual(1,len(item["chart_spec"]["data"]))
            self.assertEqual(1,len(item["table_spec"]["rows"]))
            self.assertEqual(0,augment_with_verified_events(articles,path,now))
            self.assertEqual(1,len(articles))

    def test_unvalidated_event_never_generates_public_article(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"pulse_events.tsv"
            path.write_text(
                "id\tscope\tvalidation_status\tperiod\tindicator\tanalysis\tannual\tsource_url\n"
                "bad\tGREEN\tPROMETTENTE — RIVEDERE\t2025\t"
                "Consumo di suolo\tUnità di misura dichiarata: ettari.\t1|2\t"
                "https://example.it/dati.csv\n",encoding="utf8")
            self.assertEqual(0,augment_with_verified_events({},
                             path,datetime(2026,10,27,tzinfo=timezone.utc)))

if __name__=="__main__": unittest.main()
