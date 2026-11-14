"""Regression: all 34 real source-locked PULSE articles preserve original facts.

No synthetic fixtures are published; no AI, network or Android compilation.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from scripts import pulse_story_composer as composer

ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/"data/news/automatic_features.json"


class ComposerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.articles=json.loads(CORPUS.read_text(encoding="utf-8"))["articles"]

    def test_actual_feed_34_articles_have_verified_nonformulaic_readings(self):
        created=[]
        for item in self.articles:
            with self.subTest(item=item["id"]):
                orig=deepcopy(item)
                converted=composer.attach(item)
                self.assertEqual(item,orig)
                self.assertIsNot(converted,item)
                self.assertEqual(
                    {k:v for k,v in converted.items() if k!="editorial_story"},
                    item)
                story=converted["editorial_story"]
                self.assertEqual(story["period_reference"],item["period_reference"])
                self.assertEqual(story["source_sha256"],
                                 item["source_documents"][0]["sha256"])
                self.assertLessEqual(len(story["headline"]),110)
                self.assertEqual(story["schema"],composer.SCHEMA)
                self.assertTrue(50 <= len(story["lead"]) <= 700)
                self.assertTrue(3 <= len(story["sections"]) <= 5)
                for section in story["sections"]:
                    self.assertTrue(5 <= len(section["heading"]) <= 80)
                    self.assertTrue(60 <= len(section["text"]) <= 1300)
                # Android v0.14 only displays the optional story when these
                # source-bound conditions are all satisfied.
                self.assertTrue(story["original_text_preserved"])
                self.assertNotIn("Il dato più recente disponibile",story["lead"])
                self.assertNotIn("i dati di",story["headline"])
                self.assertTrue(story["source_locked"])
                self.assertEqual(composer.attach(converted),converted)
                created.append(story)
        self.assertGreaterEqual(len(created),30)
        self.assertGreater(len({x["headline"] for x in created}),20)

    def test_tampered_chart_or_table_never_gets_new_editorial_presentation(self):
        original=deepcopy(self.articles[0])
        for key in ("chart_spec","table_spec","source_documents","automatic_review"):
            changed=deepcopy(original)
            if key=="chart_spec":
                changed[key]["data"][-1]["value"]+=99
            elif key=="table_spec":
                changed[key]["rows"][-1][1]+=99
            elif key=="source_documents":
                changed[key][0]["sha256"]="0"*64
            else:
                changed[key]["passed"]=False
            self.assertIsNone(composer.compose(changed),key)

    def test_non_adjacent_does_not_claim_monthly_change(self):
        original=deepcopy(next(x for x in self.articles
                if x["public_source"]["domain"]=="INPS"))
        for where in (original["verified_series_relevant"][0]["observations"],
                      original["chart_spec"]["data"],
                      original["table_spec"]["rows"]):
            if isinstance(where[-2],dict):
                where[-2]["period"]="2025-05"
            else:
                where[-2][0]="2025-05"
        story=composer.compose(original)
        self.assertIsNotNone(story)
        self.assertIn("non sono consecutivi",story["lead"])
        self.assertNotIn("Lo scarto è",story["lead"])

    def test_percentage_points_not_relative_growth(self):
        original=next(x for x in self.articles if x["topic"]=="CASA")
        story=composer.compose(original)
        self.assertIsNotNone(story)
        self.assertIn("0,4 punti percentuali",story["lead"])
        self.assertIn("24,3%",story["lead"])
        self.assertIn("23,9%",story["lead"])
        self.assertNotIn("0,4% ",story["lead"])


if __name__ == "__main__":
    unittest.main()
