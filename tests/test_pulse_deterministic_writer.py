"""Offline regression for recovered historical PULSE deterministic longform.

No AI call, no live network, no publication; all numbers from a fake fixture.
"""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scripts import pulse_editorial_engine_v1 as editor
from scripts import pulse_deterministic_writer as writer
from scripts import pulse_italia_auto_pipeline as pipeline

FIX = Path(__file__).resolve().parent / "fixtures"


def evidence_fixture():
    manifest=json.loads((FIX/"pulse_italia_integration_manifest.json").read_text())
    data=(FIX/"pulse_italia_integration_FAKE.csv").read_bytes()
    return editor.extract(manifest, data)


class HistoricalDeterministicWriterTests(TestCase):
    def test_original_longform_is_independently_audited_no_ai(self):
        e=evidence_fixture()
        draft,report=writer.write_verified_article(e)
        self.assertIsNotNone(draft,report)
        self.assertTrue(report["passed"],report)
        self.assertGreaterEqual(report["word_count"],250)
        self.assertLessEqual(report["word_count"],500)
        self.assertGreaterEqual(len(draft["paragraphs"]),4)
        self.assertTrue(draft["requires_human_review"])
        self.assertEqual(draft["source_url"],e["source_url"])
        self.assertEqual(draft["dataset_url"],e["dataset_url"])

    def test_rejects_invented_or_unverified_evidence(self):
        e=evidence_fixture()
        e["verified"]=False
        draft,report=writer.write_verified_article(e)
        self.assertIsNone(draft)
        self.assertFalse(report["passed"])

    def test_pipeline_without_ai_has_real_article_but_cannot_publish(self):
        e=evidence_fixture()
        with TemporaryDirectory() as td, \
             patch.object(pipeline,"run_data_tools",return_value={
                 "data_analyst":{"status":"completed"},
                 "dstory":{"status":"verified_fallback",
                          "chart_engine":"pulse_italia_chart_analytics.calculate",
                          "external_cli_completed":False},
                 "data2story_inspector":{"status":"completed"},
             }), \
             patch.object(pipeline.engine,"call_model",
                          side_effect=AssertionError("AI must NEVER be called")):
            report=pipeline.run_pipeline(td,discovery_fn=lambda:([e],{"sources_considered":[]}),
                                         ai_enabled=False,max_sources=3)
            self.assertEqual(report["deterministic_no_ai_drafts"],1,report)
            self.assertEqual(report["ai_attempts"],0)
            folder=Path(td)/report["results"][0]["id"]
            draft=json.loads((folder/"deterministic_draft.json").read_text())
            preview=json.loads((folder/"preview.json").read_text())
            review=json.loads((folder/"review_required.json").read_text())
            self.assertTrue(draft["audit"]["passed"])
            self.assertEqual(preview["pulse_article_body"][0]["text"],draft["paragraphs"][0])
            self.assertEqual(len(preview["pulse_article_body"]),len(draft["paragraphs"]))
            self.assertEqual(review["draft_origin"],"deterministic_no_ai")
            self.assertFalse(review["publication_allowed"])
            self.assertFalse(preview["publishable_without_review"])
            self.assertFalse((folder/"approval.json").exists())


if __name__=="__main__":
    import unittest
    unittest.main()
