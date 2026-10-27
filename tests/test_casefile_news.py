"""BES 2026: original newsroom casefile and source/date integrity."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.pulse_casefile_news import add_verified_casefiles

class BesCasefileTests(unittest.TestCase):
    def setUp(self):
        self.working=tempfile.TemporaryDirectory()
        self.addCleanup(self.working.cleanup)
        self.path=Path(self.working.name)/"casefile.json"
        self.case={
            "id":"PULSE-BES-20261026",
            "source_publication_day":"2026-10-26",
            "published_at":"2026-10-26T08:00:00+00:00",
            "statistical_primary":"https://www.istat.it/comunicato-stampa/nota-stampa-rapporto-bes-edizione-2026/",
            "discovered_from":"https://www.corriere.it/economia/finanza/some-story.shtml",
            "chart_categories":[["Migliorano",54],["Stabili",55],["Peggiorano",23]],
            "denominator":132,"headline":"BES 2026: un'analisi originale",
            "summary":"Istat misura il benessere con indicatori comparabili.",
            "body":[{"heading":"Andamento","text":"Testo proprio PULSE."}]
        }
        self.today=datetime(2026,10,27,tzinfo=timezone.utc)

    def write(self):
        self.path.write_text(json.dumps({"version":1,"cases":[self.case]}),encoding="utf8")

    def test_bes_is_yesterday_and_chart_sums_to_132(self):
        self.write()
        articles={}
        self.assertEqual(1,add_verified_casefiles(articles,self.path,self.today))
        article=next(iter(articles.values()))
        self.assertEqual("2026-10-26",article["published_at"][:10])
        self.assertEqual(132,sum(x["value"] for x in article["chart_spec"]["data"]))
        self.assertEqual(3,len(article["table_spec"]["rows"]))
        self.assertEqual("verified",article["chart_spec"]["status"])
        self.assertEqual("Redazione PULSE",article["byline"])
        self.assertEqual("istat.it",article["public_source"]["domain"])
        self.assertEqual(0,add_verified_casefiles(articles,self.path,self.today))

    def test_false_total_blocked(self):
        self.case["denominator"]=150
        self.write()
        with self.assertRaises(ValueError):add_verified_casefiles({},self.path,self.today)

    def test_nonofficial_or_future_publication_blocked(self):
        self.case["statistical_primary"]="https://attacker.test/fake-statistics"
        self.write()
        with self.assertRaises(ValueError):add_verified_casefiles({},self.path,self.today)
        self.case["statistical_primary"]="https://www.istat.it/nota"
        self.case["published_at"]="2026-11-26T08:00:00+00:00"
        self.case["source_publication_day"]="2026-11-26"
        self.write()
        with self.assertRaises(ValueError):add_verified_casefiles({},self.path,self.today)

if __name__=="__main__":
    unittest.main()
