"""Offline acceptance tests for original 250+ word articles and interactive charts."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.pulse_historical_interactive_export import START, END, build_payload, regenerate

ROOT = Path(__file__).resolve().parents[1]


class HistoricalInteractiveTests(unittest.TestCase):
    def test_all_historical_articles_are_long_and_numeric(self):
        data = json.loads((ROOT/"data/news/automatic_features.json").read_text(encoding="utf-8"))
        result = build_payload(data)
        self.assertGreaterEqual(len(result["articles"]), 1)
        for a in result["articles"]:
            with self.subTest(article=a["id"]):
                self.assertGreaterEqual(len((" ".join([a["lead"], *a["paragraphs"]])).split()), 250)
                self.assertGreaterEqual(len(a["data"]), 2)
                self.assertTrue(a["source"].startswith("https://"))

    def test_html_has_embedded_full_articles_and_interactivity(self):
        html = (ROOT/"docs/PULSE_STORICO_INTERATTIVO.html").read_text(encoding="utf-8")
        left = html.index(START) + len(START)
        right = html.index(END, left)
        encoded = json.loads(html[left:right])
        feed = json.loads((ROOT/"data/news/automatic_features.json").read_text(encoding="utf-8"))
        actual = build_payload(feed)
        self.assertEqual(encoded, actual)
        self.assertIn('id="sortValue"', html)
        self.assertIn('id="sortPeriod"', html)
        self.assertIn('id="last5"', html)
        self.assertIn('id="bars"', html)
        self.assertIn('function adjacent', html)
        self.assertNotIn("api.openai.com", html)

    def test_generator_is_deterministic(self):
        source = ROOT/"docs/PULSE_STORICO_INTERATTIVO.html"
        with TemporaryDirectory() as temp:
            copy = Path(temp)/"offline.html"
            copy.write_bytes(source.read_bytes())
            count = regenerate(ROOT/"data/news/automatic_features.json", copy)
            self.assertGreaterEqual(count, 1)
            first = copy.read_bytes()
            regenerate(ROOT/"data/news/automatic_features.json", copy)
            self.assertEqual(first, copy.read_bytes())


if __name__ == "__main__":
    unittest.main()
