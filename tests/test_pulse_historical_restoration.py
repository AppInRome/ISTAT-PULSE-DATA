"""Regression: PULSE historical original longform is primary, no paid AI pipeline.

The saved official articles are independently audited source snapshots, not
copyrighted newspaper texts. Press headlines without source evidence remain
labelled press radar items and are NOT automatically expanded.
"""
from pathlib import Path
import json
import unittest

from scripts import pulse_deterministic_writer as historical

ROOT=Path(__file__).resolve().parents[1]

class HistoricalRestoration(unittest.TestCase):
    def test_historical_writer_recovered(self):
        self.assertTrue(callable(historical.write_verified_article))
        self.assertIn("historical_PULSE_deterministic_restored_v1",
                      (ROOT/"scripts/pulse_deterministic_writer.py").read_text())

    def test_no_active_paid_ai_schedule(self):
        workflow=(ROOT/".github/workflows/pulse-italia-newsroom.yml").read_text()
        self.assertIn("--no-ai",workflow)
        self.assertNotIn("secrets.OPENAI_API_KEY",workflow)
        self.assertNotIn("PULSE_MISTRAL_API_KEY",workflow)
        self.assertFalse((ROOT/".github/workflows/pulse-luna-publish.yml").exists())

    def test_complete_published_articles_retain_numeric_series(self):
        feed=json.loads((ROOT/"data/news/automatic_features.json").read_text())
        self.assertEqual(feed["schema"],"pulse-automatic-official-features-v1")
        self.assertGreaterEqual(len(feed["articles"]),1)
        for article in feed["articles"]:
            with self.subTest(article=article["id"]):
                review=article["automatic_review"]
                self.assertTrue(review["passed"])
                self.assertFalse(review["model_used"])
                self.assertNotIn("luna_story",article)
                paragraphs=article["pulse_article_body"]
                text=" ".join([article["summary"]]+[p["text"] for p in paragraphs])
                self.assertGreaterEqual(len(text.split()),250)
                self.assertGreaterEqual(len(paragraphs),4)
                series=article["verified_series_relevant"][0]["observations"]
                self.assertEqual(len(series),len(article["chart_spec"]["data"]))
                self.assertEqual(len(series),len(article["table_spec"]["rows"]))

if __name__=="__main__":
    unittest.main()
