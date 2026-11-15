"""PULSE Luna: safety checks run without using or exposing OpenAI credentials."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import pulse_luna_publisher as luna


def fixture():
    obs = [{"period": "2021", "value": 73.6},
           {"period": "2022", "value": 72.9},
           {"period": "2023", "value": 73.9},
           {"period": "2024", "value": 75.5},
           {"period": "2025", "value": 73.7}]
    return {
        "id": "PULSE-DATA-TEST",
        "publication_status": "published",
        "editorial_format": "deterministic_source_locked_auto_audited",
        "publication_tier": "verified_official_deterministic",
        "public_source": {"role": "primary_statistical_source", "url": "https://ec.europa.eu/eurostat"},
        "source_documents": [{"sha256": "b" * 64}],
        "automatic_review": {
            "passed": True, "model_used": False, "evidence_sha256": "a" * 64,
            "original_source_sha256": "b" * 64
        },
        "verified_series_relevant": [{
            "verified": True, "indicator": "Buona salute percepita",
            "territory": "Italia", "population": "Totale", "unit": "%",
            "observations": obs
        }],
        "period_reference": "2025",
        "topic": "SALUTE"
    }


def story(paragraph):
    # Enough words for normal-length article validation.
    return {"title": "Buona salute percepita in Italia, i dati ufficiali al 2025",
            "lead": "La serie completa Eurostat descrive il cambiamento della salute percepita in Italia nel periodo osservato.",
            "paragraphs": [paragraph + " " + ("Il confronto richiede cautela metodologica. " * 12)] * 4}


class TestPulseLuna(unittest.TestCase):
    def test_eligibility(self):
        self.assertTrue(luna.eligible(fixture()))
        a = fixture()
        a["automatic_review"]["passed"] = False
        self.assertFalse(luna.eligible(a))

    def test_full_historical_dossier(self):
        d = luna.dossier(fixture())
        self.assertEqual(len(d["full_verified_series"][0]["observations"]), 5)
        self.assertEqual(d["full_verified_series"][0]["observations"][0]["period"], "2021")

    def test_reversed_health_comparison_is_blocked(self):
        a = fixture()
        bad = story("La quota è più alta nel 2025 rispetto al 2023.")
        self.assertIn("reversed_comparison", luna.validate(a, bad))

    def test_invalid_latest_record_is_blocked(self):
        a = fixture()
        bad = story("Nel 2025 la quota raggiunge il massimo storico.")
        self.assertIn("latest_not_historical_max", luna.validate(a, bad))

    def test_unknown_number_is_blocked(self):
        a = fixture()
        bad = story("Nel 2025 la percentuale supera il 91,111%.")
        self.assertIn("unsupported_number", luna.validate(a, bad))

    def test_missing_key_never_uses_ai_and_preserves_feed(self):
        a = fixture()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            feed = root / "feed.json"
            feed.write_text(json.dumps({"schema": "pulse-automatic-official-features-v1",
                                        "articles": [a]}), encoding="utf-8")
            before = feed.read_bytes()
            status = luna.run(feed, root / "ledger.json", root / "status.json", "")
            self.assertEqual(before, feed.read_bytes())
            self.assertFalse(status["enabled"])
            self.assertFalse(status["is_actual_openai_prepaid_balance"])

    def test_verified_ai_story_is_not_recharged(self):
        a = fixture()
        a["luna_story"] = {"schema": "pulse-luna-story-v1", "passed": True,
                           "source_evidence_sha256": "a" * 64}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            feed = root / "feed.json"
            feed.write_text(json.dumps({"schema": "pulse-automatic-official-features-v1",
                                        "articles": [a]}), encoding="utf-8")
            with patch.object(luna, "generate", side_effect=AssertionError("API called twice")):
                status = luna.run(feed, root / "ledger.json", root / "status.json", "dummy")
            self.assertEqual(status["articles_ai_skipped_unchanged"], 1)
            self.assertEqual(status["requests_this_run"], 0)


if __name__ == "__main__":
    unittest.main()
