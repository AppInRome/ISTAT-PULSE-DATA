"""PULSE Italia official-data journalism stack tests. Synthetic observations only."""
import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pulse_data_story_stack import (
    exact_verified_csv, source_trace, pipeline, as_float,
    run_data_analyst, run_dstory, run_data2story_inspector,
)

MANIFEST = {
    "source_url": "https://www.istat.it/",
    "dataset_url": "https://www.istat.it/dataset-prova.csv",
    "publisher": "ISTAT", "topic": "LAVORO",
    "schema": {
        "format": "csv", "period_column": "Anno", "value_column": "Misura",
        "dimensions": {"Indicatore": "Quota illustrativa", "Territorio": "Italia",
                       "Popolazione": "Persone 14 anni e piu", "Unita": "%",
                       "Frequenza": "Annuale"},
        "semantic_columns": {"indicator": "Indicatore", "territory": "Territorio",
                             "population": "Popolazione", "unit": "Unita",
                             "frequency": "Frequenza"}
    }
}
DATA = (
    "Indicatore;Territorio;Popolazione;Unita;Frequenza;Anno;Misura\n"
    "Quota illustrativa;Italia;Persone 14 anni e piu;%;Annuale;2022;10,0\n"
    "Quota illustrativa;Italia;Persone 14 anni e piu;%;Annuale;2023;12,1\n"
    "Quota illustrativa;Italia;Persone 14 anni e piu;%;Annuale;2024;13,2\n"
    "Quota illustrativa;Francia;Persone 14 anni e piu;%;Annuale;2024;88,8\n"
)


class StackTests(unittest.TestCase):
    def test_numeric_guard(self):
        self.assertEqual(as_float("12.5"), 12.5)
        with self.assertRaises(ValueError):
            as_float("Infinity")

    def test_export_only_verified_rows(self):
        from scripts.pulse_editorial_engine_v1 import extract
        e = extract(MANIFEST, DATA.encode())
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "verified.csv"
            exact_verified_csv(e, p)
            with p.open(encoding="utf8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[-1]["period"], "2024")
            self.assertEqual(rows[-1]["value"], "13.2")
            self.assertFalse(any("88.8" in str(x) for x in rows))

    def test_source_trace_has_document_and_rows(self):
        from scripts.pulse_editorial_engine_v1 import extract
        e = extract(MANIFEST, DATA.encode())
        with tempfile.TemporaryDirectory() as td:
            p = source_trace(e, None, Path(td))
            self.assertTrue((p / "analyst.json").exists())
            self.assertTrue((p / "detective.json").exists())
            html = (p / "index.html").read_text(encoding="utf-8")
            self.assertIn('data-ana="ana_01"', html)
            self.assertIn("13.2", html)
            self.assertIn("www.istat.it", html)
            self.assertNotIn("88.8", html)

    def test_no_external_dependency_is_disclosed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            self.assertEqual(run_data_analyst(None, p / "a.csv", p, "")["status"], "not_configured")
            self.assertEqual(run_dstory(None, p / "a.csv", p, "")["status"], "not_configured")
            self.assertEqual(run_data2story_inspector(None, p)["status"], "not_configured")

    def test_missing_dependency_not_presented_as_complete(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            self.assertEqual(run_data_analyst(p / "404.py", p / "a.csv", p, "")["status"], "missing_external_tool")
            self.assertEqual(run_data2story_inspector(p / "404", p)["status"], "missing_external_tool")

    def test_pipeline_offline_without_llm(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            manifest = home / "manifest.json"
            manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
            source = home / "official.csv"
            source.write_text(DATA, encoding="utf-8")
            result = pipeline(manifest, source, home / "out", ai_mode="none")
            self.assertEqual(result["status"], "research_artifacts_only")
            self.assertEqual(result["observations"], 3)
            self.assertFalse(result["publish"])
            self.assertEqual(result["ai"]["status"], "disabled")
            self.assertTrue((home / "out" / "evidence.json").is_file())
            self.assertFalse((home / "out" / "llama_draft.json").exists())
            self.assertTrue((home / "out" / "data2story_trace" / "index.html").is_file())

    def test_ai_unconfigured_never_called(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            manifest = home / "manifest.json"
            manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
            source = home / "official.csv"
            source.write_text(DATA, encoding="utf-8")
            with patch.dict(os.environ, {
                "PULSE_LLM_API_KEY": "", "PULSE_LLM_ENDPOINT": "", "PULSE_LLM_MODEL": ""}):
                with patch("scripts.pulse_editorial_engine_v1.call_model") as call:
                    result = pipeline(manifest, source, home / "out", ai_mode="llama")
                    call.assert_not_called()
            self.assertEqual(result["ai"]["status"], "credentials_absent_not_called")

    def test_foreign_manifest_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            bad = json.loads(json.dumps(MANIFEST))
            bad["schema"]["dimensions"]["Territorio"] = "Francia"
            manifest = home / "bad.json"
            manifest.write_text(json.dumps(bad), encoding="utf-8")
            source = home / "official.csv"
            source.write_text(DATA, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside_italian"):
                pipeline(manifest, source, home / "out", ai_mode="none")

    def test_non_llama_model_cannot_masquerade_as_llama(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            manifest = home / "manifest.json"
            manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
            source = home / "official.csv"
            source.write_text(DATA, encoding="utf-8")
            with patch.dict(os.environ, {
                "PULSE_LLM_API_KEY": "dummy-key", "PULSE_LLM_ENDPOINT":
                "https://example.test/v1/chat/completions", "PULSE_LLM_MODEL": "gemini"}):
                with self.assertRaisesRegex(ValueError, "llama_model_required"):
                    pipeline(manifest, source, home / "out", ai_mode="llama")


if __name__ == "__main__":
    unittest.main()
