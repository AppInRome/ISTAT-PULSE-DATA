"""PULSE architecture 2 offline integration tests — fake numerical fixture ONLY."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import pulse_ai_provider as ai
from scripts import pulse_editorial_audit_v1 as audit
from scripts import pulse_editorial_engine_v1 as engine
from scripts import pulse_italia_auto_pipeline as pipeline
from scripts import pulse_editorial_architecture_v2 as architecture

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture():
    raw = (FIXTURES / "pulse_italia_integration_FAKE.csv").read_bytes()
    manifest = json.loads((FIXTURES / "pulse_italia_integration_manifest.json").read_text())
    return engine.extract(manifest, raw)


def research_bundle(folder, evidence, preview=None, locked=True):
    folder.mkdir(parents=True,exist_ok=True)
    (folder / "evidence.json").write_text(json.dumps(evidence),encoding="utf-8")
    (folder / "preview.json").write_text(
        json.dumps(preview if preview is not None else pipeline.build_preview(evidence)),encoding="utf-8")
    (folder / "review_required.json").write_text(json.dumps({
        "publication_allowed": not locked,
        "review_status": "pending_human_signoff" if locked else "published",
        "evidence_sha256": audit.digest(evidence),
    }),encoding="utf-8")


class ArchitectureIntegrationTests(unittest.TestCase):
    def test_verified_fixture_generates_brief_with_exact_graphs_without_ai(self):
        e=fixture()
        with TemporaryDirectory() as td:
            root=Path(td)
            research_bundle(root/"research"/"one", e)
            report=architecture.prepare(root/"research",root/"queue",target=30)
            self.assertEqual(report["research_bundles_checked"],1)
            self.assertEqual(report["briefs_prepared_for_ai"],1)
            self.assertEqual(report["not_written_due_to_lack_of_verified_sources"],29)
            self.assertEqual(report["ai_calls"],0)
            self.assertEqual(report["automatically_published"],0)
            briefs=list((root/"queue"/"briefs").glob("*.json"))
            self.assertEqual(len(briefs),1)
            b=json.loads(briefs[0].read_text())
            self.assertFalse(b["publish_allowed"])
            self.assertTrue(b["not_yet_an_article"])
            self.assertEqual(b["brief"]["source"]["evidence_sha256"], audit.digest(e))

    def test_tampered_graph_and_table_rejected(self):
        e=fixture()
        preview=pipeline.build_preview(e)
        preview["chart_spec"]["data"][-1]["value"] += 900
        with TemporaryDirectory() as td:
            root=Path(td)
            research_bundle(root/"in"/"bad",e,preview)
            report=architecture.prepare(root/"in",root/"out")
            self.assertEqual(report["briefs_prepared_for_ai"],0)
            self.assertIn("chart_differs_from_verified_observations",
                          report["excluded"][0]["reasons"])

    def test_unverified_and_self_approved_are_excluded(self):
        e=fixture()
        with TemporaryDirectory() as td:
            root=Path(td)
            research_bundle(root/"in"/"approved",e,locked=False)
            bad=dict(e)
            bad["verified"]=False
            research_bundle(root/"in"/"not_verified",bad)
            report=architecture.prepare(root/"in",root/"out")
            self.assertEqual(report["briefs_prepared_for_ai"],0)
            self.assertEqual(len(report["excluded"]),2)

    def test_duplicate_source_story_does_not_fill_30_quota(self):
        e=fixture()
        with TemporaryDirectory() as td:
            root=Path(td)
            research_bundle(root/"in"/"one",e)
            research_bundle(root/"in"/"two",e)
            report=architecture.prepare(root/"in",root/"out")
            self.assertEqual(report["briefs_prepared_for_ai"],1)
            self.assertEqual(report["not_written_due_to_lack_of_verified_sources"],29)
            self.assertTrue(any("duplicate_statistical_story" in x["reasons"]
                                for x in report["excluded"]))


class ProviderTests(unittest.TestCase):
    def test_mistral_is_optional_and_does_not_look_for_cloudflare_credentials(self):
        with patch.dict(os.environ, {
            "PULSE_AI_PROVIDER":"mistral",
            "PULSE_MISTRAL_API_KEY":"",
            "PULSE_CF_AI_TOKEN":"old-account",
            "PULSE_CF_ACCOUNT_ID":"0"*32,
        }):
            self.assertFalse(ai.configure_environment())
            self.assertEqual(ai.credentials_status(),"missing_mistral_credentials")
        with patch.dict(os.environ, {
            "PULSE_AI_PROVIDER":"mistral", "PULSE_MISTRAL_API_KEY":"FAKE-KEY",
        }):
            self.assertTrue(ai.configure_environment())
            self.assertEqual(os.environ["PULSE_LLM_ENDPOINT"],
                             "https://api.mistral.ai/v1/chat/completions")
            self.assertEqual(os.environ["PULSE_LLM_MODEL"],"mistral-small-2603")
            self.assertLess(ai.reserved_cost("x"*4000), ai.run_budget_limit())
            self.assertEqual(ai.budget_unit(),"USD_upper_estimate")

    def test_mistral_draft_stays_unpublished_and_separate_from_llama(self):
        e=fixture()
        with patch.dict(os.environ, {
            "PULSE_AI_PROVIDER":"mistral", "PULSE_MISTRAL_API_KEY":"FAKE-KEY",
        }), TemporaryDirectory() as td, \
             patch.object(pipeline, "run_data_tools", return_value={
                 "analyst":{"status":"completed"},
                 "dstory":{"status":"completed"},
                 "inspector":{"status":"completed"},
             }), \
             patch.object(pipeline.engine, "call_model", return_value={
                 "title":"Esempio di verifica di una serie italiana",
                 "lead":"Un esempio sufficientemente lungo per verificare il passaggio editoriale senza utilizzare alcuna API reale in questo test.",
                 "paragraphs":["Testo dimostrativo di verifica numerica."]*4,
             }), \
             patch.object(pipeline.audit, "audit", return_value={"passed":True,"issues":[]}):
            result=pipeline.run_pipeline(td,discovery_fn=lambda:([e],{"sources_considered":[]}),max_sources=30)
            self.assertEqual(result["ai_provider"],"mistral")
            self.assertEqual(result["ai_attempts"],1)
            self.assertEqual(result["ai_audited_drafts"],1)
            self.assertFalse(result["requires_human_editorial_review"] is False)
            folder=Path(td)/result["results"][0]["id"]
            self.assertTrue((folder/"ai_draft.json").exists())
            self.assertFalse((folder/"llama_draft.json").exists())
            self.assertFalse((folder/"approval.json").exists())


if __name__=="__main__":
    unittest.main()
