"""Review/release safety: fake fixtures, no real article publication."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from scripts.pulse_italia_reviewed_publish import (
    is_published_feature, overlay_approved, load_reviewed, update_feed
)

def feature():
    return {
        "id": "PULSE-EDITORIAL-EXAMPLE123",
        "publication_status": "published", "editorial_status": "verified",
        "editorial_format": "ai_assisted_independently_audited_human_approved",
        "geographic_scope": {"country_code": "IT"},
        "public_source": {"role": "primary_statistical_source",
                          "url": "https://www.istat.it/dati"},
        "editorial_review": {"reviewer": "Test reviewer",
                             "approved_at": "2026-11-14T08:00:00+01:00",
                             "evidence_sha256": "a"*64},
        "source_documents": [{"url": "https://www.istat.it/dati.csv",
                              "sha256": "c"*64}],
        "chart_spec": {"status": "verified", "data": [
            {"period":"2024","value":1.2},{"period":"2025","value":1.3}]},
        "table_spec": {"status": "verified", "rows": [
            ["2024",1.2],["2025",1.3]]},
        "published_at": "2026-11-14T07:00:00Z",
    }

class PublishTests(unittest.TestCase):
    def test_verified_feed_shape(self):
        self.assertTrue(is_published_feature(feature()))

    def test_no_approved_is_no_publication(self):
        a, idx, added = overlay_approved(
            {"articles":[{"id":"old","published_at":"2026-01-01"}]},
            {"oggi":["old"],"ieri":[],"archivio":[]}, {"articles":[]})
        self.assertEqual(added,0)
        self.assertEqual(len(a["articles"]),1)

    def test_exact_table_chart_equality_required(self):
        a=feature()
        a["table_spec"]["rows"][-1][1]=4
        self.assertFalse(is_published_feature(a))

    def test_official_scope_and_editor_required(self):
        a=feature()
        a["geographic_scope"]={"country_code":"FR"}
        self.assertFalse(is_published_feature(a))
        a=feature()
        a["editorial_review"]["reviewer"]=""
        self.assertFalse(is_published_feature(a))
        a=feature()
        a["public_source"]["url"]="https://www.istat.it.evil.test/dati"
        self.assertFalse(is_published_feature(a))

    def test_approved_persists_through_new_feed_refresh(self):
        base={"articles":[{"id":"old","published_at":"2026-11-13T12:00:00Z"}]}
        buckets={"oggi":["old"],"ieri":[],"archivio":[]}
        a,b,added=overlay_approved(base,buckets,{"articles":[feature()]})
        self.assertEqual(added,1)
        self.assertIn(feature()["id"],b["archivio"])
        a2,b2,added2=overlay_approved(a,b,{"articles":[feature()]})
        self.assertEqual(added2,0)
        self.assertEqual(len(a2["articles"]),2)
        self.assertEqual(len(b2["archivio"]),1)

    def test_rewrite_approved_date_fails(self):
        a=feature()
        prior={**a,"published_at":"2025-01-01T00:00:00Z"}
        with self.assertRaisesRegex(ValueError,"date"):
            overlay_approved({"articles":[prior]},
                             {"oggi":[],"ieri":[],"archivio":[]},
                             {"articles":[a]})

    def test_reviewed_bundle_absent_is_empty_not_approved(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(load_reviewed(Path(td)/"missing"), [])

    def test_update_feed_no_reviewed_does_not_invent(self):
        with tempfile.TemporaryDirectory() as td:
            t=Path(td)
            (t/"articles.json").write_text(json.dumps({"articles":[]}))
            (t/"index.json").write_text(
                json.dumps({"oggi":[],"ieri":[],"archivio":[]}))
            report=update_feed(t/"approved",t/"store.json",
                               t/"articles.json",t/"index.json")
            self.assertEqual(report["added_to_feed"],0)
            self.assertEqual(report["durable_published_total"],0)


if __name__ == "__main__":
    unittest.main()
