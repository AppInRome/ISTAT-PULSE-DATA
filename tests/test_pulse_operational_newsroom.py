"""PULSE newsroom integration unit tests; never call a real AI or publish fixture."""
import copy
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import pulse_editorial_engine_v1 as engine
from scripts.pulse_auto_sources import detect_manifests
from scripts.pulse_operational_newsroom import analyze_verified, approve_and_merge

CSV = ("Indicatore;Territorio;Popolazione;Unita;Frequenza;Anno;Valore\n"
       "Tasso sperimentale;Italia;Persone 15-64 anni;%;Annuale;2022;10,0\n"
       "Tasso sperimentale;Italia;Persone 15-64 anni;%;Annuale;2023;11,2\n"
       "Tasso sperimentale;Italia;Persone 15-64 anni;%;Annuale;2024;12,3\n")
SRC = "https://www.istat.it/comunicato-stampa/esempio/"
DATA_URL = "https://www.istat.it/wp-content/uploads/esempio.csv"


class OperatingNewsroomTests(unittest.TestCase):
    def make_evidence(self):
        return detect_manifests(SRC, DATA_URL, CSV.encode())[0]["evidence"]

    def test_article_data_and_chart_created_from_real_parsed_rows(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            evidence=self.make_evidence()
            file=p/"source_evidence.json"
            file.write_text(json.dumps(evidence),encoding="utf-8")
            result=analyze_verified(file,p/"result",allow_llama=False)
            self.assertTrue(result["graph_and_table_prepared"])
            self.assertEqual(result["llama"],"disabled")
            self.assertTrue((p/"result"/"evidence_report"/"index.html").exists())
            with (p/"result"/"verified_table.csv").open(encoding="utf-8") as h:
                obs=list(csv.DictReader(h))
            self.assertEqual([o["period"] for o in obs],["2022","2023","2024"])
            self.assertEqual(obs[-1]["value"],"12.3")

    def test_no_approved_casefiles_no_feed_write(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/"articles.json").write_text(json.dumps({"articles":[{"id":"OLDER"}]}))
            (p/"index.json").write_text(json.dumps({"oggi":[],"ieri":[],"archivio":["OLDER"]}))
            old=(p/"articles.json").read_bytes()
            articles,index,count=approve_and_merge(p/"approved",p/"articles.json",p/"index.json")
            self.assertEqual(count,0)
            self.assertEqual(len(articles["articles"]),1)
            self.assertEqual((p/"articles.json").read_bytes(),old)

    def test_unreviewed_candidate_rejected_before_app_feed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/"articles.json").write_text(json.dumps({"articles":[]}))
            (p/"index.json").write_text(json.dumps({"oggi":[],"ieri":[],"archivio":[]}))
            (p/"approved").mkdir()
            casefile={"evidence":self.make_evidence(),"draft":{"publication_status":"draft"},
                      "approval":{"decision":"publish"}}
            (p/"approved"/"fake.json").write_text(json.dumps(casefile))
            with self.assertRaises(ValueError):
                approve_and_merge(p/"approved",p/"articles.json",p/"index.json")


if __name__ == "__main__":
    unittest.main()
