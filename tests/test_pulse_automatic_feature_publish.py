"""Tests of the independent no-AI, official-only Android publication channel."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts import pulse_editorial_audit_v1 as audit
from scripts import pulse_editorial_engine_v1 as engine
from scripts import pulse_italia_auto_pipeline as pipeline
from scripts import pulse_deterministic_writer as writer
from scripts import pulse_automatic_feature_publish as release

FIX = Path(__file__).resolve().parent / "fixtures"


def fixture():
    manifest=json.loads((FIX/"pulse_italia_integration_manifest.json").read_text())
    return engine.extract(manifest,(FIX/"pulse_italia_integration_FAKE.csv").read_bytes())


def research(folder,evidence):
    folder.mkdir(parents=True,exist_ok=True)
    draft,assessment=writer.write_verified_article(evidence)
    assert draft is not None,assessment
    (folder/"evidence.json").write_text(json.dumps(evidence))
    (folder/"deterministic_draft.json").write_text(json.dumps(draft))
    (folder/"preview.json").write_text(json.dumps(pipeline.build_preview(evidence,draft)))
    (folder/"review_required.json").write_text(json.dumps({
        "evidence_sha256":audit.digest(evidence),
        "draft_sha256":audit.digest({k:v for k,v in draft.items() if k!="audit"}),
        "draft_origin":"deterministic_no_ai",
        "publication_allowed":False,
        "data_components":{
            "data_analyst":{"status":"completed"},
            "data2story_inspector":{"status":"completed"},
            "dstory":{"status":"verified_fallback",
                      "chart_engine":"pulse_italia_chart_analytics.calculate"}
        }
    }))
    return draft


class AutomaticOfficialFeatureTests(TestCase):
    def test_one_verified_non_ai_article_persisted_and_deduplicated(self):
        e=fixture()
        # A fake fixture has an official extraction method; it can be rendered by APK.
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            research(root/"work"/"a",e)
            out=root/"data"/"automatic_features.json"
            a=release.publish(root/"work",out,now="2026-11-14T13:00:00Z")
            self.assertEqual(a["published_new"],1,a)
            self.assertEqual(a["ai_calls"],0)
            item=json.loads(out.read_text())["articles"][0]
            self.assertEqual(item["publication_status"],"published")
            self.assertFalse(item["automatic_review"]["model_used"])
            self.assertFalse(item["automatic_review"]["human_editorial_approval"])
            self.assertEqual(len(item["verified_series_relevant"]),1)
            b=release.publish(root/"work",out,now="2026-11-15T13:00:00Z")
            self.assertEqual(b["published_new"],0)
            self.assertEqual(json.loads(out.read_text())["articles"][0]["published_at"],
                             "2026-11-14T13:00:00Z")

    def test_rejects_tampered_values_without_removing_existing(self):
        e=fixture()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            draft=research(root/"work"/"good",e)
            out=root/"news"/"automatic_features.json"
            release.publish(root/"work",out,now="2026-11-14T13:00:00Z")
            research(root/"work"/"bad",e)
            path=root/"work"/"bad"/"preview.json"
            preview=json.loads(path.read_text())
            preview["chart_spec"]["data"][-1]["value"] += 10000
            path.write_text(json.dumps(preview))
            result=release.publish(root/"work",out)
            self.assertEqual(result["rejected"],1)
            self.assertEqual(len(json.loads(out.read_text())["articles"]),1)

    def test_smart_editorial_only_releases_relevant_new_reference_period(self):
        from scripts import pulse_editorial_selector as selection
        e=fixture()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            research(root/"work"/"a",e)
            output=root/"news"/"automatic_features.json"
            ledger=root/"news"/"source_versions.json"
            homepage=root/"news"/"editorial_frontpage.json"
            old_period=e["series"]["observations"][-2]["period"]
            ledger.parent.mkdir(parents=True, exist_ok=True)
            ledger.write_text(json.dumps({"schema":selection.REGISTRY,"series":{
                selection.series_key(e):{
                    "last_period":old_period,
                    "observation_signature":"0"*64,
                    "history":[]
                }
            }}))
            result=release.publish(root/"work",output,
                now="2026-11-14T18:40:00Z",smart=True,
                versions_file=ledger,frontpage_file=homepage)
            self.assertEqual(result["new_features_selected"],1,result)
            a=json.loads(output.read_text())["articles"][0]
            start=json.loads(homepage.read_text())
            self.assertEqual(start["featured_article_ids"],[a["id"]])
            self.assertEqual(start["features_new"],[a["id"]])
            before=output.read_bytes()
            next_run=release.publish(root/"work",output,
                now="2026-11-14T18:45:00Z",smart=True,
                versions_file=ledger,frontpage_file=homepage)
            self.assertEqual(next_run["published_new"],0)
            self.assertEqual(output.read_bytes(),before)

    def test_context_analysis_publishes_once_with_explicit_old_data_warning(self):
        # These are fabricated test observations, NOT Italian public data.
        manifest=json.loads((FIX/"pulse_italia_integration_manifest.json").read_text())
        raw=(FIX/"pulse_italia_integration_FAKE.csv").read_bytes().replace(
            b";2025;14,1", b";2025;14,4")
        e=engine.extract(manifest,raw)
        e["topic"]="DEMOGRAFIA"
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            research(root/"work"/"a",e)
            out=root/"data"/"automatic_features.json"
            ledger=root/"data"/"source_versions.json"
            frontpage=root/"data"/"editorial_frontpage.json"
            first=release.publish(root/"work",out,now="2026-11-14T18:40:00Z",
                    smart=True,versions_file=ledger,frontpage_file=frontpage)
            self.assertEqual(first["published_new"],1,first)
            self.assertEqual(first["new_features_selected"],0,first)
            self.assertEqual(first["new_context_analyses_published"],1,first)
            article=json.loads(out.read_text())["articles"][0]
            self.assertEqual(article["editorial_kind"],"verified_context_analysis")
            self.assertIn("non segnala una nuova pubblicazione",article["summary"])
            self.assertEqual(article["period_reference"],"2025")
            self.assertEqual(article["publication_status"],"published")
            self.assertEqual(json.loads(frontpage.read_text())["features_new"],[])
            again=release.publish(root/"work",out,now="2026-11-15T18:40:00Z",
                    smart=True,versions_file=ledger,frontpage_file=frontpage)
            self.assertEqual(again["published_new"],0,again)
            self.assertEqual(len(json.loads(out.read_text())["articles"]),1)

    def test_without_evidence_never_publishes_media_article(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            result=release.publish(root/"missing",root/"automatic_features.json")
            self.assertEqual(result["published_new"],0)
            self.assertEqual(json.loads((root/"automatic_features.json").read_text())["articles"],[])

    def test_end_to_end_release_to_mobile_source_contract_and_corrupt_input(self):
        """Fixture evidence only: never copied into the production feed."""
        from scripts import pulse_editorial_selector as selection
        e=fixture()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            research(root/"work"/"valid",e)
            feed=root/"news"/"automatic_features.json"
            versions=root/"news"/"source_versions.json"
            front=root/"news"/"editorial_frontpage.json"
            versions.parent.mkdir(parents=True, exist_ok=True)
            versions.write_text(json.dumps({"schema":selection.REGISTRY,"series":{
                selection.series_key(e):{
                    "last_period":e["series"]["observations"][-2]["period"],
                    "observation_signature":"0"*64,
                    "history":[]
                }
            }}))
            result=release.publish(root/"work",feed,smart=True,
                now="2026-11-14T18:40:00Z",
                versions_file=versions,frontpage_file=front)
            self.assertEqual(result["published_new"],1,result)
            article=json.loads(feed.read_text())["articles"][0]
            self.assertEqual(article["publication_status"],"published")
            self.assertEqual(article["automatic_review"]["original_source_sha256"],
                             article["source_documents"][0]["sha256"])
            self.assertTrue(article["editorial_story"]["source_locked"])
            self.assertEqual(article["chart_spec"]["status"],"verified")
            self.assertEqual(article["table_spec"]["status"],"verified")
            self.assertGreaterEqual(len(article["pulse_article_body"]),4)
            self.assertIn(article["id"],json.loads(front.read_text())["featured_article_ids"])
            baseline=feed.read_bytes()
            rerun=release.publish(root/"work",feed,smart=True,
                now="2026-11-14T19:00:00Z",
                versions_file=versions,frontpage_file=front)
            self.assertEqual(rerun["published_new"],0,rerun)
            self.assertEqual(feed.read_bytes(),baseline)
            # The original published dossier survives a malformed new candidate.
            research(root/"work"/"tampered",e)
            p=root/"work"/"tampered"/"preview.json"
            bad=json.loads(p.read_text())
            bad["chart_spec"]["data"][-1]["value"]+=100
            p.write_text(json.dumps(bad))
            blocked=release.publish(root/"work",feed,smart=True,
                now="2026-11-14T19:10:00Z",
                versions_file=versions,frontpage_file=front)
            self.assertGreaterEqual(blocked["rejected"],1)
            self.assertEqual(feed.read_bytes(),baseline)
