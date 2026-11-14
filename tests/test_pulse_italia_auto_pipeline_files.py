"""Offline source-to-article pipeline integration tests (FAKE fixtures only).

Never makes a real HTTP call, invokes Cloudflare or publishes news.
"""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from scripts import pulse_editorial_engine_v1 as engine
from scripts.pulse_italia_auto_pipeline import load_official_file_evidences, run_pipeline

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class AutomaticFilePipelineTests(TestCase):
    def fixture_evidence(self):
        raw = (FIXTURES / "pulse_italia_integration_FAKE.csv").read_bytes()
        manifest = json.loads((FIXTURES / "pulse_italia_integration_manifest.json").read_text())
        evidence = engine.extract(manifest, raw)
        evidence.update({
            "auto_discovered": True,
            "dataset_format_original": "csv",
            "dataset_bytes_sha256": sha256(raw).hexdigest(),
        })
        return evidence, raw

    def test_realistic_official_file_path_reaches_graph_and_table_preview(self):
        evidence, raw = self.fixture_evidence()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "discovery"
            source.mkdir()
            (source / "fake.json").write_text(json.dumps(evidence))
            with patch("scripts.pulse_italia_auto_pipeline.engine.fetch", return_value=raw):
                report = run_pipeline(
                    root / "review", external_evidence_dir=source,
                    discovery_fn=lambda: ([], {"sources_considered": []}),
                    ai_enabled=False, max_sources=6,
                )
            self.assertEqual(report["candidate_articles"], 1)
            self.assertEqual(report["published_articles"], 0)
            self.assertEqual(report["official_discovery"]["independent_csv_json_xlsx_discovery"]["files_reverified"], 1)
            preview = json.loads(Path(report["results"][0]["preview"]).read_text())
            self.assertEqual(preview["publication_status"], "draft")
            self.assertFalse(preview["publishable_without_review"])
            self.assertGreaterEqual(len(preview["table_spec"]["rows"]), 2)
            self.assertEqual(
                [(x["period"], x["value"]) for x in preview["chart_spec"]["data"]],
                [tuple(x) for x in preview["table_spec"]["rows"]],
            )
            self.assertEqual(len(preview["chart_analyses"]["views"]), 6)

    def test_workflow_calls_llama_and_saves_audited_article_for_review(self):
        # The fake model is deliberately local: this tests wiring and review
        # bundle creation, never consumes Workers AI credit.
        evidence, _ = self.fixture_evidence()
        proposal = {
            "title": "Esempio di analisi di una serie statistica ufficiale",
            "lead": "Questa è una verifica tecnica del flusso di creazione delle notizie da dati statistici ufficiali italiani, senza alcuna pubblicazione.",
            "paragraphs": ["Testo di prova per la pipeline."] * 4,
        }
        accepted = {"passed": True, "issues": []}
        with tempfile.TemporaryDirectory() as td, \\
             patch("scripts.pulse_italia_auto_pipeline.configure_environment", return_value=True), \\
             patch("scripts.pulse_italia_auto_pipeline.engine.call_model", return_value=proposal) as model, \\
             patch("scripts.pulse_italia_auto_pipeline.audit.audit", return_value=accepted), \\
             patch("scripts.pulse_italia_auto_pipeline.run_data_tools", return_value={
                 "data_analyst": {"status": "completed"},
                 "dstory": {"status": "completed"},
                 "data2story_inspector": {"status": "completed"},
             }):
            report = run_pipeline(
                td, discovery_fn=lambda: ([evidence], {"sources_considered": []}),
                ai_enabled=True,
            )
            model.assert_called_once()
            self.assertTrue(report["llama_configured"])
            self.assertEqual(report["llama_attempts"], 1)
            self.assertEqual(report["llama_audited_drafts"], 1)
            folder = Path(td) / report["results"][0]["id"]
            self.assertTrue((folder / "llama_draft.json").is_file())
            self.assertFalse((folder / "approval.json").exists())
            preview = json.loads((folder / "preview.json").read_text())
            self.assertEqual(len(preview["pulse_article_body"]), 4)
            self.assertEqual(preview["publication_status"], "draft")

    def test_missing_cloudflare_credentials_are_explicit_in_result(self):
        evidence, _ = self.fixture_evidence()
        with tempfile.TemporaryDirectory() as td, \\
             patch("scripts.pulse_italia_auto_pipeline.configure_environment", return_value=False), \\
             patch("scripts.pulse_italia_auto_pipeline.engine.call_model") as model, \\
             patch("scripts.pulse_italia_auto_pipeline.run_data_tools", return_value={}):
            report = run_pipeline(
                td, discovery_fn=lambda: ([evidence], {"sources_considered": []}),
                ai_enabled=True,
            )
            model.assert_not_called()
            self.assertFalse(report["llama_configured"])
            self.assertEqual(report["llama_status"], "missing_cloudflare_credentials")
            self.assertEqual(report["results"][0]["llama"], "missing_cloudflare_credentials")

    def test_modified_official_file_is_rejected_before_llama(self):
        evidence, raw = self.fixture_evidence()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fake.json"
            p.write_text(json.dumps(evidence))
            with patch("scripts.pulse_italia_auto_pipeline.engine.fetch", return_value=raw + b"\nMODIFIED"):
                good, checks = load_official_file_evidences(Path(td))
            self.assertEqual(good, [])
            self.assertEqual(checks[0]["status"], "rejected")
            self.assertEqual(checks[0]["reason"], "source_changed_since_discovery")

    def test_unverified_file_cannot_enter_newsroom(self):
        evidence, raw = self.fixture_evidence()
        evidence["verified"] = False
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "fake.json").write_text(json.dumps(evidence))
            with patch("scripts.pulse_italia_auto_pipeline.engine.fetch", return_value=raw) as fetch:
                eligible, checks = load_official_file_evidences(td)
            self.assertEqual(eligible, [])
            self.assertEqual(checks[0]["status"], "rejected")
            fetch.assert_not_called()
